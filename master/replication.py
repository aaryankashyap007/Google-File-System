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
        self._stale_queue = queue.Queue()
        self._chunk_stubs = {}
        threading.Thread(target=self._worker, daemon=True).start()
        threading.Thread(target=self._stale_worker, daemon=True).start()

    def _get_stub(self, addr):
        if addr not in self._chunk_stubs:
            channel = grpc.insecure_channel(addr)
            self._chunk_stubs[addr] = chunk_pb2_grpc.ChunkServiceStub(channel)
        return self._chunk_stubs[addr]

    def enqueue(self, chunk_handle: int, priority: str = 'normal'):
        prio_val = 0 if priority == 'high' else 1
        self._queue.put((prio_val, chunk_handle))

    def enqueue_stale_repair(self, chunk_handle: int, stale_address: str):
        self._stale_queue.put((chunk_handle, stale_address))

    def _worker(self):
        while True:
            prio, handle = self._queue.get()
            try:
                self._rereplicate(handle)
            except Exception as e:
                print(f"[Replication] Failed for chunk {handle}: {e}", flush=True)
                time.sleep(2)
                self._queue.put((prio, handle))  # retry

    def _stale_worker(self):
        while True:
            handle, stale_addr = self._stale_queue.get()
            try:
                self._repair_stale_replica(handle, stale_addr)
            except Exception as e:
                print(f"[Replication] Failed to repair stale replica {stale_addr} for chunk {handle}: {e}", flush=True)
                time.sleep(2)
                self._stale_queue.put((handle, stale_addr))

    def _rereplicate(self, chunk_handle: int):
        chunk = self.store.chunk_map.get(chunk_handle)
        if not chunk or len(chunk.replicas) >= 3:
            return   # already healthy or GC'd

        source = chunk.replicas[0] if chunk.replicas else None
        if not source:
            print(f"[WARNING] Chunk {chunk_handle} has NO replicas — DATA LOST!", flush=True)
            return

        all_servers = list(self.heartbeat._last_seen.keys())
        targets = [s for s in all_servers if s not in chunk.replicas]
        if not targets:
            return # No empty servers to replicate to

        target = targets[0]
        print(f"[Replication] Cloning chunk {chunk_handle} from {source} to {target}...", flush=True)

        # Instruct source to push to target
        stub = self._get_stub(source)
        resp = stub.CopyChunkTo(chunk_pb2.CopyRequest(
            chunk_handle=chunk_handle,
            target_address=target,
            chunk_version=self.store.chunk_versions.get(chunk_handle, 0)
        ))
        
        if resp.success:
            chunk.replicas.append(target)
            print(f"[Replication] Success! Chunk {chunk_handle} restored to {len(chunk.replicas)} replicas.", flush=True)
        else:
            raise Exception(resp.error_message)

    def _repair_stale_replica(self, chunk_handle: int, stale_address: str):
        chunk = self.store.chunk_map.get(chunk_handle)
        if not chunk:
            return

        healthy_replicas = [r for r in chunk.replicas if r not in chunk.stale_replicas]
        if not healthy_replicas:
            print(f"[Replication] No healthy replicas for chunk {chunk_handle}; skipping stale repair.", flush=True)
            return

        source = chunk.primary if chunk.primary in healthy_replicas else healthy_replicas[0]
        authoritative_version = self.store.chunk_versions.get(chunk_handle, 0)

        print(f"[Replication] Repairing stale replica {stale_address} for chunk {chunk_handle} from {source} (version {authoritative_version})...", flush=True)

        stub = self._get_stub(source)
        resp = stub.CopyChunkTo(chunk_pb2.CopyRequest(
            chunk_handle=chunk_handle,
            target_address=stale_address,
            chunk_version=authoritative_version
        ))

        if resp.success:
            if stale_address in chunk.stale_replicas:
                chunk.stale_replicas.remove(stale_address)
            if stale_address not in chunk.replicas:
                chunk.replicas.append(stale_address)
            print(f"[Replication] Stale replica {stale_address} repaired for chunk {chunk_handle}.", flush=True)
        else:
            raise Exception(resp.error_message)