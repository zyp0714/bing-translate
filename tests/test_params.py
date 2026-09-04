from __future__ import annotations

import time
import unittest

from Btrans.exceptions import ParamExtractionError
from Btrans.params import API_BASE, BingPageParams, ParamProvider

_IG = "A1B2C3D4E5F60718"
_TIMESTAMP = "1712345678"
_TOKEN = "AbusePreventionTokenAbc"
_IID = "translator.5023"
_ENDPOINT = "https://cn.bing.com/ttranslatev3?isVertical=1&category=general"

_FAKE_HTML = f"""
<html>
<script>
var IG: "{_IG}";
window.params_AbusePreventionHelper = [{_TIMESTAMP}, "{_TOKEN}", 60000];
<div data-iid="{_IID}"></div>
window.params_RichTranslate = [
    "https://cn.bing.com/ttranslatev3?isVertical=1\\u0026category=general",
    "params_RichTranslate.2"
];
</script>
</html>
"""

_HTML_NO_IG = _FAKE_HTML.replace(f'var IG: "{_IG}";\n', "")
_HTML_NO_ABUSE = _FAKE_HTML.replace(
    f'window.params_AbusePreventionHelper = [{_TIMESTAMP}, "{_TOKEN}", 60000];\n',
    "",
)
_HTML_NO_RICH = _FAKE_HTML.replace(
    'window.params_RichTranslate = [\n'
    '    "https://cn.bing.com/ttranslatev3?isVertical=1\\u0026category=general",\n'
    '    "params_RichTranslate.2"\n'
    "];\n",
    "",
)


class FakeResponse:
    def __init__(self, html: str) -> None:
        self.text = html

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self, pages: list[str]) -> None:
        self._pages = pages
        self.requests = 0

    def get(self, url: str, headers: object, timeout: object) -> FakeResponse:
        self.requests += 1
        return FakeResponse(self._pages.pop(0))


class ParamsTests(unittest.TestCase):
    def test_from_html_extracts_all_fields(self) -> None:
        params = BingPageParams.from_html(_FAKE_HTML, fetched_at=100.0)
        self.assertEqual(params.ig, _IG)
        self.assertEqual(params.key, _TIMESTAMP)
        self.assertEqual(params.token, _TOKEN)
        self.assertEqual(params.ttl_ms, 60_000)
        self.assertEqual(params.iid, _IID)
        self.assertEqual(params.endpoint_prefix, _ENDPOINT)

    def test_expiry_and_url_build(self) -> None:
        params = BingPageParams.from_html(_FAKE_HTML, fetched_at=100.0)
        self.assertEqual(params.expires_at(), 160.0)
        self.assertFalse(params.is_expired(now=159.9))
        self.assertTrue(params.is_expired(now=160.0))
        expected = (
            API_BASE
            + _ENDPOINT
            + "&IG="
            + _IG
            + "&IID="
            + _IID
            + "&SFX=0"
        )
        self.assertEqual(params.build_url(), expected)

    def test_missing_field_raises_extraction_error(self) -> None:
        cases = [
            (_HTML_NO_IG, "IG"),
            (_HTML_NO_ABUSE, "params_AbusePreventionHelper"),
            (_HTML_NO_RICH, "params_RichTranslate"),
        ]
        for html, field in cases:
            with self.subTest(field=field):
                with self.assertRaises(ParamExtractionError) as context:
                    BingPageParams.from_html(html)
                self.assertIn(field, str(context.exception))

    def test_provider_reuses_fresh_parameters(self) -> None:
        session = FakeSession([_FAKE_HTML])
        provider = ParamProvider(session=session, headers={})
        first = provider.get()
        second = provider.get()
        self.assertIs(first, second)
        self.assertEqual(session.requests, 1)

    def test_provider_refetches_after_ttl_expiry(self) -> None:
        short_ttl_html = _FAKE_HTML.replace("60000", "100")
        session = FakeSession([short_ttl_html, _FAKE_HTML])
        provider = ParamProvider(session=session, headers={})
        provider.get()
        time.sleep(0.11)
        provider.get()
        self.assertEqual(session.requests, 2)

    def test_provider_raises_when_homepage_missing_fields(self) -> None:
        session = FakeSession([_HTML_NO_ABUSE])
        provider = ParamProvider(session=session, headers={})
        with self.assertRaises(ParamExtractionError):
            provider.get()
        self.assertEqual(session.requests, 1)


if __name__ == "__main__":
    unittest.main()
