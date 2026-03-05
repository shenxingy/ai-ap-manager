"""X-Request-ID middleware for distributed tracing (pure ASGI — no BaseHTTPMiddleware)."""
import uuid

from starlette.types import ASGIApp, Receive, Scope, Send


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        request_id = headers.get(b"x-request-id", b"").decode() or str(uuid.uuid4())

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers_list = list(message.get("headers", []))
                headers_list.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers_list
            await send(message)

        await self.app(scope, receive, send_wrapper)
