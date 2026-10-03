"""Connecting a device (/setup): the app's address, a QR code for it, and the home-screen steps.

Since public release Phase 4b HTTPS is off by default, so the page is "connect a device" and a phone or
tablet needs nothing installed. With HTTPS=on the page also offers the certificate authority and the
trust steps, and these routes are the only ones served over plain HTTP without a redirect (see
PlainHttpRedirect in app/main.py), because a device cannot reach HTTPS until it has them.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, Response

from app.api.envelope import envelope, error_response
from app.config import STATIC_DIR, Settings
from app.netinfo import http_url, lan_ip, other_urls, preferred_host, tablet_url
from app.services.connect import addresses, qr_svg
from app.tls import CA_COMMON_NAME, CA_DOWNLOAD_NAME, CA_MEDIA_TYPE, TlsState

router = APIRouter(tags=["setup"])

CA_DOWNLOAD_PATH = f"/setup/{CA_DOWNLOAD_NAME}"


def ca_name(tls: TlsState) -> str:
    """The certificate authority's name as its certificate says it (an install from before the public
    release keeps its original name), else the name a new one gets."""
    subject = getattr(tls.ca, "subject", None)
    if isinstance(subject, str):
        for part in subject.split(","):
            key, _, value = part.partition("=")
            if key.strip().upper() == "CN" and value.strip():
                return value.strip()
    return CA_COMMON_NAME


@router.get("/setup", include_in_schema=False)
async def setup_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "setup.html", media_type="text/html", headers={"Cache-Control": "no-cache"})


@router.get(CA_DOWNLOAD_PATH, include_in_schema=False, response_model=None)
async def ca_certificate(request: Request) -> FileResponse | Response:
    tls: TlsState | None = request.app.state.tls
    if tls is None or not request.app.state.settings.https:
        return Response("HTTPS is off: there is no certificate to install.", status_code=404, media_type="text/plain")
    # Served inline on purpose: iOS Safari offers to install a profile, Firefox offers to
    # trust the authority, other browsers save the file under the URL's name.
    return FileResponse(tls.ca_cert_path, media_type=CA_MEDIA_TYPE, headers={"Cache-Control": "no-cache"})


@router.get("/api/setup")
def setup_info(request: Request) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    tls: TlsState | None = request.app.state.tls
    ip = lan_ip()
    host = preferred_host(settings, ip)
    https = bool(settings.https and tls is not None)
    data: dict[str, Any] = {
        "scheme": request.url.scheme,
        "https": https,
        "app_url": tablet_url(settings, ip),
        "https_url": tablet_url(settings, ip),  # the name before Phase 4b; kept for old pages
        "other_urls": other_urls(settings, ip),
        "setup_url": f"{http_url(host, settings.port)}/setup",
        "qr_path": "/setup/qr.svg",
        "download_path": CA_DOWNLOAD_PATH if https else None,
        "download_name": CA_DOWNLOAD_NAME if https else None,
        "ca": {"name": ca_name(tls), **tls.ca.summary()} if https and tls is not None else None,
        "server": tls.server.summary() if https and tls is not None else None,
    }
    return envelope(data)


@router.get("/setup/qr.svg", include_in_schema=False)
def setup_qr(request: Request, url: str | None = Query(default=None, max_length=200)) -> Response:
    """A QR code for one of this server's own addresses (the first by default); anything else is refused."""
    settings: Settings = request.app.state.settings
    known = addresses(settings, lan_ip())
    target = url if url is not None else known[0]
    if target not in known:
        return error_response(404, "not_found", "Only this server's own addresses get a QR code.")
    return Response(qr_svg(target), media_type="image/svg+xml", headers={"Cache-Control": "no-cache"})
