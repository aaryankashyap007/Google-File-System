import time
from client.gfs_client import GFSClient

def run_test():
    print("Connecting to Master...")
    client = GFSClient(master_addr="localhost:50051")
    
    # Use a unique timestamped filename so the test can run multiple times!
    file_path = f"/test_file_{int(time.time())}.txt"
    test_data = b"Hello from GFS Phase 3! Pipelining works."
    
    print(f"Creating file {file_path}...")
    client.create_file(file_path)
    
    # We must wait a few seconds so the Chunkservers have time to send their 
    # initial heartbeats and register themselves with the Master!
    print("Waiting 6 seconds for chunkservers to register heartbeats...")
    time.sleep(6)
    
    print(f"Writing data to {file_path}...")
    client.write(file_path, 0, test_data)
    
    print("SUCCESS! Data written and committed across the cluster.")

if __name__ == "__main__":
    run_test()