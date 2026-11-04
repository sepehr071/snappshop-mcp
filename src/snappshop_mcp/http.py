"""Shared async HTTP client for the public API behind Snapp! Shop (snappshop.ir, apix.snappshop.ir).

Every tool goes through `fetch`, which signs in as a guest (no account), caps concurrency, caches GETs briefly and
turns HTTP failures into `ToolError` messages the model can act on.
"""

from __future__ import annotations

import asyncio
import copy
import json as json_lib
import os
import random
import time
import uuid
from typing import Any

import httpx
from curl_cffi.const import CurlOpt
from httpx_curl_cffi import AsyncCurlTransport
from mcp.server.mcpserver.exceptions import ToolError

SITE = "https://snappshop.ir"
API = "https://apix.snappshop.ir"
# The site's own web app sends the lat/lng of Tehran with every call and area ids 29,197 (checked in Chrome 2026-11-04).
LOCATION = {"lat": "35.77331", "lng": "51.418591"}

HEADERS = {
    # User-Agent, sec-ch-ua and TLS come from the impersonated Chrome profile (see _get_client).
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "priority": "u=1, i",
    "s-device": "DESKTOP",
    "s-device-source": "shop",
    "s-area-ids": "29,197",
    "x-origin": SITE,
}

MAX_CONCURRENCY = 3
JITTER = (0.1, 0.4)  # seconds before each uncached call
MAX_RETRIES = 2
MAX_RETRY_WAIT = 10  # cap for Retry-After and backoff, seconds
CACHE_TTL = 60  # seconds; prices and stock change during the day
CACHE_MAX = 128
RETRY_DELAY = 0.5  # seconds, doubled per retry
MAX_BODY = 5_000_000  # bytes; the mega menu is ~130 KB, larger responses are refused
HOSTS = {"apix.snappshop.ir"}  # doubles as the host allowlist

_transport: httpx.AsyncBaseTransport | None = None
_client: httpx.AsyncClient | None = None
_limit: asyncio.Semaphore | None = None
_proxy_index = 0
_retired: set[asyncio.Task] = set()
_cache: dict[tuple, tuple[float, Any]] = {}
_session = {"s-session-id": str(uuid.uuid4()), "uuid": str(uuid.uuid4())}
_token: str | None = None
_token_lock: asyncio.Lock | None = None


class _XhrTransport(AsyncCurlTransport):
    """The Chrome profile sends navigation-only headers; a None value makes curl drop them on XHR calls."""

    def _create_request_params(self, req: httpx.Request) -> dict[str, Any]:
        # The parent drops "accept: */*" as an httpx default; curl would then send Chrome's page Accept instead.
        accept = req.headers.get("accept")
        p = super()._create_request_params(req)
        extra = [(b"cache-control", None)]  # Chrome sends max-age=0 only on a reload
        if req.headers.get("sec-fetch-mode") != "navigate":
            extra += [(b"upgrade-insecure-requests", None), (b"sec-fetch-user", None)]
        p["headers"] = [*p["headers"], *extra, *([(b"accept", b"*/*")] if accept == "*/*" else [])]
        return p


class ApiError(ToolError):
    """A failed upstream call. `status` is the HTTP status, or None for network errors."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def set_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    """Swap the transport (tests use httpx.MockTransport). Drops the current client and guest token."""
    global _transport, _client, _limit, _proxy_index, _token, _token_lock
    _transport, _client, _limit, _proxy_index, _token, _token_lock = transport, None, None, 0, None, None
    _cache.clear()


def _proxies() -> list[str]:
    """SNAPPSHOP_MCP_PROXY: one proxy URL, or a comma-separated list used one at a time."""
    return [p.strip() for p in os.environ.get("SNAPPSHOP_MCP_PROXY", "").split(",") if p.strip()]


def _next_proxy(client: httpx.AsyncClient) -> None:
    """Sticky pool: move to the next proxy after a block or connect error; the next call rebuilds the client.

    Only the client that failed may rotate. The old client is closed late because other requests may still use it.
    """
    global _client, _limit, _proxy_index
    if len(_proxies()) < 2 or client is not _client:
        return
    _client, _limit, _proxy_index = None, None, _proxy_index + 1
    t = asyncio.create_task(_close_later(client))
    _retired.add(t)
    t.add_done_callback(_retired.discard)


async def _close_later(client: httpx.AsyncClient) -> None:
    await asyncio.sleep(30)  # longer than the 20 s request timeout
    await client.aclose()


def _get_client() -> tuple[httpx.AsyncClient, asyncio.Semaphore]:
    global _client, _limit
    if _client is None:
        # System proxy settings are ignored; the proxy only comes from SNAPPSHOP_MCP_PROXY. curl_cffi
        # presents Chrome's TLS/HTTP2 fingerprint and default headers. The proxy goes to the transport.
        proxies = _proxies()
        _client = httpx.AsyncClient(
            transport=_transport
            or _XhrTransport(
                impersonate="chrome",
                default_headers=True,
                curl_options={
                    CurlOpt.NOPROXY: "*"
                },  # httpx-curl-cffi drops its own NOPROXY unless this dict is non-empty
                proxy=proxies[_proxy_index % len(proxies)] if proxies else None,
                max_connections=2 * MAX_CONCURRENCY,
            ),
            headers=HEADERS,
            timeout=httpx.Timeout(20, connect=5),
            limits=httpx.Limits(max_connections=2 * MAX_CONCURRENCY),
            follow_redirects=False,
            trust_env=False,
        )
        _limit = asyncio.Semaphore(MAX_CONCURRENCY)
    assert _limit is not None
    return _client, _limit


def _headers(token: str | None) -> dict[str, str]:
    h = {"Origin": SITE, "Referer": f"{SITE}/", "Accept": "*/*", "sec-fetch-site": "same-site", **_session}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


async def _guest_token(refresh: bool = False) -> str:
    """The site signs every visitor in as a guest: GET guest/v2/token returns a JWT valid for weeks."""
    global _token, _token_lock
    if _token_lock is None:
        _token_lock = asyncio.Lock()
    async with _token_lock:
        if _token is None or refresh:
            r, content = await _request(
                "GET", f"{API}/guest/v2/token", LOCATION, None, _headers(None), "apix.snappshop.ir"
            )
            if r.status_code >= 400:
                raise ApiError(_status_message(r, "apix.snappshop.ir"), r.status_code)
            try:
                _token = json_lib.loads(content)["data"]["token"]
            except (ValueError, KeyError, TypeError) as e:
                raise ApiError("apix.snappshop.ir sent no guest token.", r.status_code) from e
        return _token


async def fetch(path: str, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> Any:
    """Call an apix.snappshop.ir endpoint the way the site's web app does and return the parsed JSON body.

    GET when `body` is None, else POST with a JSON body. Sends the guest token (renewed once on 401). GETs are
    cached briefly and retried up to MAX_RETRIES times on timeout, network error, 5xx or 429 (jittered exponential
    backoff, Retry-After honoured); POSTs and 403 are never retried.
    """
    url = f"{API}/{path.lstrip('/')}"
    host = httpx.URL(url).host
    if host not in HOSTS:
        raise ApiError(f"Refusing to call unexpected host {host}.")
    query = {**LOCATION, **(params or {})}
    method = "GET" if body is None else "POST"
    key = (url, tuple(sorted(query.items())), json_lib.dumps(body, sort_keys=True))
    if method == "GET" and (hit := _cache.get(key)) and time.monotonic() - hit[0] < CACHE_TTL:
        return copy.deepcopy(hit[1])
    token = await _guest_token()
    renewed = False
    for attempt in range(MAX_RETRIES + 1):
        last = attempt == MAX_RETRIES or method == "POST"
        wait = RETRY_DELAY * 2**attempt * random.uniform(1, 1.5)
        try:
            r, content = await _request(method, url, query, body, _headers(token), host)
        except ApiError as e:
            if last or e.status is not None:
                raise
            await asyncio.sleep(min(wait, MAX_RETRY_WAIT))
            continue
        if r.status_code == 401 and not renewed:
            renewed, token = True, await _guest_token(refresh=True)
            continue
        if (r.status_code == 429 or r.status_code >= 500) and not last:
            await asyncio.sleep(min(_retry_after(r) or wait, MAX_RETRY_WAIT))
            continue
        break

    if r.status_code >= 400:
        raise ApiError(_status_message(r, host, content), r.status_code)
    try:
        data = json_lib.loads(content)
    except ValueError as e:
        raise ApiError(f"{host} returned a non-JSON response (HTTP {r.status_code}).", r.status_code) from e
    if method == "GET":
        if len(_cache) >= CACHE_MAX:
            _cache.pop(next(iter(_cache)))
        _cache[key] = (time.monotonic(), copy.deepcopy(data))
    return data


async def _request(method, url, query, body, headers, host) -> tuple[httpx.Response, bytes]:
    client, limit = _get_client()
    try:
        async with limit:
            await asyncio.sleep(random.uniform(*JITTER))
            async with client.stream(method, url, params=query, json=body, headers=headers) as r:
                content = await _read_capped(r, host)
    except httpx.TimeoutException as e:
        raise ApiError(f"{host} did not answer in time. Try again in a moment.") from e
    except httpx.RequestError as e:
        if isinstance(e, httpx.ConnectError | httpx.ProxyError):
            _next_proxy(client)
        raise ApiError(
            f"Could not reach {host} ({type(e).__name__}). Snapp! Shop answers Iranian IPs only: check the "
            "internet connection (or the SNAPPSHOP_MCP_PROXY setting if you use one)."
        ) from e
    if r.status_code in (403, 429):
        _next_proxy(client)  # blocked: try the next proxy on the following call
    return r, content


async def _read_capped(r: httpx.Response, host: str) -> bytes:
    """Read the body, refusing anything over MAX_BODY so one huge answer cannot flood memory or context."""
    buf = bytearray()
    async for chunk in r.aiter_bytes():
        buf += chunk
        if len(buf) > MAX_BODY:
            raise ApiError(f"{host} sent a response over {MAX_BODY // 1_000_000} MB; refused.", r.status_code)
    return bytes(buf)


def _retry_after(r: httpx.Response) -> float | None:
    """Seconds from a numeric Retry-After on a 429/503, else None (HTTP-date form is ignored)."""
    v = r.headers.get("retry-after", "")
    return float(v) if r.status_code in (429, 503) and v.replace(".", "", 1).isdigit() else None


def _status_message(r: httpx.Response, host: str, content: bytes = b"") -> str:
    code = r.status_code
    if code == 403:
        return (
            f"{host} blocked the request (HTTP 403). It only answers Iranian IPs: use an Iranian connection "
            "or set SNAPPSHOP_MCP_PROXY."
        )
    if code == 404:
        return f"{host} found nothing at that address (HTTP 404). Check the product id, category path or seller id."
    if code == 429:
        return f"{host} is rate limiting requests (HTTP 429). Wait a minute before retrying."
    if code >= 500:
        return f"{host} had a server error (HTTP {code}). Try again later."
    try:
        msg = json_lib.loads(content).get("message")
    except (ValueError, AttributeError):
        msg = None
    return f"{host} rejected the request (HTTP {code}{f': {msg}' if msg else ''})."
