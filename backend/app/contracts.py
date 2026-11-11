"""Deterministic OpenAPI export; does not connect to a database."""

import argparse
import json
from pathlib import Path

from pydantic import SecretStr

from app.config import Settings
from app.main import create_app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    settings = Settings(
        app_env="test",
        database_url=SecretStr("postgresql+psycopg://advisory_app@localhost/advisory_test"),
        auth_database_url=SecretStr("postgresql+psycopg://advisory_auth@localhost/advisory_test"),
        identity_signing_key=SecretStr("contract-export-only-not-a-real-key"),
    )
    path = Path(__file__).resolve().parents[1] / "contracts/openapi.json"
    content = json.dumps(create_app(settings).openapi(), indent=2, sort_keys=True) + "\n"
    if args.check:
        if not path.exists() or path.read_text() != content:
            raise SystemExit("OpenAPI drift: run uv run python -m app.contracts")
    else:
        path.write_text(content)


if __name__ == "__main__":
    main()
