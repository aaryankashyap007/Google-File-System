import time
from dataclasses import dataclass, field

CACHE_TTL_SECONDS = 60

@dataclass
class CacheEntry:
    chunk_handle: int
    primary: str
    replicas: list[str]
    version: int
    expires_at: float = field(default_factory=lambda: time.time() + CACHE_TTL_SECONDS)

class ChunkLocationCache:
    def __init__(self):
        self._cache = {}

    def get(self, filename: str, chunk_index: int) -> CacheEntry | None:
        key = (filename, chunk_index)
        entry = self._cache.get(key)
        if entry and time.time() < entry.expires_at:
            return entry
        self._cache.pop(key, None) # Evict expired entry
        return None

    def put(self, filename: str, chunk_index: int, entry: CacheEntry):
        self._cache[(filename, chunk_index)] = entry

    def invalidate(self, filename: str, chunk_index: int):
        """Call this when a read gets a stale-version error or NOT_FOUND."""
        self._cache.pop((filename, chunk_index), None)