"""Bound request bytes before multipart parsing/spooling, including chunked bodies."""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.security import ApiError


class UploadLimit:
    def __init__(self, app: ASGIApp, maximum: int):
        self.app = app
        self.maximum = maximum

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        total = 0

        async def limited() -> Message:
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > self.maximum:
                raise ApiError(413, "FILE_TOO_LARGE", "The request exceeds the size limit.")
            return message

        await self.app(scope, limited if scope["type"] == "http" else receive, send)
