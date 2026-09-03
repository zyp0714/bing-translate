from __future__ import annotations

import tempfile
import time
import unittest

from Btrans.cache import (
    MemoryCache,
    TranslationCache,
    make_cache_key,
)


class CacheTests(unittest.TestCase):
    def test_memory_cache_hit_miss_and_stats(self) -> None:
        cache = TranslationCache(backend=MemoryCache())
        key = make_cache_key("hello", "en", "zh-Hans")
        self.assertIsNone(cache.get(key))
        cache.put(key, {"text": "ok", "detected_language": "en"})
        self.assertEqual(cache.get(key), {"text": "ok", "detected_language": "en"})
        self.assertEqual(cache.stats.hits, 1)
        self.assertEqual(cache.stats.misses, 1)
        self.assertEqual(cache.stats.writes, 1)
        self.assertEqual(cache.get_cache_size(), 1)

    def test_expired_entry_is_removed_on_read(self) -> None:
        cache = TranslationCache(backend=MemoryCache(), ttl_seconds=0.05)
        key = make_cache_key("hello", "en", "zh-Hans")
        cache.put(key, {"text": "ok"})
        time.sleep(0.06)
        self.assertIsNone(cache.get(key))
        self.assertEqual(cache.get_cache_size(), 0)
        self.assertGreaterEqual(cache.stats.expired_removals, 1)

    def test_file_cache_persists_between_instances(self) -> None:
        key = make_cache_key("hello", "en", "zh-Hans")
        with tempfile.TemporaryDirectory() as directory:
            first = TranslationCache(cache_dir=directory)
            first.put(key, {"text": "ok", "detected_language": "en"})
            second = TranslationCache(cache_dir=directory)
            self.assertEqual(
                second.get(key),
                {"text": "ok", "detected_language": "en"},
            )
            self.assertEqual(second.get_cache_size(), 1)

    def test_file_cache_clear_and_prune(self) -> None:
        key = make_cache_key("hello", "en", "zh-Hans")
        with tempfile.TemporaryDirectory() as directory:
            cache = TranslationCache(cache_dir=directory, ttl_seconds=0.05)
            cache.put(key, {"text": "ok"})
            self.assertEqual(cache.get_cache_size(), 1)
            time.sleep(0.06)
            self.assertEqual(cache.prune(), 1)
            self.assertEqual(cache.get_cache_size(), 0)
            cache.put(key, {"text": "ok"})
            cache.clear_cache()
            self.assertEqual(cache.get_cache_size(), 0)

    def test_disabled_cache_does_nothing(self) -> None:
        cache = TranslationCache(backend=MemoryCache(), enabled=False)
        key = make_cache_key("hello", "en", "zh-Hans")
        cache.put(key, {"text": "ok"})
        self.assertIsNone(cache.get(key))
        self.assertEqual(cache.get_cache_size(), 0)
        self.assertEqual(cache.prune(), 0)

    def test_cache_key_depends_on_text_and_language_pair(self) -> None:
        keys = {
            make_cache_key("hello", "en", "zh"),
            make_cache_key("hello", "auto", "zh"),
            make_cache_key("world", "en", "zh"),
        }
        self.assertEqual(len(keys), 3)
        for key in keys:
            self.assertEqual(len(key), 64)


if __name__ == "__main__":
    unittest.main()

