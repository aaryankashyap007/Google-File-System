import time
import threading

LEASE_DURATION = 60   # seconds

class LeaseManager:
    def __init__(self, metadata_store, oplog):
        self.store = metadata_store
        self.oplog = oplog
        self._lock = threading.Lock()

    def grant_lease(self, chunk_handle: int) -> str | None:
        """Pick a primary and grant it a lease. Increments chunk version."""
        with self._lock:
            chunk = self.store.chunk_map.get(chunk_handle)
            # Filter to healthy replicas
            healthy_replicas = [r for r in chunk.replicas if r not in chunk.stale_replicas]
            
            if not chunk or not healthy_replicas:
                return None

            # Increment version BEFORE notifying replicas
            new_version = self.store.chunk_versions.get(chunk_handle, 0) + 1
            self.store.chunk_versions[chunk_handle] = new_version
            self.oplog.append('GRANT_LEASE', {'chunk_handle': chunk_handle, 'version': new_version})
            
            # Pick the first available healthy replica as primary
            primary = healthy_replicas[0]
            chunk.primary = primary
            chunk.lease_expiry = time.time() + LEASE_DURATION

            return primary

    def has_valid_lease(self, chunk_handle: int) -> bool:
        chunk = self.store.chunk_map.get(chunk_handle)
        if not chunk:
            return False
        return chunk.primary is not None and time.time() < chunk.lease_expiry