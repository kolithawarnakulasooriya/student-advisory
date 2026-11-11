from urllib.parse import urlparse

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore", hide_input_in_errors=True)
    app_env: str = "development"
    auth_mode: str = "mock"
    inference_provider: str = "disabled"
    database_url: SecretStr
    auth_database_url: SecretStr
    session_cookie_secure: bool = False
    identity_signing_key: SecretStr = Field(min_length=32)
    web_origin: str = "http://localhost:3000"
    session_idle_seconds: int = Field(default=1800, ge=1)
    session_absolute_seconds: int = Field(default=28800, ge=1)
    recent_auth_seconds: int = Field(default=600, ge=1)
    verification_seconds: int = Field(default=600, ge=1)
    identity_issuer: str = "urn:advisory:synthetic"
    identity_audience: str = "advisory-api"

    @model_validator(mode="after")
    def safe_runtime(self) -> "Settings":
        # This release deliberately has no live IdP or production serving mode.
        if self.app_env not in {"development", "test"} or self.auth_mode != "mock":
            raise ValueError("Release 0.1 supports explicit development/test mock identity only")
        if self.inference_provider not in {"mock", "disabled"}:
            raise ValueError("Inference is unavailable in Release 0.1")
        origin = urlparse(self.web_origin)
        if origin.hostname not in {"localhost", "127.0.0.1"} or origin.path or origin.query:
            raise ValueError("Synthetic identity requires a loopback web origin")
        if origin.scheme not in {"http", "https"}:
            raise ValueError("Invalid web origin")
        for secret, role in (
            (self.database_url, "advisory_app"),
            (self.auth_database_url, "advisory_auth"),
        ):
            if not secret.get_secret_value().startswith("postgresql+psycopg://"):
                raise ValueError("PostgreSQL with psycopg is required")
            url = make_url(secret.get_secret_value())
            if (
                url.host not in {"localhost", "127.0.0.1"}
                or url.database not in {"advisory_dev", "advisory_test"}
                or url.username != role
            ):
                raise ValueError("Require separate runtime roles on a loopback disposable database")
        return self
