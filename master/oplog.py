import json
import os
import time
import pickle
import threading

class OperationLog:
    def __init__(self, log_path: str):
        self.log_path = log_path
        self._lock = threading.Lock()
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        self._fh = open(self.log_path, 'a')

    def append(self, op_type: str, payload: dict):
        """Write a log record and force it to disk."""
        with self._lock:
            record = json.dumps({"ts": time.time(), "op": op_type, **payload})
            self._fh.write(record + "\n")
            self._fh.flush()
            os.fsync(self._fh.fileno())

    def replay(self) -> list[dict]:
        """Read all log records. Used on master startup."""
        records = []
        try:
            with open(self.log_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        except FileNotFoundError:
            pass
        return records

    def write_checkpoint(self, metadata_store):
        """Serialize full metadata state to a checkpoint file to shrink the log."""
        with self._lock:
            cp_path = self.log_path + ".checkpoint"
            tmp_path = cp_path + ".tmp"
            
            with open(tmp_path, 'wb') as f:
                pickle.dump({
                    "namespace": metadata_store.namespace,
                    "file_chunks": metadata_store.file_chunks,
                    "chunk_map": metadata_store.chunk_map,
                    "chunk_versions": metadata_store.chunk_versions,
                    "next_handle": metadata_store._next_handle,
                }, f)
            
            os.rename(tmp_path, cp_path)
            
            # Truncate log
            self._fh.close()
            open(self.log_path, 'w').close()
            self._fh = open(self.log_path, 'a')

    def load_checkpoint(self) -> dict | None:
        """Load state from the latest checkpoint."""
        cp_path = self.log_path + ".checkpoint"
        try:
            with open(cp_path, 'rb') as f:
                return pickle.load(f)
        except FileNotFoundError:
            return None