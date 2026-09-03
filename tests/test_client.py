from __future__ import annotations

import gzip
import json
import unittest
import zlib

import brotli

from Btrans.client import (
    ResponseParseError,
    TranslationClient,
    TranslationResult,
    decompress_content,
)

PAYLOAD = (
    b'[{"detectedLanguage":{"language":"en"},'
    b'"translations":[{"text":"ok"}]}]'
)


class ClientTests(unittest.TestCase):
    def test_decompress_gzip(self) -> None:
        compressed = gzip.compress(PAYLOAD)
        self.assertEqual(decompress_content(compressed, "gzip"), PAYLOAD)

    def test_decompress_br(self) -> None:
        compressed = brotli.compress(PAYLOAD)
        self.assertEqual(decompress_content(compressed, "br"), PAYLOAD)

    def test_decompress_deflate(self) -> None:
        compressed = zlib.compress(PAYLOAD)
        self.assertEqual(decompress_content(compressed, "deflate"), PAYLOAD)

    def test_unsupported_encoding_raises(self) -> None:
        with self.assertRaises(ResponseParseError):
            decompress_content(PAYLOAD, "snappy")

    def test_extract_result_from_json_structure(self) -> None:
        payload = json.loads(PAYLOAD)
        result = TranslationClient._extract_result(payload)
        self.assertEqual(
            result,
            TranslationResult(text="ok", detected_language="en"),
        )

    def test_missing_translation_raises(self) -> None:
        with self.assertRaises(ResponseParseError):
            TranslationClient._extract_result([{"translations": []}])


if __name__ == "__main__":
    unittest.main()

