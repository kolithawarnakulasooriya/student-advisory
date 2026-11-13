"""Revision headers for ordinary JSON responses; validated answers remain buffered."""

import json
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.routing import APIRoute


class RevisionRoute(APIRoute):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        responses = kwargs.get("responses") or {}
        status = kwargs.get("status_code") or 200
        entry = responses.setdefault(status, {})
        entry.setdefault("headers", {})["ETag"] = {
            "description": "Current revision, when the response contains a top-level version.",
            "schema": {"type": "string"},
        }
        kwargs["responses"] = responses
        super().__init__(*args, **kwargs)

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def revised(request: Request) -> Response:
            response = await handler(request)
            body = getattr(response, "body", b"")
            if body and response.headers.get("content-type", "").startswith("application/json"):
                value = json.loads(body)
                version = value.get("version") if isinstance(value, dict) else None
                if type(version) is int:
                    response.headers["ETag"] = f'"{version}"'
            return response

        return revised
