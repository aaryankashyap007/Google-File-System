# Google File System (GFS) MVP Replica

A highly concurrent, fault-tolerant distributed file system inspired by the original 2003 Google File System paper. This project implements the core architecture of GFS, featuring a decoupled control plane and a high-performance data plane to handle massive parallel workloads.

## 🏗️ Architecture

This implementation utilizes a containerized microservices architecture communicating via **gRPC**:

* **The Master (Python):** The brain of the cluster. Maintains all filesystem metadata, manages access control, grants primary chunk leases, monitors Chunkserver health via 15-second heartbeats, and orchestrates lazy garbage collection and re-replication. Metadata is kept entirely in RAM for speed, backed by a Write-Ahead Log (Oplog).
* **The Chunkservers (C++):** High-performance storage nodes that store physical 64MB chunks on local disk. They handle the heavy lifting of data streaming, concurrent mutation locking, and checksum verification.
* **The Client (Python):** A smart library embedded in user applications that caches metadata to minimize Master bottlenecking and streams data directly to/from Chunkservers.

## ✨ Implemented Features

This MVP faithfully reproduces the hardest distributed systems problems solved in the original GFS paper:

1. **Decoupled Data Flow:** Clients get metadata from the Master but stream physical data directly to Chunkservers.
2. **Write Pipelining & Leases:** The Master grants a "Primary Lease" to one chunkserver. The client pushes data to all replicas over a TCP pipeline, and the Primary dictates the serial write order to guarantee consistency.
3. **Atomic Record Append:** Solves the "multiple concurrent writers" problem. Concurrent clients can blast data at the same file simultaneously; the Primary uses strict per-chunk mutex locks to serialize the appends, guaranteeing at-least-once atomic insertion without client-side locking.
4. **Fault Tolerance & Self-Healing:** The Master monitors heartbeats. If a Chunkserver dies, the Master instantly evicts it, identifies under-replicated chunks, and commands surviving nodes to clone data to empty spare nodes.
5. **Lazy Garbage Collection:** Files are soft-deleted and hidden. A background thread securely wipes orphaned metadata and commands Chunkservers to delete physical data during off-peak heartbeats.

## 📂 File Structure
```text
Google-File-System/
├── benchmarks/
│   ├── bench_append.py       # Stress tests concurrent atomic record appends
│   ├── bench_fault.py        # Chaos Monkey test for re-replication
│   └── test_e2e.py           # Validates pipeline and client cache
├── chunkserver/
│   ├── CMakeLists.txt
│   ├── main.cpp              # C++ gRPC Server, Locking, and Checksums
│   └── protos/               # .proto definitions for Chunk/Master comms
├── client/
│   ├── gfs_client.py         # Client API and cache management
│   └── pipeline.py           # Network pipeline for chunk streaming
├── docker/
│   ├── docker-compose.yml    # Topology: 1 Master, 4 Chunkservers
│   ├── Dockerfile.chunkserver
│   └── Dockerfile.master
├── master/
│   ├── garbage_collection.py # Soft-delete and background cleanup
│   ├── replication.py        # Self-healing clone orchestration
│   └── server.py             # Python gRPC Server and lease management
└── README.md
```

## 🚀 Getting Started

### Prerequisites
* Docker
* Docker Compose
* Python 3.10+ (for running scripts locally, though tests can be run seamlessly inside the containers)

### 1. Boot the Cluster
The cluster consists of 1 Master and 4 C++ Chunkservers (3 active, 1 spare for self-healing).
```bash
sudo docker-compose -f docker/docker-compose.yml up --build -d
```
*(To view the cluster's internal logs, run: `sudo docker-compose -f docker/docker-compose.yml logs -f`)*

### 2. Run the Test Suite
The project includes three major integration benchmarks. Because the Docker network uses internal DNS resolution, the easiest way to run these tests is by executing them *inside* the Master container.

#### Test A: The Read/Write Pipeline
Validates file creation, chunk allocation, data pipelining, and client-side metadata caching.
```bash
sudo docker exec -it $(sudo docker ps -qf "name=master") python benchmarks/test_e2e.py
```

#### Test B: Concurrency & Atomic Record Appends
Spawns 10 concurrent threads that simultaneously blast records at the exact same file. Validates that the C++ Primary Chunkserver correctly locks and serializes the writes, preventing data corruption or race conditions.
```bash
sudo docker exec -it $(sudo docker ps -qf "name=master") python benchmarks/bench_append.py
```

#### Test C: The Chaos Monkey (Fault Tolerance)
The ultimate test. The client writes a 3MB payload to the cluster. The script will pause and prompt you to manually kill one of the Docker chunkservers hosting the data. Once killed, you will watch the Master detect the heartbeat timeout, evict the node, and trigger the Replication Manager to clone the data to the 4th spare chunkserver.
```bash
sudo docker exec -it $(sudo docker ps -qf "name=master") python benchmarks/bench_fault.py
```

### 3. Teardown
To cleanly shut down the cluster and wipe the persistent storage volumes:
```bash
sudo docker-compose -f docker/docker-compose.yml down -v
```