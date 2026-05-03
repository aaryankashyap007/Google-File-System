import time
import sys
import os
import hashlib

sys.path.append(os.path.join(os.path.dirname(__file__), '../'))
from client.gfs_client import GFSClient
import master_pb2

FILE_PATH = f"/fault_test_{int(time.time())}.bin"
DATA_SIZE = 3 * 1024 * 1024  # 5 MB

def port_to_container_name(port):
    port_map = {
        50052: "docker-chunkserver1-1",
        50053: "docker-chunkserver2-1",
        50054: "docker-chunkserver3-1",
        50055: "docker-chunkserver4-1",
    }
    return port_map.get(port, None)

def run_fault_test():
    print("\n" + "="*50)
    print("  GFS FAULT TOLERANCE & RECOVERY TEST")
    print("="*50)
    
    client = GFSClient(master_addr="localhost:50051")
    
    print(f"\n1. Creating file {FILE_PATH}...")
    client.create_file(FILE_PATH)
    time.sleep(6) # Wait for initial heartbeats
    
    print(f"2. Writing {DATA_SIZE // (1024*1024)} MB of data...")
    test_data = os.urandom(DATA_SIZE)
    expected_hash = hashlib.md5(test_data).hexdigest()
    client.write(FILE_PATH, 0, test_data)
    print("   Data written successfully.")

    loc = client.master_stub.GetChunkLocations(master_pb2.ChunkLocRequest(
        filename=FILE_PATH, chunk_index=0, create_if_missing=False
    ))
    
    initial_replicas = [loc.primary_address] + list(loc.secondary_addresses)
    target_to_kill = initial_replicas[-1]
    
    port = int(target_to_kill.split(':')[1])
    container_to_kill = port_to_container_name(port)
    
    print(f"\n3. Current Replicas for Chunk {loc.chunk_handle}:")
    for r in initial_replicas:
        print(f"    {r}")

    print("\n" + "-"*25)
    print("ACTION REQUIRED ON YOUR HOST MACHINE!")
    print("Open a NEW terminal window and run this command:")
    print(f"\n   sudo docker stop {container_to_kill}\n")
    print("-"*25 + "\n")
    
    input("Press ENTER here *after* you have stopped the container...")

    print("\n4. Monitoring cluster for failure detection and re-replication...")
    print("   (Watching heartbeat timeout -> 15s. This will take a moment...)")
    
    recovered = False
    for i in range(20):
        client.cache.invalidate(FILE_PATH, 0)
        loc = client.master_stub.GetChunkLocations(master_pb2.ChunkLocRequest(
            filename=FILE_PATH, chunk_index=0, create_if_missing=False
        ))
        
        # DEBUG: Print raw response
        print(f"   [DEBUG] Raw response: primary='{loc.primary_address}', secondaries={list(loc.secondary_addresses)}")
        
        current_replicas = [loc.primary_address] + list(loc.secondary_addresses)
        current_replicas = [r for r in current_replicas if r] # filter out empty strings
        
        print(f"   [T+{i*2}s] Replica count: {len(current_replicas)} -> {current_replicas}")
        
        if len(current_replicas) == 3 and target_to_kill not in current_replicas:
            recovered = True
            break
            
        time.sleep(2)

    if recovered:
        print("\n RE-REPLICATION SUCCESSFUL!")
        print("   The Master detected the dead node, isolated it, and cloned the data to a surviving node.")
    else:
        print("\n RE-REPLICATION TIMED OUT.")
        print("   Did the replication manager fail to trigger?")

    print("\n5. Verifying Data Integrity...")
    client.cache.invalidate(FILE_PATH, 0)
    recovered_data = client.read(FILE_PATH, 0, DATA_SIZE)
    recovered_hash = hashlib.md5(recovered_data).hexdigest()
    
    if expected_hash == recovered_hash:
        print(" DATA INTEGRITY VERIFIED! Hash matches perfectly despite the server crash.")
    else:
        print(" DATA CORRUPTION DETECTED!")

if __name__ == "__main__":
    run_fault_test()