from pathlib import Path
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
    invitation_hours: int = Field(default=48, ge=1, le=720)
    mail_database_url: SecretStr = SecretStr(
        "postgresql+psycopg://advisory_mail:local-mail-only@127.0.0.1:5432/advisory_dev"
    )
    ingest_database_url: SecretStr = SecretStr(
        "postgresql+psycopg://advisory_ingest:local-ingest-only@127.0.0.1:5432/advisory_dev"
    )
    private_storage_path: Path = Path(__file__).resolve().parents[2] / "local-data/intake"
    parser_image: str = "advisory-parser:0.3"
    scanner_database_path: Path = Path(__file__).resolve().parents[2] / "local-data/clamav"
    max_upload_bytes: int = Field(default=25 * 1024 * 1024, ge=1024, le=25 * 1024 * 1024)
    parser_timeout_seconds: int = Field(default=240, ge=10, le=600)
    smtp_host: str = "127.0.0.1"
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    rag_database_url: SecretStr = SecretStr(
        "postgresql+psycopg://advisory_rag:local-rag-only@127.0.0.1:5432/advisory_dev"
    )
    inference_gateway_url: str = "http://127.0.0.1:11435"
    inference_gateway_token: SecretStr = SecretStr("")
    inference_manifest_path: Path = (
        Path(__file__).resolve().parents[2] / "infra/inference/models.lock.json"
    )
    inference_artifact_path: Path = Path(__file__).resolve().parents[2] / "local-data/inference"
    inference_timeout_seconds: int = Field(default=180, ge=1, le=300)
    vllm_url: str = "http://127.0.0.1:8001"
    vllm_model: str = "advisory-chat"
    vllm_token: SecretStr = SecretStr("")
    identity_issuer: str = "urn:advisory:synthetic"
    identity_audience: str = "advisory-api"

    @model_validator(mode="after")
    def safe_runtime(self) -> "Settings":
        frontend = Path(__file__).resolve().parents[2] / "frontend"
        if self.private_storage_path.resolve().is_relative_to(frontend):
            raise ValueError("Private storage must be outside the frontend directory")
        # This release deliberately has no live IdP or production serving mode.
        if self.app_env not in {"development", "test"} or self.auth_mode != "mock":
            raise ValueError("Release 0.4 supports explicit development/test mock identity only")
        if self.inference_provider not in {"mock", "disabled", "ollama", "vllm"}:
            raise ValueError("Invalid inference provider")
        for endpoint in (self.inference_gateway_url, self.vllm_url):
            parsed = urlparse(endpoint)
            if (
                parsed.scheme != "http"
                or parsed.hostname not in {"127.0.0.1", "localhost"}
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
                or parsed.path
            ):
                raise ValueError("Local inference must use configured loopback HTTP endpoints")
        token_file = self.inference_artifact_path / "gateway-token"
        if self.inference_provider in {"ollama", "vllm"}:
            if not self.inference_gateway_token.get_secret_value() and token_file.is_file():
                self.inference_gateway_token = SecretStr(token_file.read_text().strip())
            if len(self.inference_gateway_token.get_secret_value()) < 32:
                raise ValueError("Private inference gateway token is required")
            if self.inference_provider == "vllm" and not self.vllm_token.get_secret_value():
                raise ValueError("Private vLLM authentication is required")
        if self.smtp_host not in {"127.0.0.1", "localhost"}:
            raise ValueError("Synthetic invitations require loopback SMTP")
        origin = urlparse(self.web_origin)
        if origin.hostname not in {"localhost", "127.0.0.1"} or origin.path or origin.query:
            raise ValueError("Synthetic identity requires a loopback web origin")
        if origin.scheme not in {"http", "https"}:
            raise ValueError("Invalid web origin")
        for secret, role in (
            (self.database_url, "advisory_app"),
            (self.auth_database_url, "advisory_auth"),
            (self.mail_database_url, "advisory_mail"),
            (self.ingest_database_url, "advisory_ingest"),
            (self.rag_database_url, "advisory_rag"),
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
