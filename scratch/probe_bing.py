"""Probe the current Bing Translator web flow end to end.

This is intentionally a throwaway spike: fetch the homepage, extract the
anti-abuse values, POST a translation, and print every verifiable step.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import requests

HOME_URL = "https://cn.bing.com/translator"
API_BASE = "https://cn.bing.com"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

HOME_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": API_BASE + "/",
}

POST_HEADERS = {
    "User-Agent": UA,
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": API_BASE,
    "Referer": HOME_URL,
}

_IG_RE = re.compile(r'\bIG\s*:\s*"([A-Fa-f0-9]+)"')
_ABUSE_RE = re.compile(
    r"params_AbusePreventionHelper\s*=\s*\[(\d+),\s*\"([^\"]+)\",\s*(\d+)\]"
)
_IID_RE = re.compile(r'data-iid="(translator\.\d+)"')
_RICH_RE = re.compile(
    r'params_RichTranslate\s*=\s*\[\s*"([^"]+)"\s*,\s*"([^"]+)"'
)


@dataclass
class PageParams:
    ig: str
    token: str
    key: str
    ttl_ms: int
    iid: str
    endpoint_prefix: str


def fetch_home(session: requests.Session) -> str:
    response = session.get(HOME_URL, headers=HOME_HEADERS, timeout=20)
    print("[step] GET", HOME_URL)
    print("  status =", response.status_code)
    print("  content-encoding =", response.headers.get("Content-Encoding"))
    print("  content-length =", len(response.content))
    print("  cookies after GET =", len(session.cookies))
    response.raise_for_status()
    return response.text


def extract_params(html: str) -> PageParams:
    ig_match = _IG_RE.search(html)
    abuse_match = _ABUSE_RE.search(html)
    iid_match = _IID_RE.search(html)
    rich_match = _RICH_RE.search(html)

    if not all([ig_match, abuse_match, iid_match, rich_match]):
        missing = {
            "IG": bool(ig_match),
            "params_AbusePreventionHelper": bool(abuse_match),
            "data-iid": bool(iid_match),
            "params_RichTranslate": bool(rich_match),
        }
        raise RuntimeError("parameter extraction failed: " + json.dumps(missing))

    timestamp_raw, token_raw, ttl_raw = abuse_match.groups()
    endpoint = rich_match.group(1).replace("\\u0026", "&")
    return PageParams(
        ig=ig_match.group(1),
        token=token_raw,
        key=timestamp_raw,
        ttl_ms=int(ttl_raw),
        iid=iid_match.group(1),
        endpoint_prefix=endpoint,
    )


def build_endpoint(params: PageParams) -> str:
    return (
        API_BASE
        + params.endpoint_prefix
        + "&IG="
        + params.ig
        + "&IID="
        + params.iid
        + "&SFX=0"
    )


def extract_translation(payload: Any) -> str | None:
    if not isinstance(payload, list):
        return None
    for group in payload:
        translations = group.get("translations") if isinstance(group, dict) else None
        if translations and isinstance(translations[0], dict):
            text = translations[0].get("text")
            if text:
                return str(text)
    return None


def translate(
    session: requests.Session,
    params: PageParams,
    text: str,
    from_lang: str,
    to_lang: str,
) -> str:
    url = build_endpoint(params)
    body = {
        "fromLang": from_lang,
        "to": to_lang,
        "text": text,
        "token": params.token,
        "key": params.key,
    }
    print("[step] POST", url)
    print("  body fields =", ",".join(sorted(body)))
    print("  token =", params.token[:6] + "..." + params.token[-4:])
    print("  key =", params.key)

    response = session.post(url, headers=POST_HEADERS, data=body, timeout=20)
    print("  status =", response.status_code)
    print("  content-encoding =", response.headers.get("Content-Encoding"))
    print("  content-type =", response.headers.get("Content-Type"))

    try:
        payload = response.json()
    except requests.JSONDecodeError:
        print("  body (first 500 chars) =", response.text[:500])
        raise RuntimeError("translation response is not JSON")

    print("  json top-level =", type(payload).__name__)
    if isinstance(payload, dict):
        print("  json keys =", ",".join(sorted(payload.keys())))
    translated = extract_translation(payload)
    if not translated:
        raise RuntimeError("no translated text in response: " + response.text[:500])
    return translated


def main() -> int:
    session = requests.Session()
    html = fetch_home(session)
    params = extract_params(html)

    print("[extract] IG =", params.ig)
    print("[extract] token =", params.token[:6] + "..." + params.token[-4:])
    print("[extract] key (timestamp) =", params.key)
    print("[extract] ttl_ms =", params.ttl_ms)
    print("[extract] iid =", params.iid)
    print("[extract] endpoint_prefix =", params.endpoint_prefix)

    translated = translate(session, params, "Hello, world!", "en", "zh-Hans")
    print("[result] zh =", translated)

    translated = translate(session, params, "你好，世界！", "zh-Hans", "en")
    print("[result] en =", translated)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("[error]", type(exc).__name__, str(exc))
        raise SystemExit(1)
