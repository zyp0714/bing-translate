"""Bing Translator 低层 HTTP 客户端。"""

from __future__ import annotations

import gzip
import json
import zlib
from dataclasses import dataclass

import brotli
import requests

from Btrans.exceptions import (
    InvalidParameterResponse,
    ResponseParseError,
    TranslationClientError,
    TranslationRequestError,
)
from Btrans.params import API_BASE, HOME_URL, USER_AGENT, ParamProvider

POST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": API_BASE,
    "Referer": HOME_URL,
}

DEFAULT_TIMEOUT = 20.0


@dataclass(frozen=True, slots=True)
class TranslationResult:
    """从 Bing JSON 响应中提取出的结果。"""

    text: str
    detected_language: str | None = None


def decompress_content(data: bytes, content_encoding: str | None) -> bytes:
    """手动解码 HTTP 内容，使 br 处理不依赖 requests 内部实现。"""

    encoding = (content_encoding or "").strip().lower()
    if not encoding:
        return data
    if encoding == "br":
        try:
            return brotli.decompress(data)
        except brotli.error as exc:
            raise ResponseParseError(f"brotli decode failed: {exc}") from exc
    if encoding == "gzip":
        try:
            return gzip.decompress(data)
        except OSError as exc:
            raise ResponseParseError(f"gzip decode failed: {exc}") from exc
    if encoding == "deflate":
        try:
            return zlib.decompress(data)
        except zlib.error:
            try:
                return zlib.decompress(data, -zlib.MAX_WBITS)
            except zlib.error as exc:
                raise ResponseParseError(f"deflate decode failed: {exc}") from exc
    raise ResponseParseError(f"unsupported Content-Encoding: {encoding!r}")


class TranslationClient:
    """使用共享 ParamProvider 提供的参数发送一次翻译 POST 请求。"""

    def __init__(
        self,
        param_provider: ParamProvider,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._provider = param_provider
        self._session = param_provider.session
        self._timeout = timeout

    def translate(
        self,
        text: str,
        from_lang: str,
        to_lang: str,
    ) -> TranslationResult:
        params = self._provider.get()
        url = params.build_url()
        body = {
            "fromLang": from_lang,
            "to": to_lang,
            "text": text,
            "token": params.token,
            "key": params.key,
        }
        response = self._session.post(
            url,
            headers=POST_HEADERS,
            data=body,
            timeout=self._timeout,
        )
        if response.status_code in (205, 400):
            raise InvalidParameterResponse(
                f"server invalidated parameters (HTTP {response.status_code})"
            )
        if response.status_code != 200:
            raise TranslationRequestError(
                f"translation request failed (HTTP {response.status_code})"
            )
        return self._parse_response(response)

    def _parse_response(self, response: requests.Response) -> TranslationResult:
        raw = response.raw.read(decode_content=False)
        if raw:
            decoded = decompress_content(
                raw,
                response.headers.get("Content-Encoding"),
            )
        else:
            # requests/urllib3 already decoded br/gzip before exposing content.
            decoded = response.content
        try:
            payload = json.loads(decoded.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ResponseParseError(f"response is not valid JSON: {exc}") from exc
        return self._extract_result(payload)

    @staticmethod
    def _extract_result(payload: object) -> TranslationResult:
        if not isinstance(payload, list):
            raise ResponseParseError("expected top-level JSON list")
        for group in payload:
            if not isinstance(group, dict):
                continue
            translations = group.get("translations")
            if not isinstance(translations, list) or not translations:
                continue
            first = translations[0]
            if not isinstance(first, dict) or not isinstance(first.get("text"), str):
                continue
            detected = group.get("detectedLanguage")
            detected_language: str | None = None
            if isinstance(detected, dict):
                value = detected.get("language")
                detected_language = value if isinstance(value, str) else None
            elif isinstance(detected, str):
                detected_language = detected
            return TranslationResult(
                text=first["text"],
                detected_language=detected_language,
            )
        raise ResponseParseError("no translatable text found in response")
