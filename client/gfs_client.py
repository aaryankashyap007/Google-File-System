import grpc
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../master'))

import master_pb2
import master_pb2_grpc
from client.pipeline import WritePipeline

class GFSClient:
    def __init__(self, master_addr="localhost:50051"):
        self.channel = grpc.insecure_channel(master_addr)
        self.master_stub = master_pb2_grpc.MasterServiceStub(self.channel)
        self.pipeline = WritePipeline(self.master_stub)

    def create_file(self, filename: str):
        resp = self.master_stub.CreateFile(master_pb2.CreateFileRequest(filename=filename))
        if not resp.success:
            raise Exception(f"Failed to create file: {resp.error_message}")
        print(f"File {filename} created successfully.")

    def write(self, filename: str, offset: int, data: bytes):
        self.pipeline.write(filename, offset, data)
        print(f"Successfully wrote {len(data)} bytes to {filename} at offset {offset}.")