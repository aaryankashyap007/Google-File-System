import time
import threading
from concurrent import futures
import grpc
import os
from lease import LeaseManager

# Import generated stubs
import master_pb2
import master_pb2_grpc

from metadata import MetadataStore, NamespaceLockManager, FileMetadata
from oplog import OperationLog
from heartbeat import HeartbeatMonitor

class MasterServicer(master_pb2_grpc.MasterServiceServicer):
    def __init__(self):
        self.store = MetadataStore()
        # Make sure the log directory exists based on our Docker env var
        log_dir = os.environ.get('GFS_LOG_DIR', '/data/oplog')
        self.oplog = OperationLog(f"{log_dir}/gfs.log")
        self.locks = NamespaceLockManager()
        self.heartbeat = HeartbeatMonitor(self.store)
        self.lease_manager = LeaseManager(self.store) # ADD THIS LINE

        self._restore_state()
        
        # Start the dead server detection thread
        threading.Thread(target=self.heartbeat.check_dead_servers, daemon=True).start()
        print("[Master] Initialized and ready.")

    def _restore_state(self):
        """On startup: load checkpoint, then replay any subsequent log records."""
        cp = self.oplog.load_checkpoint()
        if cp:
            self.store.namespace = cp['namespace']
            self.store.file_chunks = cp['file_chunks']
            self.store.chunk_map = cp['chunk_map']
            self.store.chunk_versions = cp['chunk_versions']
            self.store._next_handle = cp['next_handle']
            print("[Master] Restored state from checkpoint.")
            
        records = self.oplog.replay()
        for record in records:
            # Replay logic (simplified for MVP)
            if record['op'] == 'CREATE_FILE':
                self.store.namespace[record['filename']] = FileMetadata(
                    path=record['filename'], 
                    created_at=record['ts']
                )
            elif record['op'] == 'ALLOCATE_CHUNK':
                handle = record['chunk_handle']
                filepath = record['filename']
                if filepath not in self.store.file_chunks:
                    self.store.file_chunks[filepath] = []
                self.store.file_chunks[filepath].append(handle)
        print(f"[Master] Replayed {len(records)} operations from log.")

    def CreateFile(self, request, context):
        filepath = request.filename
        locks = self.locks.acquire_for_operation(filepath)
        try:
            if filepath in self.store.namespace:
                return master_pb2.CreateFileResponse(success=False, error_message="File already exists")
            
            self.store.namespace[filepath] = FileMetadata(path=filepath, created_at=time.time())
            self.oplog.append('CREATE_FILE', {'filename': filepath})
            
            return master_pb2.CreateFileResponse(success=True)
        finally:
            for lock in reversed(locks):
                lock.release()

    def GetChunkLocations(self, request, context):
        filepath = request.filename
        chunk_index = request.chunk_index
        
        if filepath not in self.store.namespace:
            context.abort(grpc.StatusCode.NOT_FOUND, "File not found")

        # FIX: Acquire locks BEFORE checking chunk lengths to prevent concurrent 
        # threads from creating multiple "first" chunks simultaneously!
        locks = self.locks.acquire_for_operation(filepath)
        try:
            file_chunks = self.store.file_chunks.get(filepath, [])
            
            # Resolve -1 to the actual last chunk index safely inside the lock
            if chunk_index == -1:
                if len(file_chunks) > 0:
                    chunk_index = len(file_chunks) - 1
                else:
                    chunk_index = 0

            # If the chunk doesn't exist yet, allocate it
            if chunk_index >= len(file_chunks):
                if not request.create_if_missing:
                    context.abort(grpc.StatusCode.NOT_FOUND, "Chunk not found")
                
                import random
                active_servers = list(self.heartbeat._last_seen.keys())
                if not active_servers:
                    context.abort(grpc.StatusCode.UNAVAILABLE, "No active servers")
                
                handle = self.store.allocate_chunk(filepath)
                chosen = random.sample(active_servers, min(3, len(active_servers)))
                self.store.chunk_map[handle].replicas = chosen
                
                self.oplog.append('ALLOCATE_CHUNK', {'filename': filepath, 'chunk_handle': handle})
                
                chunk_index = len(self.store.file_chunks[filepath]) - 1

            chunk_handle = self.store.file_chunks[filepath][chunk_index]
        finally:
            for lock in reversed(locks):
                lock.release()

        # The rest of the method remains exactly the same!
        chunk_meta = self.store.chunk_map[chunk_handle]
        healthy_replicas = [r for r in chunk_meta.replicas if r not in chunk_meta.stale_replicas]
        
        if not self.lease_manager.has_valid_lease(chunk_handle):
            self.lease_manager.grant_lease(chunk_handle)

        primary = chunk_meta.primary if chunk_meta.primary else ""
        secondaries = [r for r in healthy_replicas if r != primary]

        return master_pb2.ChunkLocResponse(
            chunk_handle=chunk_handle,
            primary_address=primary,
            secondary_addresses=secondaries,
            chunk_version=self.store.chunk_versions.get(chunk_handle, 0)
        )

    def HeartBeat(self, request, context):
        chunks_to_delete = self.heartbeat.handle_heartbeat(
            request.chunkserver_address,
            list(request.chunk_handles),
            list(request.chunk_versions)
        )
        return master_pb2.HeartBeatResponse(chunks_to_delete=chunks_to_delete)

def serve():
    port = os.environ.get('GFS_MASTER_PORT', '50051')
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    master_pb2_grpc.add_MasterServiceServicer_to_server(MasterServicer(), server)
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    print(f"[Master] Server started, listening on {port}")
    server.wait_for_termination()

if __name__ == '__main__':
    serve()