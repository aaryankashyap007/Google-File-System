import time
import threading
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '../'))
from client.gfs_client import GFSClient

FILE_PATH = f"/concurrent_append_{int(time.time())}.bin"
NUM_CLIENTS = 10
APPENDS_PER_CLIENT = 5
RECORD_DATA = b"x" * 1024  # 1 KB records

def client_worker(client_id: int):
    client = GFSClient(master_addr="localhost:50051")
    for i in range(APPENDS_PER_CLIENT):
        # Create a unique, trackable record payload
        record = f"|CLIENT_{client_id}_MSG_{i}|".encode('utf-8')
        record += RECORD_DATA 
        client.record_append(FILE_PATH, record)
    print(f"Client {client_id} finished appending.")

def run_benchmark():
    print("Initializing cluster and creating target file...")
    setup_client = GFSClient(master_addr="localhost:50051")
    setup_client.create_file(FILE_PATH)
    time.sleep(6)  # Wait for heartbeats
    
    print(f"\n--- Starting {NUM_CLIENTS} concurrent appenders ---")
    threads = []
    start_time = time.time()
    
    for i in range(NUM_CLIENTS):
        t = threading.Thread(target=client_worker, args=(i,))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    elapsed = time.time() - start_time
    total_appends = NUM_CLIENTS * APPENDS_PER_CLIENT
    
    print(f"\n--- BENCHMARK COMPLETE ---")
    print(f"Total time: {elapsed:.2f} seconds")
    print(f"Throughput: {total_appends / elapsed:.2f} appends/sec")
    
    # Read the file back and verify NO data was lost to race conditions
    print("\nVerifying data integrity...")
    file_data = setup_client.read(FILE_PATH, 0, total_appends * (1024 + 20)) # approx size
    
    # Check if every single message from every client made it in
    missing = 0
    for c in range(NUM_CLIENTS):
        for m in range(APPENDS_PER_CLIENT):
            marker = f"|CLIENT_{c}_MSG_{m}|".encode('utf-8')
            if marker not in file_data:
                missing += 1
                print(f"MISSING: {marker}")
                
    if missing == 0:
        print("SUCCESS! Atomic Record Append resolved all concurrent writes flawlessly!")
    else:
        print(f"FAILURE! Lost {missing} records to race conditions.")

if __name__ == "__main__":
    run_benchmark()