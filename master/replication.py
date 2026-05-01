import threading
import queue
import time
import grpc
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '../chunkserver'))
import chunk_pb2
import chunk_pb2_grpc

class ReplicationManager:
    def __init__(self, metadata_store, heartbeat_monitor):
        self.store = metadata_store
        self.heartbeat = heartbeat_monitor
        self._queue = queue.PriorityQueue()
        self._chunk_stubs = {}
        threading.Thread(target=self._worker, daemon=True).start()

    def _get_stub(self, addr):
        if addr not in self._chunk_stubs:
            channel = grpc.insecure_channel(addr)
            self._chunk_stubs[addr] = chunk_pb2_grpc.ChunkServiceStub(channel)
        return self._chunk_stubs[addr]

    def enqueue(self, chunk_handle: int, priority: str = 'normal'):
        prio_val = 0 if priority == 'high' else 1
        self._queue.put((prio_val, chunk_handle))

    def _worker(self):
        while True:
            prio, handle = self._queue.get()
            try:
                self._rereplicate(handle)
            except Exception as e:
                print(f"[Replication] Failed for chunk {handle}: {e}")
                time.sleep(2)
                self._queue.put((prio, handle))  # retry

    def _rereplicate(self, chunk_handle: int):
        chunk = self.store.chunk_map.get(chunk_handle)
        if not chunk or len(chunk.replicas) >= 3:
            return   # already healthy or GC'd

        source = chunk.replicas[0] if chunk.replicas else None
        if not source:
            print(f"[WARNING] Chunk {chunk_handle} has NO replicas — DATA LOST!")
            return

        all_servers = list(self.heartbeat._last_seen.keys())
        targets = [s for s in all_servers if s not in chunk.replicas]
        if not targets:
            return # No empty servers to replicate to

        target = targets[0]
        print(f"[Replication] Cloning chunk {chunk_handle} from {source} to {target}...")

        # Instruct source to push to target
        stub = self._get_stub(source)
        resp = stub.CopyChunkTo(chunk_pb2.CopyRequest(
            chunk_handle=chunk_handle,
            target_address=target
        ))
        
        if resp.success:
            chunk.replicas.append(target)
            print(f"[Replication] Success! Chunk {chunk_handle} restored to {len(chunk.replicas)} replicas.")
        else:
            raise Exception(resp.error_message)