from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.config import Settings


class MockIdentityProvider:
    """Backend-only simulator. Assertions never leave this service."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def issue(self, subject: str, verified: bool, mfa: bool = False) -> str:
        now = datetime.now(UTC)
        return jwt.encode(
            {
                "iss": self.settings.identity_issuer,
                "aud": self.settings.identity_audience,
                "sub": subject,
                "iat": now,
                "exp": now + timedelta(seconds=60),
                "email_verified": verified,
                "amr": ["mock", "mfa"] if mfa else ["mock"],
            },
            self.settings.identity_signing_key.get_secret_value(),
            algorithm="HS256",
        )

    def validate(self, assertion: str) -> dict[str, Any]:
        claims: dict[str, Any] = jwt.decode(
            assertion,
            self.settings.identity_signing_key.get_secret_value(),
            algorithms=["HS256"],
            audience=self.settings.identity_audience,
            issuer=self.settings.identity_issuer,
            options={"require": ["iss", "aud", "sub", "exp", "iat", "email_verified", "amr"]},
        )
        if not isinstance(claims["sub"], str) or not claims["sub"]:
            raise jwt.InvalidTokenError("Invalid subject")
        if type(claims["email_verified"]) is not bool or not isinstance(claims["amr"], list):
            raise jwt.InvalidTokenError("Invalid assurance claims")
        return claims
