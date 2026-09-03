"""Bing Translate 公开翻译门面。"""

from __future__ import annotations

import os

import requests

from Btrans.cache import DEFAULT_TTL_SECONDS, TranslationCache
from Btrans.client import TranslationClient, TranslationResult
from Btrans.exceptions import (
    InvalidParameterResponse,
    ResponseParseError,
    TranslationArgumentError,
    TranslationCacheError,
    TranslationError,
    TranslationRequestError,
)
from Btrans.params import ParamProvider

_PUBLIC_TO_INTERNAL = {
    "auto": "auto-detect",
    "zh": "zh-Hans",
    "en": "en",
}
_SOURCE_LANGS = frozenset(_PUBLIC_TO_INTERNAL)
_TARGET_LANGS = _SOURCE_LANGS - {"auto"}


class Translator:
    """面向调用方的高可用翻译门面，负责参数校验、缓存和失效重试。"""

    def __init__(
        self,
        enable_cache: bool = True,
        cache_dir: str | os.PathLike[str] = "./my_cache",
        *,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        param_provider: ParamProvider | None = None,
        client: TranslationClient | None = None,
        cache: TranslationCache | None = None,
    ) -> None:
        self._param_provider = param_provider or ParamProvider()
        self._client = client or TranslationClient(self._param_provider)
        self._cache: TranslationCache | None
        if cache is not None:
            self._cache = cache
        elif enable_cache:
            self._cache = TranslationCache(
                cache_dir=cache_dir,
                ttl_seconds=ttl_seconds,
            )
        else:
            self._cache = None

    def translate(
        self,
        text: str,
        from_lang: str,
        to_lang: str,
    ) -> TranslationResult:
        """翻译文本，优先返回本地缓存，未命中时请求 Bing。"""

        source, target = self._normalize_languages(text, from_lang, to_lang)
        if self._cache is not None:
            key = self._cache.key_for(text, source, target)
            cached = self._read_cache(key)
            if cached is not None:
                return cached
        else:
            key = None

        try:
            result = self._translate_with_retry(text, source, target)
        except TranslationError:
            raise
        except requests.RequestException as exc:
            raise TranslationRequestError(
                f"translation request failed: {exc}"
            ) from exc

        if key is not None:
            self._write_cache(key, result)
        return result

    def get_cache_size(self) -> int:
        """返回当前缓存中未过期的条目数量。"""

        if self._cache is None:
            return 0
        return self._cache.get_cache_size()

    def clear_cache(self) -> None:
        """清空本地翻译缓存。"""

        if self._cache is not None:
            self._cache.clear_cache()

    def _normalize_languages(
        self,
        text: str,
        from_lang: str,
        to_lang: str,
    ) -> tuple[str, str]:
        if not isinstance(text, str) or not text.strip():
            raise TranslationArgumentError("text must be a non-empty string")
        if from_lang not in _SOURCE_LANGS:
            raise TranslationArgumentError(
                f"unsupported source language: {from_lang!r}"
            )
        if to_lang not in _TARGET_LANGS:
            raise TranslationArgumentError(
                f"unsupported target language: {to_lang!r}"
            )
        return _PUBLIC_TO_INTERNAL[from_lang], _PUBLIC_TO_INTERNAL[to_lang]

    def _translate_with_retry(
        self,
        text: str,
        source: str,
        target: str,
    ) -> TranslationResult:
        return self._translate_once(text, source, target, retried=False)

    def _translate_once(
        self,
        text: str,
        source: str,
        target: str,
        *,
        retried: bool,
    ) -> TranslationResult:
        try:
            return self._client.translate(text, source, target)
        except (InvalidParameterResponse, ResponseParseError):
            if retried:
                raise
            self._param_provider.invalidate()
            return self._translate_once(
                text,
                source,
                target,
                retried=True,
            )

    def _read_cache(self, key: str) -> TranslationResult | None:
        try:
            raw = self._cache.get(key)  # type: ignore[union-attr]
        except TranslationCacheError:
            self._discard_broken_entry(key)
            return None
        if raw is None:
            return None
        try:
            return self._result_from_cache_value(raw)
        except (KeyError, TypeError, ValueError):
            self._discard_broken_entry(key)
            return None

    def _write_cache(
        self,
        key: str,
        result: TranslationResult,
    ) -> None:
        if self._cache is None:
            return
        try:
            self._cache.put(
                key,
                {
                    "text": result.text,
                    "detected_language": result.detected_language,
                },
            )
        except TranslationCacheError:
            pass

    def _discard_broken_entry(self, key: str) -> None:
        if self._cache is None:
            return
        try:
            self._cache.delete(key)
        except TranslationCacheError:
            pass

    @staticmethod
    def _result_from_cache_value(value: object) -> TranslationResult:
        if not isinstance(value, dict):
            raise TypeError("cached value is not an object")
        text = value.get("text")
        if not isinstance(text, str):
            raise ValueError("cached value has no translation text")
        detected = value.get("detected_language")
        detected_language: str | None = (
            detected if isinstance(detected, str) else None
        )
        return TranslationResult(
            text=text,
            detected_language=detected_language,
        )
