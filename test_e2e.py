import time
from client.gfs_client import GFSClient

def run_test():
    print("Connecting to Master...")
    client = GFSClient(master_addr="localhost:50051")
    
    file_path = f"/test_file_{int(time.time())}.txt"
    test_data = b"Hello from GFS! This data was piped through the cluster and read back."
    
    print(f"Creating file {file_path}...")
    client.create_file(file_path)
    
    print("Waiting 6 seconds for chunkservers to register heartbeats...")
    time.sleep(6)
    
    print(f"\n--- WRITING DATA ---")
    client.write(file_path, 0, test_data)
    
    print(f"\n--- READING DATA ---")
    # Read the exact length of our test_data back
    read_data = client.read(file_path, 0, len(test_data))
    print(f"Data read back: {read_data}")
    
    assert read_data == test_data, "Data integrity mismatch!"
    print("\nSUCCESS! Phase 4 Complete. Data matches perfectly.")

if __name__ == "__main__":
    run_test()