import logging
import secrets
from collections.abc import Generator
from datetime import timedelta
from typing import Annotated, cast
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings
from app.db import context, make_engine, transaction
from app.identity import MockIdentityProvider
from app.models import LoginSession, OrgUnit, User, Verification
from app.schemas import (
    CsrfOut,
    EmailInput,
    ErrorOut,
    GrantOut,
    MeOut,
    RegisterInput,
    RegistrationOut,
    Role,
    ScopeOut,
    StatusOut,
    VerifyInput,
)
from app.security import (
    COOKIE,
    ApiError,
    authorize,
    check_csrf,
    csrf_token,
    digest,
    load_actor,
    new_session,
    now,
    scoped_orgs,
    session_for,
)

logger = logging.getLogger("advisory")


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings()
    app = FastAPI(
        title="Student Advisory Foundation",
        version="0.1.0",
        responses={
            401: {"model": ErrorOut},
            403: {"model": ErrorOut},
            404: {"model": ErrorOut},
            409: {"model": ErrorOut},
            422: {"model": ErrorOut},
            503: {"model": ErrorOut},
        },
    )
    app.state.settings = cfg
    app.state.engine = make_engine(cfg.database_url.get_secret_value())
    app.state.auth_engine = make_engine(cfg.auth_database_url.get_secret_value())
    provider = MockIdentityProvider(cfg)

    @app.middleware("http")
    async def boundary(request: Request, call_next):  # type: ignore[no-untyped-def]
        # Never trust client-supplied correlation IDs or log URLs/query strings/bodies.
        request.state.correlation_id = str(uuid4())
        try:
            response = await call_next(request)
        except Exception:
            logger.error("request_failed correlation_id=%s", request.state.correlation_id)
            response = JSONResponse(
                status_code=500,
                content={
                    "code": "INTERNAL_ERROR",
                    "message": "The request could not be completed.",
                    "field_errors": [],
                    "correlation_id": request.state.correlation_id,
                },
            )
        response.headers["x-correlation-id"] = request.state.correlation_id
        response.headers["cache-control"] = "no-store"
        response.headers["x-content-type-options"] = "nosniff"
        return response

    def error(
        request: Request, status: int, code: str, message: str, fields: list[str] | None = None
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            content={
                "code": code,
                "message": message,
                "field_errors": fields or [],
                "correlation_id": request.state.correlation_id,
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return error(request, exc.status_code, "HTTP_ERROR", "The request could not be completed.")

    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError) -> JSONResponse:
        return error(request, exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Pydantic input/ctx may contain secrets; emit field locations only.
        fields = [".".join(map(str, e["loc"])) for e in exc.errors()]
        return error(request, 422, "INVALID_INPUT", "Check the submitted fields.", fields)

    @app.exception_handler(IntegrityError)
    async def conflict(request: Request, exc: IntegrityError) -> JSONResponse:
        return error(request, 409, "CONFLICT", "This operation conflicts with existing data.")

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        return error(request, 503, "SERVICE_UNAVAILABLE", "Service temporarily unavailable. Retry.")

    def db_role(db: Session, expected: str) -> None:
        row = db.execute(
            text(
                "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles "
                "WHERE rolname = current_user"
            )
        ).one()
        owns_tables = db.scalar(
            text(
                "SELECT EXISTS (SELECT 1 FROM pg_class c "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='public' AND c.relowner=(SELECT oid FROM pg_roles "
                "WHERE rolname=current_user) AND c.relkind IN ('r','p'))"
            )
        )
        if row[0] != expected or row[1] or row[2] or owns_tables:
            raise ApiError(503, "UNSAFE_DATABASE_ROLE", "Database role configuration is invalid.")

    def auth_db() -> Generator[Session]:
        with transaction(app.state.auth_engine) as db:
            db_role(db, "advisory_auth")
            yield db

    def app_db() -> Generator[Session]:
        with transaction(app.state.engine) as db:
            db_role(db, "advisory_app")
            yield db

    AuthDB = Annotated[Session, Depends(auth_db, scope="function")]
    AppDB = Annotated[Session, Depends(app_db, scope="function")]

    def signed_session(request: Request, db: Session) -> LoginSession:
        session = session_for(db, request.cookies.get(COOKIE), cfg)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            check_csrf(request, session, cfg)
        return session

    def identity(db: Session, session: LoginSession) -> User:
        if session.user_id is None:
            raise ApiError(401, "SESSION_REQUIRED", "Sign in to continue.")
        user = db.get(User, session.user_id)
        if user is None or user.status != "active":
            raise ApiError(401, "ACCOUNT_UNAVAILABLE", "This account is unavailable.")
        return user

    def issue_challenge(db: Session, user: User) -> str:
        challenge = secrets.token_urlsafe(32)
        db.add(
            Verification(
                user_id=user.id,
                token_hash=digest(challenge),
                expires_at=now() + timedelta(seconds=cfg.verification_seconds),
            )
        )
        return challenge

    @app.get("/api/v1/health/live", response_model=StatusOut)
    def live() -> StatusOut:
        return StatusOut(status="alive")

    @app.get("/api/v1/health/ready", response_model=StatusOut)
    def ready() -> StatusOut:
        try:
            for engine, role in (
                (app.state.engine, "advisory_app"),
                (app.state.auth_engine, "advisory_auth"),
            ):
                with transaction(engine) as db:
                    db_role(db, role)
                    if not db.scalar(
                        text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname='vector')")
                    ):
                        raise ApiError(503, "NOT_READY", "Database is not ready.")
                    protected_tables = db.scalar(
                        text(
                            "SELECT count(*) FROM pg_class c "
                            "JOIN pg_namespace n ON n.oid=c.relnamespace "
                            "WHERE n.nspname='public' AND c.relrowsecurity "
                            "AND c.relforcerowsecurity "
                            "AND c.relname IN ('users','sessions','verifications','role_grants',"
                            "'institutions','org_units')"
                        )
                    )
                    if protected_tables != 6:
                        raise ApiError(503, "NOT_READY", "Database is not ready.")
        except OperationalError:
            raise ApiError(503, "NOT_READY", "Database is not ready.") from None
        return StatusOut(status="ready")

    @app.get("/api/v1/auth/csrf", response_model=CsrfOut)
    def csrf(request: Request, response: Response, db: AuthDB) -> CsrfOut:
        token = request.cookies.get(COOKIE)
        try:
            session_for(db, token, cfg)
        except ApiError:
            token = new_session(db, response, cfg)
        assert token is not None
        return CsrfOut(csrf_token=csrf_token(token, cfg))

    @app.post("/api/v1/auth/sign-in", response_model=StatusOut)
    def sign_in(body: EmailInput, request: Request, response: Response, db: AuthDB) -> StatusOut:
        old = signed_session(request, db)
        # Flush before switching anonymous-session token context.
        db.flush()
        context(db, login_email=body.email)
        user = db.scalar(select(User).where(User.email == body.email))
        if user is None or user.status != "active":
            raise ApiError(401, "SIGN_IN_FAILED", "This synthetic account is unavailable.")
        claims = provider.validate(provider.issue(user.subject, user.verified))
        if claims["sub"] != user.subject or claims["iss"] != user.issuer:
            raise ApiError(401, "SIGN_IN_FAILED", "Identity could not be verified.")
        old.revoked = True
        db.flush()
        new_session(db, response, cfg, user.id)
        return StatusOut(status="signed_in")

    @app.post("/api/v1/auth/register", response_model=RegistrationOut, status_code=201)
    def register(
        body: RegisterInput, request: Request, response: Response, db: AuthDB
    ) -> RegistrationOut:
        old = signed_session(request, db)
        old.revoked = True
        db.flush()
        user_id = uuid4()
        context(db, login_email=body.email, user_id=str(user_id))
        user = User(
            id=user_id,
            issuer=cfg.identity_issuer,
            subject=str(uuid4()),
            email=body.email,
            name=body.name,
            verified=False,
        )
        db.add(user)
        db.flush()
        challenge = issue_challenge(db, user)
        new_session(db, response, cfg, user.id)
        return RegistrationOut(simulator_challenge=challenge)

    @app.post("/api/v1/auth/simulator/challenge", response_model=RegistrationOut)
    def challenge(request: Request, db: AuthDB) -> RegistrationOut:
        session = signed_session(request, db)
        user = identity(db, session)
        if user.verified:
            raise ApiError(409, "ALREADY_VERIFIED", "This account is already verified.")
        return RegistrationOut(simulator_challenge=issue_challenge(db, user))

    @app.post("/api/v1/auth/verify", response_model=StatusOut)
    def verify(body: VerifyInput, request: Request, response: Response, db: AuthDB) -> StatusOut:
        old = signed_session(request, db)
        user = identity(db, old)
        challenge = db.scalar(
            select(Verification)
            .where(
                Verification.token_hash == digest(body.challenge), Verification.user_id == user.id
            )
            .with_for_update()
        )
        if challenge is None or challenge.used or challenge.expires_at <= now():
            raise ApiError(409, "INVALID_CHALLENGE", "Challenge expired or used. Request another.")
        challenge.used, user.verified = True, True
        old.revoked = True
        db.flush()
        claims = provider.validate(provider.issue(user.subject, user.verified))
        if not claims["email_verified"]:
            raise ApiError(401, "VERIFICATION_FAILED", "Verification failed.")
        new_session(db, response, cfg, user.id)
        return StatusOut(status="verified")

    @app.post("/api/v1/auth/simulator/step-up", response_model=StatusOut)
    def step_up(request: Request, response: Response, db: AuthDB) -> StatusOut:
        old = signed_session(request, db)
        user = identity(db, old)
        if not user.verified:
            raise ApiError(403, "VERIFICATION_REQUIRED", "Verify your synthetic email first.")
        claims = provider.validate(provider.issue(user.subject, user.verified, mfa=True))
        old.revoked = True
        db.flush()
        new_session(db, response, cfg, user.id, mfa="mfa" in claims["amr"])
        return StatusOut(status="simulated_mfa_complete")

    @app.post("/api/v1/auth/logout", response_model=StatusOut)
    def logout(request: Request, response: Response, db: AuthDB) -> StatusOut:
        session = signed_session(request, db)
        session.revoked = True
        response.delete_cookie(
            COOKIE, path="/", secure=cfg.session_cookie_secure, httponly=True, samesite="lax"
        )
        return StatusOut(status="signed_out")

    def scope_out(org: OrgUnit) -> ScopeOut:
        return ScopeOut(
            id=org.id,
            institution_id=org.institution_id,
            name=org.name,
            kind=org.kind,
            timezone=org.timezone,
        )

    @app.get("/api/v1/me", response_model=MeOut)
    def me(request: Request, auth: AuthDB, db: AppDB, scope_id: UUID | None = None) -> MeOut:
        session = signed_session(request, auth)
        actor = load_actor(db, session.user_id, session.mfa)
        scopes = scoped_orgs(db, actor)
        if scope_id and scope_id not in actor.allowed_scopes:
            raise ApiError(404, "NOT_FOUND", "Resource not found.")
        selected = scope_id or (scopes[0].id if scopes else None)
        grants = [
            GrantOut(
                id=g.id,
                institution_id=g.institution_id,
                org_unit_id=g.org_unit_id,
                role=cast(Role, g.role),
                status=g.status,
            )
            for g in actor.grants
        ]
        membership = (
            "active"
            if actor.active
            else (
                "pending"
                if any(g.status == "pending" for g in actor.grants)
                else "awaiting_membership"
            )
        )
        return MeOut(
            user_id=actor.user.id,
            email=actor.user.email,
            name=actor.user.name,
            verified=actor.user.verified,
            account_state=actor.user.status,
            membership_state=membership,
            mfa_required=actor.mfa_required,
            recent_auth=bool(
                session.auth_time
                and session.auth_time + timedelta(seconds=cfg.recent_auth_seconds) > now()
            ),
            grant_epoch=actor.user.grant_epoch,
            active_scope=selected,
            memberships=grants,
            active_grants=[g for g in grants if any(a.id == g.id for a in actor.active)],
            capabilities=["org.read", "workspace.view"] if scopes else [],
            scopes=[scope_out(o) for o in scopes],
            expires_at=session.expires_at,
        )

    @app.get("/api/v1/org-units", response_model=list[ScopeOut])
    def organizations(
        request: Request, auth: AuthDB, db: AppDB, scope_id: UUID | None = None
    ) -> list[ScopeOut]:
        session = signed_session(request, auth)
        actor = load_actor(db, session.user_id, session.mfa)
        if scope_id and scope_id not in actor.allowed_scopes:
            raise ApiError(404, "NOT_FOUND", "Resource not found.")
        return [scope_out(o) for o in scoped_orgs(db, actor, scope_id)]

    @app.get("/api/v1/org-units/{org_id}", response_model=ScopeOut)
    def organization(org_id: UUID, request: Request, auth: AuthDB, db: AppDB) -> ScopeOut:
        session = signed_session(request, auth)
        actor = load_actor(db, session.user_id, session.mfa)
        org = db.get(OrgUnit, org_id)
        authorize(actor, "org.read", org)
        assert org is not None
        return scope_out(org)

    return app
