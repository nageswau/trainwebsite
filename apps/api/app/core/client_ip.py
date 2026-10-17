"""The caller's IP address as seen behind the proxies (AGN-024 K11, DEC-SCOPE-224).

The API is reached through the Next.js proxy (`apps/web/app/api/[...path]/route.ts`) and, in production, Caddy, so
`request.client.host` is the web container. Caddy sets `X-Forwarded-For` to the real client address (it replaces a value sent by
an untrusted client), and the Next proxy passes that header on unchanged, adding one only when none arrived. The leftmost entry is
therefore the client. Without a fronting Caddy (local dev) a caller can send its own header, which is acceptable for a throttle."""

import ipaddress

from starlette.requests import Request


def client_ip(request: Request) -> str:
    first = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if first:
        try:
            return str(ipaddress.ip_address(first))
        except ValueError:
            pass
    return request.client.host if request.client else "unknown"
