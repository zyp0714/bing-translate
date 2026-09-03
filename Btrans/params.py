"""Dynamic parameter extraction for the Bing Translator web endpoint."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Final

import requests

HOME_URL: Final = "https://cn.bing.com/translator"
API_BASE: Final = "https://cn.bing.com"
DEFAULT_TIMEOUT: Final = 20.0

USER_AGENT: Final = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS: Final = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": API_BASE + "/",
}

_IG_RE = re.compile(r'\bIG\s*:\s*"([A-Fa-f0-9]+)"')
_ABUSE_RE = re.compile(
    r'params_AbusePreventionHelper\s*=\s*\[(\d+),\s*"([^"]+)",\s*(\d+)\]'
)
_IID_RE = re.compile(r'data-iid="(translator\.\d+)"')
_RICH_RE = re.compile(
    r'params_RichTranslate\s*=\s*\[\s*"([^"]+)",\s*"([^"]+)"'
)


class ParamExtractionError(RuntimeError):
    """Raised when the Bing homepage does not expose the expected fields."""


@dataclass(frozen=True, slots=True)
class BingPageParams:
    """One set of dynamic page parameters plus the moment it was fetched."""

    ig: str
    token: str
    key: str
    ttl_ms: int
    iid: str
    endpoint_prefix: str
    fetched_at: float

    @classmethod
    def from_html(cls, html: str, fetched_at: float | None = None) -> "BingPageParams":
        ig_match = _IG_RE.search(html)
        abuse_match = _ABUSE_RE.search(html)
        iid_match = _IID_RE.search(html)
        rich_match = _RICH_RE.search(html)

        missing = {
            "IG": bool(ig_match),
            "params_AbusePreventionHelper": bool(abuse_match),
            "data-iid": bool(iid_match),
            "params_RichTranslate": bool(rich_match),
        }
        if not all(missing.values()):
            raise ParamExtractionError(
                "missing homepage fields: " + json.dumps(missing)
            )

        timestamp_raw, token_raw, ttl_raw = abuse_match.groups()  # type: ignore[union-attr]
        return cls(
            ig=ig_match.group(1),  # type: ignore[union-attr]
            token=token_raw,
            key=timestamp_raw,
            ttl_ms=int(ttl_raw),
            iid=iid_match.group(1),  # type: ignore[union-attr]
            endpoint_prefix=rich_match.group(1).replace("\\u0026", "&"),  # type: ignore[union-attr]
            fetched_at=time.time() if fetched_at is None else fetched_at,
        )

    def expires_at(self) -> float:
        return self.fetched_at + self.ttl_ms / 1000.0

    def is_expired(self, now: float | None = None) -> bool:
        return time.time() >= self.expires_at() if now is None else now >= self.expires_at()

    def build_url(self, sfx: int = 0, api_base: str = API_BASE) -> str:
        return (
            api_base
            + self.endpoint_prefix
            + "&IG="
            + self.ig
            + "&IID="
            + self.iid
            + "&SFX="
            + str(sfx)
        )


class ParamProvider:
    """Fetches the Bing homepage and caches valid dynamic parameters."""

    def __init__(
        self,
        session: requests.Session | None = None,
        homepage_url: str = HOME_URL,
        headers: dict[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._session = session or requests.Session()
        self._homepage_url = homepage_url
        self._headers = headers or DEFAULT_HEADERS
        self._timeout = timeout
        self._current: BingPageParams | None = None

    @property
    def session(self) -> requests.Session:
        """Session used for both homepage and later translation requests."""

        return self._session

    def get(self, *, force: bool = False) -> BingPageParams:
        if force or self._current is None or self._current.is_expired():
            self._current = self._fetch()
        return self._current

    def refresh(self) -> BingPageParams:
        return self.get(force=True)

    def invalidate(self) -> None:
        self._current = None

    def _fetch(self) -> BingPageParams:
        response = self._session.get(
            self._homepage_url,
            headers=self._headers,
            timeout=self._timeout,
        )
        response.raise_for_status()
        return BingPageParams.from_html(response.text, fetched_at=time.time())
