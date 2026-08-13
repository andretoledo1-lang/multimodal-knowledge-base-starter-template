"""Loopback-only provider readiness endpoint."""
from __future__ import annotations

from functools import lru_cache
from ipaddress import ip_address
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from ..deps import get_settings
from ..provider_readiness import ProviderProbeConfig, ProviderReadinessService
from ..schemas import ProviderStatusResponse

router = APIRouter(tags=["chat"])
_TRUSTED_HOSTS = {"127.0.0.1", "::1", "localhost"}
_TRUSTED_FETCH_SITES = {"none", "same-origin", "same-site"}


def _hostname(value: str) -> str:
    value = value.strip().casefold()
    if value.startswith("[") and "]" in value:
        return value[1 : value.index("]")]
    if value.count(":") == 1:
        value = value.rsplit(":", 1)[0]
    return value.rstrip(".")


def require_loopback_request(request: Request) -> None:
    client = request.client
    if client is None:
        raise HTTPException(status_code=403, detail="Chat provider access is loopback-only.")
    try:
        address = ip_address(client.host)
    except ValueError as exc:
        raise HTTPException(
            status_code=403,
            detail="Chat provider access is loopback-only.",
        ) from exc
    if address.version == 6 and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    if not address.is_loopback:
        raise HTTPException(status_code=403, detail="Chat provider access is loopback-only.")

    host = _hostname(request.headers.get("host", ""))
    if host not in _TRUSTED_HOSTS:
        raise HTTPException(status_code=403, detail="Provider status is loopback-only.")

    origin = request.headers.get("origin")
    if origin:
        parsed = urlparse(origin)
        if parsed.scheme not in {"http", "https"} or _hostname(parsed.netloc) not in _TRUSTED_HOSTS:
            raise HTTPException(status_code=403, detail="Cross-site provider status access is forbidden.")

    fetch_site = request.headers.get("sec-fetch-site")
    if fetch_site and fetch_site.casefold() not in _TRUSTED_FETCH_SITES:
        raise HTTPException(status_code=403, detail="Cross-site provider status access is forbidden.")


@lru_cache(maxsize=1)
def get_provider_readiness_service() -> ProviderReadinessService:
    settings = get_settings()
    return ProviderReadinessService(
        ProviderProbeConfig(
            deepseek_api_key=settings.deepseek_api_key,
            deepseek_base_url=settings.deepseek_base_url,
            deepseek_model=settings.deepseek_model,
            codex_bin=settings.codex_bin,
            codex_model=settings.codex_oauth_model,
            claude_bin=settings.claude_bin,
            claude_sonnet_model=settings.claude_sonnet_model,
            claude_opus_model=settings.claude_opus_model,
            claude_haiku_model=settings.claude_haiku_model,
        )
    )


@router.get("/chat/providers", response_model=ProviderStatusResponse)
def provider_status(
    request: Request,
    response: Response,
    refresh: bool = Query(default=False),
    service: ProviderReadinessService = Depends(get_provider_readiness_service),
) -> ProviderStatusResponse:
    require_loopback_request(request)
    response.headers["Cache-Control"] = "no-store"
    return ProviderStatusResponse.model_validate(service.status_payload(refresh=refresh))
