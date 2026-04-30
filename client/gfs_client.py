import grpc
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '../master'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../chunkserver'))

import master_pb2
import master_pb2_grpc
import chunk_pb2
import chunk_pb2_grpc
from client.pipeline import WritePipeline
from client.cache import ChunkLocationCache, CacheEntry

class GFSClient:
    def __init__(self, master_addr="localhost:50051"):
        self.channel = grpc.insecure_channel(master_addr)
        self.master_stub = master_pb2_grpc.MasterServiceStub(self.channel)
        self.pipeline = WritePipeline(self.master_stub)
        self.cache = ChunkLocationCache()
        self._chunk_stubs = {}

    def _get_chunk_stub(self, addr):
        if addr not in self._chunk_stubs:
            channel = grpc.insecure_channel(addr)
            self._chunk_stubs[addr] = chunk_pb2_grpc.ChunkServiceStub(channel)
        return self._chunk_stubs[addr]

    def create_file(self, filename: str):
        resp = self.master_stub.CreateFile(master_pb2.CreateFileRequest(filename=filename))
        if not resp.success:
            raise Exception(f"Failed to create file: {resp.error_message}")
        print(f"File {filename} created successfully.")

    def write(self, filename: str, offset: int, data: bytes):
        self.pipeline.write(filename, offset, data)
        print(f"Successfully wrote {len(data)} bytes to {filename} at offset {offset}.")

    def read(self, filename: str, offset: int, length: int) -> bytes:
        chunk_size = 64 * 1024 * 1024
        result = bytearray()
        remaining = length
        current_off = offset

        while remaining > 0:
            chunk_index = current_off // chunk_size
            chunk_offset = current_off % chunk_size
            read_len = min(remaining, chunk_size - chunk_offset)

            # 1. Check location cache
            loc = self.cache.get(filename, chunk_index)
            if loc is None:
                raw = self.master_stub.GetChunkLocations(master_pb2.ChunkLocRequest(
                    filename=filename, chunk_index=chunk_index, create_if_missing=False
                ))
                loc = CacheEntry(
                    chunk_handle=raw.chunk_handle,
                    primary=raw.primary_address,
                    replicas=list(raw.secondary_addresses),
                    version=raw.chunk_version
                )
                self.cache.put(filename, chunk_index, loc)

            # 2. Try reading from any replica (prefer primary, fallback to others)
            success = False
            for replica_addr in [loc.primary] + loc.replicas:
                if not replica_addr: continue
                stub = self._get_chunk_stub(replica_addr)
                try:
                    resp = stub.ReadChunk(chunk_pb2.ReadRequest(
                        chunk_handle=loc.chunk_handle,
                        offset=chunk_offset,
                        length=read_len,
                        chunk_version=loc.version
                    ))
                    if resp.checksum_ok:
                        result.extend(resp.data)
                        success = True
                        break
                    else:
                        print(f"Checksum mismatch on {replica_addr}, trying next replica...")
                except grpc.RpcError as e:
                    print(f"Read failed on {replica_addr}: {e.code()}. Trying next...")
                    self.cache.invalidate(filename, chunk_index)
                    continue
            
            if not success:
                raise IOError(f"All replicas failed for chunk {loc.chunk_handle}")

            current_off += read_len
            remaining -= read_len

        return bytes(result)
    
    def record_append(self, filename: str, data: bytes) -> int:
        """
        Atomically appends data to filename.
        Returns the offset at which data was written.
        """
        MAX_APPEND_SIZE = 16 * 1024 * 1024  # 16 MB = 1/4 of chunk size
        if len(data) > MAX_APPEND_SIZE:
            raise ValueError(f"Append data exceeds max size ({MAX_APPEND_SIZE} bytes)")

        # Ask master for the LAST chunk of the file (-1)
        raw = self.master_stub.GetChunkLocations(master_pb2.ChunkLocRequest(
            filename=filename,
            chunk_index=-1,
            create_if_missing=True
        ))

        primary = raw.primary_address
        secondaries = list(raw.secondary_addresses)
        
        if not primary:
            raise IOError("No primary lease holder available for append")

        # Send append request to the Primary
        stub = self._get_chunk_stub(primary)
        resp = stub.AppendChunk(chunk_pb2.AppendRequest(
            chunk_handle=raw.chunk_handle,
            data=data,
            forward_to=secondaries
        ))

        if resp.retry_on_next_chunk:
            # In a production GFS, the client would tell the master the chunk is full 
            # and ask it to allocate a new one. For this MVP, we will just return -1.
            print("Chunk is full! Needs padding and retry on next chunk.")
            return -1

        return resp.offset_written