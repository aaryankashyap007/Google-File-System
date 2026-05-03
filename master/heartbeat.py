import time
import threading

HEARTBEAT_INTERVAL = 5       # seconds between expected heartbeats
HEARTBEAT_TIMEOUT  = 15      # seconds before a chunkserver is considered dead

class HeartbeatMonitor:
    def __init__(self, metadata_store, replication_manager=None):
        self.store = metadata_store
        self.replication = replication_manager
        self._last_seen: dict[str, float] = {}   # address -> timestamp
        self._lock = threading.Lock()

    def handle_heartbeat(self, cs_address: str, chunk_handles: list[int], chunk_versions: list[int]):
        """Processes incoming heartbeats and updates replica locations."""
        with self._lock:
            self._last_seen[cs_address] = time.time()

        # Update replica list for each reported chunk
        for handle, version in zip(chunk_handles, chunk_versions):
            if handle not in self.store.chunk_map:
                continue   # Unknown chunk — will be garbage collected later
                
            chunk_meta = self.store.chunk_map[handle]
            master_version = self.store.chunk_versions.get(handle, 0)
            
            if version != master_version:
                if cs_address in chunk_meta.replicas:
                    chunk_meta.replicas.remove(cs_address)
                if cs_address not in chunk_meta.stale_replicas:
                    chunk_meta.stale_replicas.append(cs_address)
                    if self.replication:
                        self.replication.enqueue_stale_repair(handle, cs_address)
            else:
                if cs_address not in chunk_meta.replicas:
                    chunk_meta.replicas.append(cs_address)
                if cs_address in chunk_meta.stale_replicas:
                    chunk_meta.stale_replicas.remove(cs_address)

        # Return chunks this chunkserver should delete (GC)
        # For Phase 1, we just return an empty list. GC comes in Phase 6.
        return list(self.store._gc_pending)

    def check_dead_servers(self):
        """Background thread to detect failed chunkservers."""
        while True:
            time.sleep(HEARTBEAT_INTERVAL)
            now = time.time()
            with self._lock:
                for addr, last in list(self._last_seen.items()):
                    if now - last > HEARTBEAT_TIMEOUT:
                        self._handle_chunkserver_failure(addr)

    def _handle_chunkserver_failure(self, cs_address: str):
        """Remove dead server from all replica lists."""
        print(f"[Master] Chunkserver {cs_address} is DEAD. Removing from replicas.", flush=True)
        for chunk_meta in self.store.chunk_map.values():
            if cs_address in chunk_meta.replicas:
                chunk_meta.replicas.remove(cs_address)
                # Note: Re-replication trigger will be added in Phase 6
        del self._last_seen[cs_address]