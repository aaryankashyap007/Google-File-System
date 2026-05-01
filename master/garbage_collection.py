import time
import threading

# We use 10 seconds for testing (The paper uses 3 days!)
SOFT_DELETE_TTL  = 10        
GC_SCAN_INTERVAL = 10        

class GarbageCollector:
    def __init__(self, metadata_store, oplog):
        self.store = metadata_store
        self.oplog = oplog
        threading.Thread(target=self._run, daemon=True).start()

    def soft_delete(self, filepath: str):
        """Rename file to hidden name. Does NOT free storage yet."""
        file_meta = self.store.namespace.get(filepath)
        if not file_meta:
            return
            
        hidden = f"/.trash/{filepath.replace('/', '_')}_{int(time.time())}"
        self.store.namespace[hidden] = file_meta
        file_meta.deleted = True
        file_meta.hidden_name = hidden
        file_meta.deleted_at = time.time()
        del self.store.namespace[filepath]
        self.oplog.append('DELETE_FILE', {'path': filepath, 'hidden': hidden})
        print(f"[GC] Soft deleted {filepath} -> {hidden}")

    def _run(self):
        while True:
            time.sleep(GC_SCAN_INTERVAL)
            self._scan_and_collect()

    def _scan_and_collect(self):
        now = time.time()
        orphaned_handles = []

        # Phase 1: find expired hidden files and erase their chunk metadata
        for path, meta in list(self.store.namespace.items()):
            if meta.deleted and (now - meta.deleted_at) > SOFT_DELETE_TTL:
                handles = self.store.file_chunks.pop(path, [])
                orphaned_handles.extend(handles)
                del self.store.namespace[path]
                print(f"[GC] Permanently erased metadata for {path}")

        # Phase 2: remove orphaned chunks from chunk_map.
        # They are added to _gc_pending and will be sent to chunkservers on their next heartbeat!
        for handle in orphaned_handles:
            self.store.chunk_map.pop(handle, None)
            self.store.chunk_versions.pop(handle, None)
            self.store._gc_pending.add(handle)