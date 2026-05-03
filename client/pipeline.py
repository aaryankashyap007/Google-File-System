import grpc
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '../master'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../chunkserver'))
import master_pb2
import chunk_pb2
import chunk_pb2_grpc

class WritePipeline:
    def __init__(self, master_stub):
        self.master_stub = master_stub
        self._chunk_stubs = {}
        self._serial_counter = 1

    def _get_chunk_stub(self, addr):
        if addr not in self._chunk_stubs:
            channel = grpc.insecure_channel(addr)
            self._chunk_stubs[addr] = chunk_pb2_grpc.ChunkServiceStub(channel)
        return self._chunk_stubs[addr]

    def _next_serial(self):
        s = self._serial_counter
        self._serial_counter += 1
        return s

    def write(self, filename: str, offset: int, data: bytes):
        chunk_size = 64 * 1024 * 1024
        chunk_index = offset // chunk_size
        chunk_offset = offset % chunk_size

        # Step 1 & 2: Ask master for primary + replica locations
        loc = self.master_stub.GetChunkLocations(master_pb2.ChunkLocRequest(
            filename=filename, chunk_index=chunk_index, create_if_missing=True
        ))
        
        primary = loc.primary_address
        secondaries = list(loc.secondary_addresses)
        
        if not primary:
            raise IOError("No primary lease holder available")

        serial = self._next_serial()

        # Step 3: Push data to ALL replicas (pipelined)
        # We send to primary first, and pass the secondaries so it can chain the data forward
        push_req = chunk_pb2.WriteRequest(
            chunk_handle=loc.chunk_handle,
            offset=chunk_offset,
            data=data,
            serial_number=serial,
            forward_to=secondaries,
            chunk_version=loc.chunk_version
        )
        
        primary_stub = self._get_chunk_stub(primary)
        primary_stub.ForwardWrite(push_req)

        # Step 4: Send write commit to PRIMARY only
        commit_req = chunk_pb2.WriteRequest(
            chunk_handle=loc.chunk_handle,
            offset=chunk_offset,
            data=b'', # Data is already buffered!
            serial_number=serial,
            forward_to=secondaries,
            chunk_version=loc.chunk_version
        )
        
        resp = primary_stub.WriteChunk(commit_req)
        
        # Step 7: Check for errors
        if not resp.success:
            raise IOError(f"Write failed: {resp.error_message}")