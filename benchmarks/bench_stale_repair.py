import time
import sys
import os
import hashlib

sys.path.append(os.path.join(os.path.dirname(__file__), '../'))
from client.gfs_client import GFSClient
import master_pb2

FILE_PATH = f"/stale_repair_test_{int(time.time())}.bin"
INITIAL_SIZE = 3 * 1024 * 1024  # 3 MB
UPDATE_DATA = b"UPDATED_PAYLOAD"

def port_to_container_name(port):
    port_map = {
        50052: "docker-chunkserver1-1",
        50053: "docker-chunkserver2-1",
        50054: "docker-chunkserver3-1",
        50055: "docker-chunkserver4-1",
    }
    return port_map.get(port, None)

def run_stale_repair_test():
    print("\n" + "="*50)
    print("  GFS STALE REPLICA REPAIR TEST")
    print("="*50)

    client = GFSClient(master_addr="localhost:50051")

    print(f"\n1. Creating file {FILE_PATH} and writing initial data...")
    client.create_file(FILE_PATH)
    time.sleep(6)  # Wait for initial heartbeats

    test_data = os.urandom(INITIAL_SIZE)

    expected_hash = hashlib.md5(test_data + UPDATE_DATA).hexdigest()
    client.write(FILE_PATH, 0, test_data)
    print("   Initial data written.")

    loc = client.master_stub.GetChunkLocations(master_pb2.ChunkLocRequest(
        filename=FILE_PATH, chunk_index=0, create_if_missing=False
    ))

    initial_replicas = [loc.primary_address] + list(loc.secondary_addresses)
    initial_replicas = [r for r in initial_replicas if r]
    if len(initial_replicas) < 3:
        print("Warning: less than 3 replicas available initially. Test may be flaky.")

    target_to_stale = initial_replicas[-1]
    port = int(target_to_stale.split(':')[1])
    container_to_stop = port_to_container_name(port)

    print(f"\n2. Target chosen to be made stale: {target_to_stale} -> {container_to_stop}")

    print("\n" + "-"*25)
    print("ACTION REQUIRED ON YOUR HOST MACHINE!")
    print("Open a NEW terminal window and run this command to stop the target container:")
    print(f"\n   sudo docker stop {container_to_stop}\n")
    print("-"*25 + "\n")
    input("Press ENTER here *after* you have stopped the container (it should be down briefly)...")

    print("\n3. Wait for the Master to declare the stopped chunkserver DEAD (heartbeat timeout).")
    HEARTBEAT_TIMEOUT = 15
    margin = 3
    wait_secs = HEARTBEAT_TIMEOUT + margin
    print(f"   Waiting {wait_secs}s for the master to detect the failure...")
    time.sleep(wait_secs)

    print("\n4. Now perform a write while the target is down (should succeed without that replica).")
    try:
        client.write(FILE_PATH, len(test_data), UPDATE_DATA)
        print("   Update write completed while target was down.")
    except Exception as e:
        print(f"   Update write failed: {e}. Aborting test.")
        return

    print("\nNow start the stopped container again so it comes back alive but stale.")
    print(f"Open a NEW terminal and run: sudo docker start {container_to_stop}")
    input("Press ENTER here *after* you have started the container...")

    print("\n4. Monitoring master for stale-repair completion...")
    repaired = False
    for i in range(30):
        client.cache.invalidate(FILE_PATH, 0)
        loc = client.master_stub.GetChunkLocations(master_pb2.ChunkLocRequest(
            filename=FILE_PATH, chunk_index=0, create_if_missing=False
        ))
        current_replicas = [loc.primary_address] + list(loc.secondary_addresses)
        current_replicas = [r for r in current_replicas if r]
        print(f"   [T+{i*2}s] Replica list: {current_replicas}")

        if target_to_stale in current_replicas:
            repaired = True
            print("   Target has returned to the healthy replica set.")
            break

        time.sleep(2)

    if not repaired:
        print("\nSTALE-REPAIR TIMED OUT. The master did not bring the stale replica up to date in time.")
    else:
        print("\nVerifying data integrity after repair...")
        recovered = client.read(FILE_PATH, 0, INITIAL_SIZE + len(UPDATE_DATA))
        recovered_hash = hashlib.md5(recovered).hexdigest()
        if recovered_hash == expected_hash:
            print("SUCCESS: Stale replica was repaired and data integrity holds (updated payload present).")
        else:
            print("FAIL: Data mismatch after repair. Hash mismatch detected.")

if __name__ == "__main__":
    run_stale_repair_test()
