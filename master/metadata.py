import threading
from dataclasses import dataclass, field
import time

@dataclass
class FileMetadata:
    path: str
    created_at: float
    deleted: bool = False
    deleted_at: float | None = None
    hidden_name: str | None = None

@dataclass
class ChunkMetadata:
    handle: int
    replicas: list[str] = field(default_factory=list)
    stale_replicas: list[str] = field(default_factory=list)
    primary: str | None = None
    lease_expiry: float = 0.0

class NamespaceLockManager:
    """Read-write locks for namespace paths to allow concurrent mutations."""
    def __init__(self):
        self._locks = {}
        self._meta_lock = threading.Lock()

    def _get_lock(self, path_component: str):
        with self._meta_lock:
            if path_component not in self._locks:
                # Using RLock as a simplified Read/Write lock for the MVP
                self._locks[path_component] = threading.RLock()
            return self._locks[path_component]

    def acquire_for_operation(self, filepath: str):
        """Acquires locks for the full path. Caller must release them."""
        parts = filepath.strip('/').split('/')
        path = ''
        acquired_locks = []
        for part in parts:
            if not part: continue
            path = f"{path}/{part}"
            lock = self._get_lock(path)
            lock.acquire()
            acquired_locks.append(lock)
        return acquired_locks

class MetadataStore:
    def __init__(self):
        self.namespace: dict[str, FileMetadata] = {}
        self.file_chunks: dict[str, list[int]] = {}
        self.chunk_map: dict[int, ChunkMetadata] = {}
        self.chunk_versions: dict[int, int] = {}
        self._next_handle: int = 1
        self._gc_pending: set[int] = set()

    def allocate_chunk(self, filepath: str) -> int:
        """Allocates a new chunk handle and assigns it to a file."""
        handle = self._next_handle
        self._next_handle += 1
        
        if filepath not in self.file_chunks:
            self.file_chunks[filepath] = []
            
        self.file_chunks[filepath].append(handle)
        self.chunk_map[handle] = ChunkMetadata(handle=handle)
        self.chunk_versions[handle] = 0
        return handle