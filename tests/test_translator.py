from __future__ import annotations

import unittest

from Btrans import Translator
from Btrans.cache import MemoryCache, TranslationCache, make_cache_key
from Btrans.client import TranslationResult
from Btrans.exceptions import (
    InvalidParameterResponse,
    ResponseParseError,
    TranslationArgumentError,
    TranslationCacheError,
)


class FakeClient:
    def __init__(
        self,
        *,
        fail_once: bool = False,
        always_fail: bool = False,
        fail_once_parse: bool = False,
    ) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.fail_once = fail_once
        self.always_fail = always_fail
        self.fail_once_parse = fail_once_parse

    def translate(self, text: str, from_lang: str, to_lang: str) -> TranslationResult:
        self.calls.append((text, from_lang, to_lang))
        if self.always_fail or (self.fail_once and len(self.calls) == 1):
            raise InvalidParameterResponse("stale parameters")
        if self.fail_once_parse and len(self.calls) == 1:
            raise ResponseParseError("empty response")
        return TranslationResult(text="ok", detected_language="en")


class FakeProvider:
    def __init__(self) -> None:
        self.invalidated = 0

    def invalidate(self) -> None:
        self.invalidated += 1


class BrokenCacheBackend:
    def get(self, key: str) -> object:
        raise TranslationCacheError("read failed")

    def put(self, key: str, record: object) -> None:
        raise TranslationCacheError("write failed")

    def delete(self, key: str) -> None:
        raise TranslationCacheError("delete failed")

    def clear(self) -> None:
        raise TranslationCacheError("clear failed")

    def keys(self) -> list[str]:
        return []

    def __len__(self) -> int:
        return 0


class TranslatorTests(unittest.TestCase):
    def test_translate_normalizes_languages(self) -> None:
        client = FakeClient()
        translator = Translator(
            enable_cache=False,
            client=client,
            param_provider=FakeProvider(),
        )
        result = translator.translate("hello", from_lang="zh", to_lang="en")
        self.assertEqual(result.text, "ok")
        self.assertEqual(client.calls, [("hello", "zh-Hans", "en")])

    def test_auto_source_maps_to_auto_detect(self) -> None:
        client = FakeClient()
        translator = Translator(
            enable_cache=False,
            client=client,
            param_provider=FakeProvider(),
        )
        translator.translate("hello", from_lang="auto", to_lang="zh")
        self.assertEqual(client.calls, [("hello", "auto-detect", "zh-Hans")])

    def test_invalid_arguments_raise(self) -> None:
        translator = Translator(
            enable_cache=False,
            client=FakeClient(),
            param_provider=FakeProvider(),
        )
        cases = [
            ("", "en", "zh"),
            ("   ", "en", "zh"),
            ("hello", "fr", "zh"),
            ("hello", "en", "auto"),
        ]
        for text, source, target in cases:
            with self.subTest(text=text, source=source, target=target):
                with self.assertRaises(TranslationArgumentError):
                    translator.translate(text, from_lang=source, to_lang=target)

    def test_cache_avoids_second_network_call(self) -> None:
        client = FakeClient()
        cache = TranslationCache(backend=MemoryCache())
        translator = Translator(
            cache=cache,
            client=client,
            param_provider=FakeProvider(),
        )
        first = translator.translate("hello", from_lang="en", to_lang="zh")
        second = translator.translate("hello", from_lang="en", to_lang="zh")
        self.assertEqual(first, second)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(translator.get_cache_size(), 1)

    def test_clear_cache_removes_stored_results(self) -> None:
        client = FakeClient()
        translator = Translator(
            cache=TranslationCache(backend=MemoryCache()),
            client=client,
            param_provider=FakeProvider(),
        )
        translator.translate("hello", from_lang="en", to_lang="zh")
        translator.clear_cache()
        self.assertEqual(translator.get_cache_size(), 0)
        translator.translate("hello", from_lang="en", to_lang="zh")
        self.assertEqual(len(client.calls), 2)

    def test_invalid_parameter_response_retries_once(self) -> None:
        client = FakeClient(fail_once=True)
        provider = FakeProvider()
        translator = Translator(
            enable_cache=False,
            client=client,
            param_provider=provider,
        )
        result = translator.translate("hello", from_lang="en", to_lang="zh")
        self.assertEqual(result.text, "ok")
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(provider.invalidated, 1)

    def test_repeated_invalid_parameter_response_stops_after_one_retry(self) -> None:
        client = FakeClient(always_fail=True)
        provider = FakeProvider()
        translator = Translator(
            enable_cache=False,
            client=client,
            param_provider=provider,
        )
        with self.assertRaises(InvalidParameterResponse):
            translator.translate("hello", from_lang="en", to_lang="zh")
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(provider.invalidated, 1)

    def test_response_parse_error_retries_with_fresh_parameters(self) -> None:
        client = FakeClient(fail_once_parse=True)
        provider = FakeProvider()
        translator = Translator(
            enable_cache=False,
            client=client,
            param_provider=provider,
        )
        result = translator.translate("hello", from_lang="en", to_lang="zh")
        self.assertEqual(result.text, "ok")
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(provider.invalidated, 1)

    def test_broken_cached_value_falls_back_to_translation(self) -> None:
        client = FakeClient()
        cache = TranslationCache(backend=MemoryCache())
        key = make_cache_key("hello", "en", "zh-Hans")
        cache.put(key, {"text": 123})
        translator = Translator(
            cache=cache,
            client=client,
            param_provider=FakeProvider(),
        )
        result = translator.translate("hello", from_lang="en", to_lang="zh")
        self.assertEqual(result.text, "ok")
        self.assertEqual(len(client.calls), 1)

    def test_cache_errors_do_not_break_translation(self) -> None:
        client = FakeClient()
        translator = Translator(
            cache=TranslationCache(backend=BrokenCacheBackend()),
            client=client,
            param_provider=FakeProvider(),
        )
        result = translator.translate("hello", from_lang="en", to_lang="zh")
        self.assertEqual(result.text, "ok")
        self.assertEqual(len(client.calls), 1)

    def test_disabled_cache_helpers_are_noops(self) -> None:
        translator = Translator(
            enable_cache=False,
            client=FakeClient(),
            param_provider=FakeProvider(),
        )
        self.assertEqual(translator.get_cache_size(), 0)
        translator.clear_cache()


if __name__ == "__main__":
    unittest.main()
