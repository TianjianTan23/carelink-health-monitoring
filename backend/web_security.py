"""HTTPS, same-origin CORS and CSRF checks independently of the Node edge."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from starlette.responses import JSONResponse, Response


def allowed_origins():
    configured = os.environ.get("CARELINK_WEB_ORIGINS")
    if configured is not None:
        values = configured.split(",")
    else:
        config = Path(__file__).resolve().parents[1] / ".tls/gateway.json"
        try:
            data = json.loads(config.read_text())
            # Explicit current LAN identity, never arbitrary Host reflection.
            values = [f"https://{data['lanIP']}:8443", f"https://{data['hostname']}:8443", f"https://{data['hostname']}:8444"]
        except (OSError, KeyError, ValueError):
            values = []
    result = set()
    for v in values:
        try:
            u = urlsplit(v)
            port = u.port  # Validate malformed/out-of-range configured ports.
            if (u.scheme == "https" and u.hostname and not u.username and not u.password
                    and u.path in ("", "/") and not u.query and not u.fragment
                    and not any(c.isspace() or c in "\\%" for c in v)
                    and (port is None or 1 <= port <= 65535)):
                result.add(f"https://{u.netloc}")
        except ValueError:
            pass
    return result


class WebSecurity:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            return await self.app(scope, receive, send)
        headers = {}
        for k, v in scope["headers"]:
            key = k.decode("latin1").lower()
            if key in headers and key in {"host", "origin", "referer", "content-type", "x-carelink-csrf", "sec-fetch-site", "cookie", "access-control-request-method", "access-control-request-headers"}:
                return await self.deny("Ambiguous security headers", 400)(scope, receive, send)
            headers[key] = v.decode("latin1")
        origin = scope.get("scheme", "http") + "://" + headers.get("host", "")
        method = scope["method"]
        status, message = None, None
        if scope.get("scheme") != "https":
            status, message = 426, "HTTPS required"
        elif origin not in allowed_origins():
            status, message = 403, "Untrusted Web origin"
        elif headers.get("origin") and headers["origin"] != origin:
            status, message = 403, "Cross-origin request denied"
        elif headers.get("sec-fetch-site") == "cross-site":
            status, message = 403, "Cross-site request denied"
        elif not headers.get("origin") and headers.get("referer"):
            try:
                u = urlsplit(headers["referer"])
                reference = f"{u.scheme}://{u.netloc}"
            except ValueError:
                reference = ""
            if reference != origin:
                status, message = 403, "Cross-origin request denied"
        if not status and method == "OPTIONS":
            requested = {v.strip().lower() for v in headers.get("access-control-request-headers", "").split(",") if v.strip()}
            if headers.get("access-control-request-method") not in {"GET", "POST", "PATCH"} or not requested <= {"content-type", "accept", "x-carelink-csrf"}:
                status, message = 403, "Preflight denied"
            else:
                return await Response(status_code=204, headers={"Access-Control-Allow-Origin":origin,"Access-Control-Allow-Credentials":"true","Access-Control-Allow-Methods":"GET, POST, PATCH","Access-Control-Allow-Headers":"Content-Type, Accept, X-CareLink-CSRF","Vary":"Origin"})(scope, receive, send)
        if not status and method not in {"GET", "HEAD", "OPTIONS"}:
            if headers.get("x-carelink-csrf") != "1" or headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
                status, message = 403, "CSRF validation failed"
        if status:
            return await self.deny(message, status)(scope, receive, send)

        if method not in {"GET", "HEAD", "OPTIONS"}:
            chunks = []
            size = 0
            while True:
                chunk = await receive()
                if chunk["type"] == "http.disconnect":
                    return
                size += len(chunk.get("body", b""))
                if size > 8192:
                    return await self.deny("Request body too large",413)(scope, receive, send)
                chunks.append(chunk)
                if not chunk.get("more_body", False):
                    break
            original_receive = receive
            async def buffered_receive():
                if chunks:
                    return chunks.pop(0)
                return await original_receive()
            receive = buffered_receive

        async def secure_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message["headers"]) + [(b"cache-control",b"no-store"),(b"x-content-type-options",b"nosniff"),(b"vary",b"Origin")]
                if headers.get("origin") == origin:
                    message["headers"] += [(b"access-control-allow-origin",origin.encode()),(b"access-control-allow-credentials",b"true")]
            await send(message)
        await self.app(scope, receive, secure_send)

    @staticmethod
    def deny(message, status):
        return JSONResponse({"detail": message}, status, headers={
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Vary": "Origin"})
