"""
Security Headers Middleware
Adds security-hardening HTTP response headers to every response.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Paths that serve Swagger / ReDoc UI — need relaxed CSP for inline scripts
_DOCS_PATHS = {"/docs", "/redoc"}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: object) -> Response:
        response: Response = await call_next(request)  # type: ignore[operator]

        is_docs = request.url.path in _DOCS_PATHS

        # Prevent MIME-type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Enable XSS protection in older browsers
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # HSTS — only in production (enforced via config check in main.py)
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains; preload"
        )

        # Content Security Policy
        # Swagger UI loads JS/CSS from cdn.jsdelivr.net and images from fastapi.tiangolo.com
        if is_docs:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https://fastapi.tiangolo.com https://cdn.jsdelivr.net; "
                "connect-src 'self'; "
                "font-src 'self' https://cdn.jsdelivr.net; "
                "frame-ancestors 'none';"
            )
        else:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self'; "
                "img-src 'self' data:; "
                "connect-src 'self'; "
                "frame-ancestors 'none';"
            )

        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Remove server identification
        if "server" in response.headers:
            del response.headers["server"]
        if "x-powered-by" in response.headers:
            del response.headers["x-powered-by"]

        # Permissions policy
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )

        return response
