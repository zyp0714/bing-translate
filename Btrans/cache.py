"""带 TTL 过期和可插拔存储的本地翻译缓存。"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Final, Iterator, Protocol

from Btrans.exceptions import TranslationCacheError

DEFAULT_CACHE_DIR: Final = Path("my_cache")
DEFAULT_TTL_SECONDS: Final = 24 * 60 * 60
_JSON_SUFFIX: Final = ".json"
_TMP_SUFFIX: Final = ".tmp"


@dataclass(frozen=True, slots=True)
class CacheRecord:
    """缓存值及其生命周期控制时间戳。"""

    value: Any
    created_at: float
    expires_at: float

    def is_expired(self, now: float | None = None) -> bool:
        current = time.time() if now is None else now
        return current >= self.expires_at


@dataclass(frozen=True, slots=True)
class CacheStats:
    """由 TranslationCache 维护的运行时计数器。"""

    hits: int = 0
    misses: int = 0
    writes: int = 0
    expired_removals: int = 0
    clears: int = 0


class CacheBackend(Protocol):
    """TranslationCache 使用的存储契约。"""

    def get(self, key: str) -> CacheRecord | None: ...

    def put(self, key: str, record: CacheRecord) -> None: ...

    def delete(self, key: str) -> None: ...

    def clear(self) -> None: ...

    def keys(self) -> Iterator[str]: ...

    def __len__(self) -> int: ...


class MemoryCache:
    """用于单元测试和临时运行的内存缓存后端。"""

    def __init__(self) -> None:
        self._records: dict[str, CacheRecord] = {}

    def get(self, key: str) -> CacheRecord | None:
        return self._records.get(key)

    def put(self, key: str, record: CacheRecord) -> None:
        self._records[key] = record

    def delete(self, key: str) -> None:
        self._records.pop(key, None)

    def clear(self) -> None:
        self._records.clear()

    def keys(self) -> Iterator[str]:
        return iter(self._records)

    def __len__(self) -> int:
        return len(self._records)


class FileCache:
    """同一目录下的 JSON 文件缓存，每个 key 对应一个文件。"""

    def __init__(self, cache_dir: str | os.PathLike[str]) -> None:
        self._root = Path(cache_dir)
        self._lock = threading.Lock()
        try:
            self._root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise TranslationCacheError(
                f"cannot create cache directory {self._root}: {exc}"
            ) from exc

    def get(self, key: str) -> CacheRecord | None:
        path = self._path_for(key)
        with self._lock:
            try:
                with path.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
            except FileNotFoundError:
                return None
            except (OSError, ValueError) as exc:
                raise TranslationCacheError(
                    f"cannot read cache entry {path}: {exc}"
                ) from exc
            if not isinstance(data, dict):
                raise TranslationCacheError(
                    f"cache entry {path} is not a JSON object"
                )
            if data.get("key") != key:
                raise TranslationCacheError(
                    f"cache entry {path} does not belong to key {key!r}"
                )
            try:
                return CacheRecord(
                    value=data["value"],
                    created_at=float(data["created_at"]),
                    expires_at=float(data["expires_at"]),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise TranslationCacheError(
                    f"cache entry {path} has invalid fields: {exc}"
                ) from exc

    def put(self, key: str, record: CacheRecord) -> None:
        path = self._path_for(key)
        temporary = Path(str(path) + _TMP_SUFFIX)
        payload = {
            "key": key,
            "value": record.value,
            "created_at": record.created_at,
            "expires_at": record.expires_at,
        }
        with self._lock:
            try:
                with temporary.open("w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False)
                temporary.replace(path)
            except (OSError, TypeError) as exc:
                raise TranslationCacheError(
                    f"cannot write cache entry {path}: {exc}"
                ) from exc
            finally:
                temporary.unlink(missing_ok=True)

    def delete(self, key: str) -> None:
        with self._lock:
            try:
                self._path_for(key).unlink(missing_ok=True)
            except OSError as exc:
                raise TranslationCacheError(
                    f"cannot delete cache entry for {key!r}: {exc}"
                ) from exc

    def clear(self) -> None:
        with self._lock:
            for path in list(self._root.glob("*" + _JSON_SUFFIX)) + list(
                self._root.glob("*" + _JSON_SUFFIX + _TMP_SUFFIX)
            ):
                try:
                    path.unlink(missing_ok=True)
                except OSError as exc:
                    raise TranslationCacheError(
                        f"cannot clear cache file {path}: {exc}"
                    ) from exc

    def keys(self) -> Iterator[str]:
        with self._lock:
            keys = []
            for path in self._root.glob("*" + _JSON_SUFFIX):
                try:
                    with path.open("r", encoding="utf-8") as handle:
                        data = json.load(handle)
                except (OSError, ValueError) as exc:
                    raise TranslationCacheError(
                        f"cannot read cache entry {path}: {exc}"
                    ) from exc
                if not isinstance(data, dict) or not isinstance(
                    data.get("key"), str
                ):
                    raise TranslationCacheError(
                        f"cache entry {path} is missing its key"
                    )
                keys.append(data["key"])
        return iter(keys)

    def __len__(self) -> int:
        with self._lock:
            return sum(1 for _ in self._root.glob("*" + _JSON_SUFFIX))

    def _path_for(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._root / (digest + _JSON_SUFFIX)


def make_cache_key(text: str, from_lang: str, to_lang: str) -> str:
    """根据文本和语言对生成稳定的 SHA-256 key。"""

    payload = "\0".join((text, from_lang, to_lang))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class TranslationCache:
    """包装 CacheBackend 的 TTL 感知缓存门面。"""

    def __init__(
        self,
        cache_dir: str | os.PathLike[str] | None = None,
        *,
        backend: CacheBackend | None = None,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        enabled: bool = True,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if backend is not None:
            self._backend = backend
        else:
            self._backend = FileCache(cache_dir or DEFAULT_CACHE_DIR)
        self._ttl_seconds = ttl_seconds
        self._enabled = enabled
        self._stats = CacheStats()
        self._lock = threading.Lock()

    def key_for(self, text: str, from_lang: str, to_lang: str) -> str:
        """make_cache_key 的便捷封装。"""

        return make_cache_key(text, from_lang, to_lang)

    def get(self, key: str) -> Any | None:
        with self._lock:
            if not self._enabled:
                return None
            record = self._backend.get(key)
            if record is None:
                self._stats = replace(
                    self._stats, misses=self._stats.misses + 1
                )
                return None
            now = time.time()
            if record.is_expired(now):
                self._backend.delete(key)
                self._stats = replace(
                    self._stats,
                    misses=self._stats.misses + 1,
                    expired_removals=self._stats.expired_removals + 1,
                )
                return None
            self._stats = replace(self._stats, hits=self._stats.hits + 1)
            return record.value

    def put(
        self,
        key: str,
        value: Any,
        *,
        ttl_seconds: float | None = None,
    ) -> None:
        with self._lock:
            if not self._enabled:
                return
            now = time.time()
            ttl = self._ttl_seconds if ttl_seconds is None else ttl_seconds
            if ttl <= 0:
                raise ValueError("ttl_seconds must be positive")
            record = CacheRecord(
                value=value,
                created_at=now,
                expires_at=now + ttl,
            )
            self._backend.put(key, record)
            self._stats = replace(self._stats, writes=self._stats.writes + 1)

    def delete(self, key: str) -> None:
        with self._lock:
            if self._enabled:
                self._backend.delete(key)

    def clear_cache(self) -> None:
        with self._lock:
            if self._enabled:
                self._backend.clear()
                self._stats = replace(
                    self._stats, clears=self._stats.clears + 1
                )

    def get_cache_size(self) -> int:
        """返回未过期的缓存值数量。"""

        with self._lock:
            if not self._enabled:
                return 0
            now = time.time()
            size = 0
            for key in self._backend.keys():
                record = self._backend.get(key)
                if record is not None and not record.is_expired(now):
                    size += 1
            return size

    def prune(self) -> int:
        """删除过期缓存值并返回删除数量。"""

        with self._lock:
            if not self._enabled:
                return 0
            now = time.time()
            removed = 0
            for key in self._backend.keys():
                record = self._backend.get(key)
                if record is not None and record.is_expired(now):
                    self._backend.delete(key)
                    removed += 1
            if removed:
                self._stats = replace(
                    self._stats,
                    expired_removals=self._stats.expired_removals + removed,
                )
            return removed

    @property
    def stats(self) -> CacheStats:
        with self._lock:
            return self._stats

    def __len__(self) -> int:
        return self.get_cache_size()
