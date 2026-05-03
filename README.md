# Google File System (GFS) MVP Implementation

This is a functional implementation of the Google File System architecture, as described in the 2003 GFS paper. The system demonstrates core distributed storage concepts including metadata management, chunk replication, lease-based consistency, fault tolerance, and automatic self-healing.

## Overview

GFS was designed with the assumption that component failures are normal. This implementation runs on a cluster of containerized commodity nodes and handles node failures through automatic re-replication and stale replica repair. The architecture separates the control plane (Python Master) from the data plane (C++ Chunkservers), allowing metadata management to be centralized while data streaming occurs directly between clients and storage nodes.

## System Architecture

This implementation uses a containerized microservices architecture with gRPC for communication:

Master (Python):
  - Manages all filesystem metadata in memory, backed by a write-ahead log (oplog)
  - Grants leases to primary chunkservers for consistent mutation ordering
  - Monitors chunkserver health via heartbeats (15-second timeout)
  - Detects replica failures and triggers automatic re-replication
  - Performs lazy garbage collection of deleted files

Chunkservers (C++):
  - Store 64MB chunks on local disk
  - Handle data streaming and pipelined writes
  - Implement per-chunk locking for concurrent mutation serialization
  - Perform checksums and verify data integrity

Client (Python):
  - Provides application-level API for file operations
  - Caches metadata to reduce Master load
  - Streams data directly to/from chunkservers

## Core Mechanisms

### Read Path
1. The Client asks the Master for the chunk locations of a specific file.
2. The Master replies with the replica addresses.
3. The Client caches metadata and reads directly from any replica.

### Write Path
1. The Client asks the Master to allocate a new chunk or find the last chunk of a file.
2. The Master grants a primary lease to one chunkserver.
3. The client pushes data to all replicas in a pipeline (primary forwards to secondaries).
4. The primary commits the data when all replicas acknowledge buffering.
5. The primary commands secondaries to commit with the same serial number for consistency.

### Atomic Record Append
Multiple clients can concurrently append to the same file. The primary chunkserver serializes appends using per-chunk mutex locks, ensuring atomicity without client-side coordination.

### Fault Tolerance
- The master monitors heartbeats from each chunkserver (expected every 5 seconds, timeout at 15 seconds)
- Dead chunkservers are removed from all replica lists
- Under-replicated chunks are re-replicated to healthy nodes
- Stale replicas (version mismatch) are repaired by cloning from healthy sources

### Garbage Collection
Deleted files are soft-deleted (renamed to hidden namespace) and later permanently deleted lazily in the background.
## Directory Structure

```text
Google-File-System/
├── benchmarks/
│   ├── bench_append.py       # Concurrent append stress test
│   ├── bench_fault.py        # Server failure and re-replication test
│   ├── bench_stale_repair.py # Stale replica detection and repair test
│   └── test_e2e.py           # Basic end-to-end pipeline test
├── chunkserver/
│   ├── CMakeLists.txt
│   ├── main.cpp              # C++ gRPC service implementation
│   ├── storage.h/cpp         # Chunk storage and version tracking
│   ├── heartbeat.h/cpp       # Heartbeat sender
│   ├── checksum.h/cpp        # Checksum computation
│   └── buffer.h/cpp          # Write buffer for pipelined data
├── proto/
│   ├── master.proto          # Master service definitions
│   └── chunk.proto           # Chunkserver service definitions
├── client/
│   ├── gfs_client.py         # Client library and API
│   ├── pipeline.py           # Write pipeline implementation
│   └── cache.py              # Metadata cache
├── docker/
│   ├── docker-compose.yml    # Topology: 1 Master, 4 Chunkservers
│   ├── Dockerfile.chunkserver
│   └── Dockerfile.master
├── master/
│   ├── server.py             # Master gRPC service
│   ├── metadata.py           # Metadata store and file namespace
│   ├── garbage_collection.py # Soft-delete and background cleanup
│   ├── heartbeat.py          # Heartbeat monitor
│   ├── replication.py        # Self-healing clone orchestration
│   ├── lease.py              # Primary lease management
│   └── oplog.py              # Write-ahead log
└── README.md
```

## Setup and Running

### Prerequisites

- Docker and Docker Compose

### Starting the Cluster

Build and start the cluster (1 Master + 4 Chunkservers):

```bash
cd docker
sudo docker compose up --build -d
```

Verify all containers are running:

```bash
sudo docker ps
```

Expected output: docker-master-1, docker-chunkserver1-1, docker-chunkserver2-1, docker-chunkserver3-1, docker-chunkserver4-1.

View cluster logs:

```bash
sudo docker compose logs -f
```

### Running the Automated Tests

Tests are run inside the master container to ensure proper DNS resolution and cluster connectivity.

#### Test 1: End-to-End Pipeline (test_e2e.py)

Validates basic read/write functionality. Creates a file, writes data, and verifies the payload is read back correctly.

```bash
sudo docker exec -it $(sudo docker ps -qf "name=master") python benchmarks/test_e2e.py
```

#### Test 2: Concurrent Atomic Appends (bench_append.py)

Tests atomicity under concurrent load. Spawns 10 concurrent client threads appending records to the same file. Verifies no data loss or corruption due to race conditions.

```bash
sudo docker exec -it $(sudo docker ps -qf "name=master") python benchmarks/bench_append.py
```

#### Test 3: Server Failure and Re-replication (bench_fault.py)

Tests fault tolerance. Writes data to the cluster, then prompts you to manually stop one chunkserver. The test monitors as the master detects the failure and re-replicates data to a spare node. Verifies data integrity after recovery.

```bash
sudo docker exec -it $(sudo docker ps -qf "name=master") python benchmarks/bench_fault.py
```

When prompted, in a separate terminal:

```bash
sudo docker stop docker-chunkserver1-1
```

Then after the test indicates to restart:

```bash
sudo docker start docker-chunkserver1-1
```

#### Test 4: Stale Replica Detection and Repair (bench_stale_repair.py)

Tests stale replica handling. Writes initial data to establish replicas, then stops one replica. While it is down, additional writes advance the chunk version on the remaining replicas. When the stopped replica is restarted, it comes back alive but stale. The master automatically detects the version mismatch and clones the updated data from a healthy replica.

```bash
sudo docker exec -it $(sudo docker ps -qf "name=master") python benchmarks/bench_stale_repair.py
```

Follow on-screen prompts to stop and start chunkserver1. To observe the master's stale replica list in real-time, open a separate terminal and tail:

```bash
sudo docker logs -f docker-master-1 | grep --line-buffered '\[DEBUG\] Chunk'
```

### Manual Testing

For interactive exploration of the system, you can start a Python shell inside the master container and use the GFS client directly.

```bash
sudo docker exec -it $(sudo docker ps -qf "name=master") python
```

Then in the Python REPL:

```python
from client.gfs_client import GFSClient
import time

# Connect to the master
client = GFSClient(master_addr='localhost:50051')

# Create a file
client.create_file('/test.txt')
time.sleep(6)  # Wait for heartbeats to propagate

# Write data
data = b'Hello, GFS!'
client.write('/test.txt', 0, data)

# Read it back
result = client.read('/test.txt', 0, len(data))
print(result)  # Should print: b'Hello, GFS!'

# Append records
client.record_append('/test.txt', b'Appended record 1')
client.record_append('/test.txt', b'Appended record 2')

# Read the appended data
appended = client.read('/test.txt', 0, 100)
print(appended)
```

To monitor master activity while running manual commands:

```bash
sudo docker logs -f docker-master-1
```

To stop the cluster and clean up volumes:

```bash
cd docker
sudo docker compose down -v
```

## Implementation Notes

### Chunk Versioning

Each chunk has an associated version number maintained by the master. When a lease is granted, the version is incremented. All replicas report their known version in heartbeats. Replicas whose reported version differs from the master's authoritative version are marked stale and scheduled for repair.

### Write Consistency

Writes are pipelined: the client sends data to the primary, which forwards to secondaries in order. Once all nodes acknowledge buffering, the client sends a commit RPC to the primary with a serial number. The primary commits to disk and commands secondaries to do the same, ensuring all replicas apply writes in the same order.

### Heartbeat-Based Detection

The heartbeat protocol uses a 5-second interval and 15-second timeout. Each heartbeat includes the chunkserver's address and all chunk handles and versions it currently stores. The master uses this information to detect failures, identify under-replicated chunks, and detect stale replicas.

### Re-replication and Stale Repair

When a chunkserver dies, the master removes it from all replicas and enqueues under-replicated chunks for cloning. When a stale replica is detected (version mismatch), it is enqueued for repair and a healthy replica is cloned to the stale node using the CopyChunkTo RPC.

## Configuration

Key constants are defined in the code:

- Chunk size: 64 MB
- Replication factor: 3
- Heartbeat interval: 5 seconds
- Heartbeat timeout: 15 seconds
- Lease duration: 60 seconds
- Max append size: 16 MB (1/4 of chunk)

These values can be modified in the respective source files and the Docker images rebuilt.

## Codebase Overview

**benchmarks/:** Integration test suite covering pipelines, concurrency, fault tolerance, and self-healing.

**chunkserver/:** C++ implementation of the storage nodes. Handles RPC endpoints for read, write, append, and copy operations; maintains per-chunk locking and checksums.

**client/:** Python client library with metadata caching and pipelined write implementation.

**master/:** Python implementation of the master server, metadata store, heartbeat monitor, lease manager, replication orchestrator, and garbage collector.

**proto/:** Protocol buffer definitions for gRPC services.

**docker/:** Docker configuration and build files.

## References

Ghemawat, S., Gobioff, H., & Leung, S. T. (2003). "The Google File System." Proceedings of the 19th ACM Symposium on Operating Systems Principles.