# 📁 GFS — Mini Google File System
### Distributed Systems Project · Team: Eventually Consistent

> A scaled-down replica of the [Google File System (2003)](https://static.googleusercontent.com/media/research.google.com/en//archive/gfs-sosp2003.pdf).  
> Built with **Python** (master + client) · **C++** (chunkserver) · **gRPC** (RPC layer) · **Docker** (cluster simulation)

---

## 👥 Team

| Name | Roll Number |
|---|---|
| Aaryan Kashyap | 2023114006 |
| Amisha | 2023114003 |
| Agrim Mittal | 2022101040 |

---

## 📋 Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Repository Structure](#repository-structure)
3. [How to Use This README (For Contributors)](#how-to-use-this-readme-for-contributors)
4. [Implementation Roadmap](#implementation-roadmap)
   - [Phase 0 — Setup & Scaffolding](#phase-0--setup--scaffolding)
   - [Phase 1 — Master Node](#phase-1--master-node)
   - [Phase 2 — Chunkserver](#phase-2--chunkserver)
   - [Phase 3 — Write Pipeline & Leases](#phase-3--write-pipeline--leases)
   - [Phase 4 — Read Path](#phase-4--read-path)
   - [Phase 5 — Atomic Record Append](#phase-5--atomic-record-append)
   - [Phase 6 — Fault Tolerance](#phase-6--fault-tolerance)
   - [Phase 7 — Benchmarking Suite](#phase-7--benchmarking-suite)
5. [Running the Project](#running-the-project)
6. [Feature Checklist](#feature-checklist)
7. [Weekly Timeline](#weekly-timeline)

---

## Architecture Overview

```
                  ┌─────────────────────────────────────────────┐
                  │             GFS CLUSTER                     │
                  │                                             │
   ┌──────────┐   │   ┌─────────────┐    heartbeat    ┌──────┐  │
   │          │──────▶│             │◀───────────────▶│ CS 1 │  │
   │  Client  │   │   │   Master    │                 └──────┘  │
   │ (Python) │   │   │  (Python)   │    heartbeat    ┌──────┐  │
   │          │◀──────│             │◀───────────────▶│ CS 2 │  │
   └────┬─────┘   │   └─────────────┘                 └──────┘  │
        │         │    ▲  metadata only                ┌──────┐  │
        │         │    │                  heartbeat   │ CS 3 │  │
        │         │    │               ◀─────────────▶└──────┘  │
        │         │    │                                         │
        │ (1) ask │    │  (2) get chunk locations                │
        │ master  │    │                                         │
        │─────────┘    │                                         │
        │              │                                         │
        │  (3) read/write DIRECTLY to chunkservers (data flow)   │
        └────────────────────────────────────────────────────────┘

Control flow  ─────▶   (always through master)
Data flow     ══════▶   (always direct client ↔ chunkserver)
```

**Key principle:** The master handles **only metadata**. All actual file data flows directly between the client and chunkservers. This is what makes GFS scalable.

---

## Repository Structure

```
gfs/
├── proto/                        # gRPC service definitions (shared)
│   ├── master.proto              # MasterService RPC contracts
│   └── chunk.proto               # ChunkService RPC contracts
│
├── master/                       # Master node (Python)
│   ├── server.py                 # gRPC server entrypoint
│   ├── metadata.py               # In-memory namespace + chunk map
│   ├── oplog.py                  # Write-ahead log + checkpointing
│   ├── lease.py                  # Lease grant/revoke/expiry logic
│   ├── heartbeat.py              # Chunkserver health monitoring
│   ├── replication.py            # Re-replication + stale detection
│   └── gc.py                     # Lazy garbage collection
│
├── chunkserver/                  # Chunkserver (C++)
│   ├── main.cpp                  # gRPC server entrypoint
│   ├── storage.cpp / .h          # Chunk read/write to disk
│   ├── checksum.cpp / .h         # 64KB block checksumming
│   ├── buffer.cpp / .h           # LRU write buffer
│   └── heartbeat.cpp / .h        # Heartbeat loop to master
│
├── client/                       # Client library (Python)
│   ├── gfs_client.py             # Public API (read, write, append)
│   ├── cache.py                  # Chunk location cache (with TTL)
│   └── pipeline.py               # Pipelined data push to replicas
│
├── benchmarks/                   # Benchmarking suite (Python)
│   ├── bench_read.py             # Concurrent read throughput
│   ├── bench_write.py            # Concurrent write throughput
│   ├── bench_append.py           # Concurrent record append
│   └── bench_fault.py            # Fault injection + recovery timing
│
├── docker/
│   ├── docker-compose.yml        # Spin up master + N chunkservers
│   ├── Dockerfile.master
│   ├── Dockerfile.chunkserver
│   └── Dockerfile.client
│
└── tests/
    ├── test_master.py
    ├── test_chunkserver.py
    ├── test_client.py
    └── test_e2e.py               # End-to-end integration tests
```

---

## How to Use This README (For Contributors)

**We work sequentially through phases.** Before starting any phase, check the latest commit message and the [Feature Checklist](#feature-checklist) to know exactly where we left off.

**Commit message convention:**
```
[PHASE-X] Short description of what was completed

Example:
[PHASE-1] Master metadata store + namespace locking done
[PHASE-2] Chunkserver read/write RPCs + checksum verification
[PHASE-3] Write pipeline 7-step flow + lease management
```

**Branch convention:**
```
phase/0-setup
phase/1-master
phase/2-chunkserver
phase/3-write-pipeline
... etc.
```

**Before picking up work:**
1. Pull latest from `main`
2. Read the last 3–5 commit messages
3. Check which checkboxes are ticked in the [Feature Checklist](#feature-checklist)
4. Start from the first unchecked item in the current phase

---

## Implementation Roadmap

---

### Phase 0 — Setup & Scaffolding

**Owner:** Any team member  
**Goal:** Get the repo, toolchain, and communication layer working so everyone can build in parallel.

---

#### Step 0.1 — Create repo structure

Create all directories listed in [Repository Structure](#repository-structure). Add a `.gitkeep` to empty folders so they are tracked by git.

```bash
mkdir -p proto master chunkserver client benchmarks docker tests
```

---

#### Step 0.2 — Write Protobuf contracts

Create `proto/master.proto` and `proto/chunk.proto`. These define all RPCs before any code is written. **Both files must be agreed upon by the team before Phase 1 begins.**

**`proto/master.proto`** — services the master exposes:

```protobuf
syntax = "proto3";
package gfs;

service MasterService {
  rpc CreateFile    (CreateFileRequest)     returns (CreateFileResponse);
  rpc OpenFile      (OpenFileRequest)       returns (OpenFileResponse);
  rpc GetChunkLocations (ChunkLocRequest)   returns (ChunkLocResponse);
  rpc ReportChunk   (ReportChunkRequest)    returns (ReportChunkResponse);
  rpc HeartBeat     (HeartBeatRequest)      returns (HeartBeatResponse);
  rpc DeleteFile    (DeleteFileRequest)     returns (DeleteFileResponse);
}

message ChunkLocRequest {
  string filename = 1;
  int32  chunk_index = 2;
  bool   create_if_missing = 3;
}

message ChunkLocResponse {
  int64  chunk_handle = 1;
  string primary_address = 2;
  repeated string secondary_addresses = 3;
  int32  chunk_version = 4;
}

message HeartBeatRequest {
  string chunkserver_address = 1;
  repeated int64 chunk_handles = 2;
  repeated int32 chunk_versions = 3;
}

message HeartBeatResponse {
  repeated int64 chunks_to_delete = 1;
}
// ... (define remaining messages similarly)
```

**`proto/chunk.proto`** — services each chunkserver exposes:

```protobuf
syntax = "proto3";
package gfs;

service ChunkService {
  rpc ReadChunk    (ReadRequest)    returns (ReadResponse);
  rpc WriteChunk   (WriteRequest)   returns (WriteResponse);
  rpc AppendChunk  (AppendRequest)  returns (AppendResponse);
  rpc DeleteChunk  (DeleteRequest)  returns (DeleteResponse);
  rpc ForwardWrite (WriteRequest)   returns (WriteResponse); // pipeline forwarding
}

message ReadRequest {
  int64  chunk_handle = 1;
  int32  offset = 2;
  int32  length = 3;
  int32  chunk_version = 4;
}

message ReadResponse {
  bytes  data = 1;
  bool   checksum_ok = 2;
}

message WriteRequest {
  int64          chunk_handle = 1;
  int32          offset = 2;
  bytes          data = 3;
  int32          serial_number = 4;
  repeated string forward_to = 5;   // pipeline: next chunkservers to forward to
}
// ... (define remaining messages similarly)
```

After writing protos, generate stubs:

```bash
# Python stubs (for master + client)
python -m grpc_tools.protoc -I./proto \
  --python_out=./master --grpc_python_out=./master ./proto/master.proto

# C++ stubs (for chunkserver)
protoc -I./proto --cpp_out=./chunkserver \
  --grpc_out=./chunkserver \
  --plugin=protoc-gen-grpc=`which grpc_cpp_plugin` ./proto/chunk.proto
```

---

#### Step 0.3 — Docker Compose setup

Create `docker/docker-compose.yml` to simulate the cluster locally:

```yaml
version: '3.8'
services:
  master:
    build:
      context: ..
      dockerfile: docker/Dockerfile.master
    ports:
      - "50051:50051"
    volumes:
      - master_data:/data
    environment:
      - GFS_MASTER_PORT=50051
      - GFS_LOG_DIR=/data/oplog

  chunkserver1:
    build:
      context: ..
      dockerfile: docker/Dockerfile.chunkserver
    environment:
      - GFS_MASTER_ADDR=master:50051
      - GFS_CS_PORT=50052
      - GFS_DATA_DIR=/chunks
    volumes:
      - cs1_data:/chunks

  chunkserver2:
    build:
      context: ..
      dockerfile: docker/Dockerfile.chunkserver
    environment:
      - GFS_MASTER_ADDR=master:50051
      - GFS_CS_PORT=50053
      - GFS_DATA_DIR=/chunks
    volumes:
      - cs2_data:/chunks

  chunkserver3:
    build:
      context: ..
      dockerfile: docker/Dockerfile.chunkserver
    environment:
      - GFS_MASTER_ADDR=master:50051
      - GFS_CS_PORT=50054
      - GFS_DATA_DIR=/chunks
    volumes:
      - cs3_data:/chunks

volumes:
  master_data:
  cs1_data:
  cs2_data:
  cs3_data:
```

**Verify:** `docker-compose up --build` should start all 4 containers without errors (even if RPCs are not yet implemented, the processes should start).

---

### Phase 1 — Master Node

**Owner:** Aaryan (suggested — reassign as needed)  
**Depends on:** Phase 0 complete  
**Goal:** A fully working master that manages metadata, survives crashes, and coordinates chunkservers.

---

#### Step 1.1 — In-memory metadata store (`master/metadata.py`)

The master holds **three** data structures in memory:

```python
# master/metadata.py

class MetadataStore:
    def __init__(self):
        # Map: filepath (str) -> FileMetadata
        self.namespace: dict[str, FileMetadata] = {}

        # Map: filepath (str) -> list of chunk handles (int)
        self.file_chunks: dict[str, list[int]] = {}

        # Map: chunk_handle (int) -> ChunkMetadata
        self.chunk_map: dict[int, ChunkMetadata] = {}

        # Chunk version tracking: chunk_handle -> version number
        self.chunk_versions: dict[int, int] = {}

        # Next chunk handle (monotonically increasing)
        self._next_handle: int = 1

        # Namespace read-write locks
        self._locks: dict[str, threading.RWLock] = {}

    def allocate_chunk(self, filepath: str) -> int:
        """Allocate a new chunk handle and add it to the file's chunk list."""
        handle = self._next_handle
        self._next_handle += 1
        self.file_chunks[filepath].append(handle)
        self.chunk_map[handle] = ChunkMetadata(handle=handle, replicas=[])
        self.chunk_versions[handle] = 0
        return handle
```

```python
@dataclass
class FileMetadata:
    path: str
    created_at: float
    deleted: bool = False
    deleted_at: float | None = None    # set when file is "soft deleted"
    hidden_name: str | None = None     # e.g. "/.trash/foo_1712345678"

@dataclass
class ChunkMetadata:
    handle: int
    replicas: list[str]                # list of chunkserver addresses
    primary: str | None = None         # current lease holder
    lease_expiry: float = 0.0          # unix timestamp
```

**Important:** Chunk location info (the `replicas` field) is **never persisted to disk**. It is always rebuilt from chunkserver heartbeats on startup. Only the namespace and file-to-chunk mapping need to survive crashes (via the op-log).

---

#### Step 1.2 — Write-ahead operation log (`master/oplog.py`)

Every mutation to the namespace or chunk mapping must be durably logged **before** the master replies to any client.

```python
# master/oplog.py
import json, os, time

class OperationLog:
    def __init__(self, log_path: str):
        self.log_path = log_path
        self._fh = open(log_path, 'a')   # append-only

    def append(self, op_type: str, payload: dict):
        """Write a log record and flush to disk before returning."""
        record = json.dumps({"ts": time.time(), "op": op_type, **payload})
        self._fh.write(record + "\n")
        self._fh.flush()
        os.fsync(self._fh.fileno())       # ← critical: force to disk

    def replay(self) -> list[dict]:
        """Read all log records. Called on master startup."""
        records = []
        try:
            with open(self.log_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        except FileNotFoundError:
            pass
        return records
```

**Op types to log:** `CREATE_FILE`, `DELETE_FILE`, `ALLOCATE_CHUNK`, `INCREMENT_CHUNK_VERSION`.

---

#### Step 1.3 — Checkpointing (`master/oplog.py` continued)

Once the log grows large, replaying it takes time. Add checkpointing so the master only replays recent records.

```python
import pickle

class OperationLog:
    # ... (continued from above)

    def write_checkpoint(self, metadata_store):
        """Serialize full metadata state to a checkpoint file."""
        cp_path = self.log_path + ".checkpoint"
        tmp_path = cp_path + ".tmp"
        with open(tmp_path, 'wb') as f:
            pickle.dump({
                "namespace":    metadata_store.namespace,
                "file_chunks":  metadata_store.file_chunks,
                "chunk_map":    metadata_store.chunk_map,
                "chunk_versions": metadata_store.chunk_versions,
                "next_handle":  metadata_store._next_handle,
            }, f)
        os.rename(tmp_path, cp_path)         # atomic replace
        # truncate log — only records AFTER this checkpoint are needed
        self._fh.close()
        open(self.log_path, 'w').close()     # clear log
        self._fh = open(self.log_path, 'a')

    def load_checkpoint(self) -> dict | None:
        cp_path = self.log_path + ".checkpoint"
        try:
            with open(cp_path, 'rb') as f:
                return pickle.load(f)
        except FileNotFoundError:
            return None
```

**Trigger checkpointing** when the log exceeds ~1000 records (configurable). Run it in a background thread to avoid blocking client requests.

---

#### Step 1.4 — Namespace locking (`master/metadata.py`)

Prevent races between concurrent operations (e.g., a file being created while its parent directory is being snapshotted).

Each operation acquires **read locks on all parent directory components** and a **write lock on the leaf** (the final file or directory name).

```python
import threading

class NamespaceLockManager:
    def __init__(self):
        self._locks: dict[str, threading.RLock] = {}
        self._meta_lock = threading.Lock()

    def _get_lock(self, path_component: str) -> threading.RLock:
        with self._meta_lock:
            if path_component not in self._locks:
                self._locks[path_component] = threading.RLock()
            return self._locks[path_component]

    def acquire_for_operation(self, filepath: str, write: bool = True):
        """
        Acquire read locks on all parent components,
        write lock on the leaf component.
        Example: /home/user/foo
          → read lock on '/home', '/home/user'
          → write lock on '/home/user/foo'
        """
        parts = filepath.split('/')
        path = ''
        acquired = []
        for i, part in enumerate(parts):
            if not part:
                continue
            path = path + '/' + part
            lock = self._get_lock(path)
            is_leaf = (i == len(parts) - 1)
            lock.acquire()         # simplified: use rwlock library for true R/W
            acquired.append(lock)
        return acquired            # caller must release all on completion
```

---

#### Step 1.5 — HeartBeat handler (`master/heartbeat.py`)

The master tracks which chunkservers are alive and what chunks they hold.

```python
# master/heartbeat.py
import time, threading

HEARTBEAT_INTERVAL = 5       # seconds between expected heartbeats
HEARTBEAT_TIMEOUT  = 15      # seconds before a chunkserver is considered dead

class HeartbeatMonitor:
    def __init__(self, metadata_store, replication_manager):
        self.store = metadata_store
        self.repl  = replication_manager
        self._last_seen: dict[str, float] = {}   # addr -> timestamp
        self._lock = threading.Lock()

    def handle_heartbeat(self, cs_address: str,
                         chunk_handles: list[int],
                         chunk_versions: list[int]):
        """Called by the gRPC handler when a heartbeat arrives."""
        with self._lock:
            self._last_seen[cs_address] = time.time()

        # Update replica list for each reported chunk
        for handle, version in zip(chunk_handles, chunk_versions):
            if handle not in self.store.chunk_map:
                continue   # unknown chunk — will be GC'd later
            master_version = self.store.chunk_versions.get(handle, 0)
            if version < master_version:
                # stale replica — do not add to active replicas
                self.store.chunk_map[handle].stale_replicas.append(cs_address)
            else:
                if cs_address not in self.store.chunk_map[handle].replicas:
                    self.store.chunk_map[handle].replicas.append(cs_address)

        # Return list of chunks this chunkserver should delete (GC)
        return self._get_chunks_to_delete(cs_address)

    def check_dead_servers(self):
        """Run in background thread. Detects failed chunkservers."""
        while True:
            time.sleep(HEARTBEAT_INTERVAL)
            now = time.time()
            with self._lock:
                for addr, last in list(self._last_seen.items()):
                    if now - last > HEARTBEAT_TIMEOUT:
                        self._handle_chunkserver_failure(addr)

    def _handle_chunkserver_failure(self, cs_address: str):
        """Remove dead server from all replica lists, trigger re-replication."""
        for chunk_meta in self.store.chunk_map.values():
            if cs_address in chunk_meta.replicas:
                chunk_meta.replicas.remove(cs_address)
                # if below replication threshold, enqueue for re-replication
                if len(chunk_meta.replicas) < 3:
                    self.repl.enqueue(chunk_meta.handle, priority='high')
        del self._last_seen[cs_address]
```

---

#### Step 1.6 — Master gRPC server (`master/server.py`)

Wire everything together into a gRPC servicer. This is where all the above components are instantiated and connected.

```python
# master/server.py
import grpc, concurrent.futures
from generated import master_pb2_grpc, master_pb2

class MasterServicer(master_pb2_grpc.MasterServiceServicer):
    def __init__(self):
        self.store     = MetadataStore()
        self.oplog     = OperationLog('/data/oplog/gfs.log')
        self.locks     = NamespaceLockManager()
        self.heartbeat = HeartbeatMonitor(self.store, ...)
        self._restore_state()
        threading.Thread(target=self.heartbeat.check_dead_servers, daemon=True).start()

    def _restore_state(self):
        """On startup: load checkpoint, then replay any subsequent log records."""
        cp = self.oplog.load_checkpoint()
        if cp:
            self.store.namespace      = cp['namespace']
            self.store.file_chunks    = cp['file_chunks']
            self.store.chunk_map      = cp['chunk_map']
            self.store.chunk_versions = cp['chunk_versions']
            self.store._next_handle   = cp['next_handle']
        for record in self.oplog.replay():
            self._apply_log_record(record)   # re-apply operations on top

    def GetChunkLocations(self, request, context):
        # 1. look up file in namespace
        # 2. find the chunk_handle for request.chunk_index
        # 3. look up replicas for that handle
        # 4. determine primary (who holds current lease)
        # 5. return ChunkLocResponse
        ...

    def HeartBeat(self, request, context):
        chunks_to_delete = self.heartbeat.handle_heartbeat(
            request.chunkserver_address,
            list(request.chunk_handles),
            list(request.chunk_versions)
        )
        return master_pb2.HeartBeatResponse(chunks_to_delete=chunks_to_delete)
```

**Test for Phase 1:** Start the master, connect a basic Python gRPC client, call `CreateFile` and `GetChunkLocations`. Kill the master process and restart it — verify the file is still visible and chunk mappings are intact (replayed from log).

---

### Phase 2 — Chunkserver

**Owner:** Agrim (suggested — reassign as needed)  
**Depends on:** Phase 0 complete (protos generated, Docker working)  
**Goal:** A chunkserver that stores chunks durably, verifies checksums, and registers with the master.

---

#### Step 2.1 — Chunk storage (`chunkserver/storage.cpp`)

Each chunk is a file on disk named by its handle. Use a flat directory (no subdirectories needed).

```cpp
// chunkserver/storage.h
#pragma once
#include <string>
#include <vector>
#include <cstdint>

class ChunkStorage {
public:
    explicit ChunkStorage(const std::string& data_dir);

    // Read `length` bytes from chunk at `offset`. Returns data or throws.
    std::vector<uint8_t> read(int64_t handle, int32_t offset, int32_t length);

    // Write `data` to chunk at `offset`. Creates chunk file if missing.
    void write(int64_t handle, int32_t offset, const std::vector<uint8_t>& data);

    // Append `data` to the end of a chunk. Returns the offset written at.
    int32_t append(int64_t handle, const std::vector<uint8_t>& data);

    // Delete a chunk file from disk.
    void remove(int64_t handle);

    // Return all chunk handles currently on disk.
    std::vector<int64_t> list_all();

    // Return size of chunk in bytes.
    int32_t get_size(int64_t handle);

private:
    std::string data_dir_;
    std::string chunk_path(int64_t handle) const;   // e.g. /chunks/chunk_0000042.bin
};
```

Constants:
```cpp
static constexpr int64_t CHUNK_SIZE_BYTES = 64 * 1024 * 1024;  // 64 MB
static constexpr int32_t BLOCK_SIZE_BYTES = 64 * 1024;         // 64 KB (for checksums)
```

---

#### Step 2.2 — Checksumming (`chunkserver/checksum.cpp`)

Every chunk is divided into 64 KB blocks. Each block has a 32-bit CRC32 checksum stored in a separate sidecar file (e.g., `chunk_0000042.checksum`).

```cpp
// chunkserver/checksum.h
#pragma once
#include <vector>
#include <cstdint>
#include <string>

class ChecksumStore {
public:
    explicit ChecksumStore(const std::string& data_dir);

    // Compute CRC32 of a data block
    static uint32_t compute(const std::vector<uint8_t>& data);

    // Update checksum for the block at block_index after a write
    void update(int64_t handle, int32_t block_index, uint32_t checksum);

    // Verify a block's data against stored checksum. Returns false on mismatch.
    bool verify(int64_t handle, int32_t block_index,
                const std::vector<uint8_t>& block_data);

    // Load all checksums for a chunk into memory
    std::vector<uint32_t> load(int64_t handle);

    // Save all checksums for a chunk to disk
    void save(int64_t handle, const std::vector<uint32_t>& checksums);
};
```

**On every read:** before returning data to the caller, call `checksum_store.verify()` for each 64 KB block in the requested range. If verification fails:
1. Log the corruption event.
2. Return an error response (do NOT return corrupt data).
3. Report the bad chunk to the master via a separate RPC so the master can re-replicate it.

**On every write/append:** recompute and update the checksum for any modified block.

---

#### Step 2.3 — LRU write buffer (`chunkserver/buffer.cpp`)

Data for a pending write is stored in memory first before being committed. This is necessary because in the 7-step write pipeline, all replicas receive the data _before_ any of them commit it to disk.

```cpp
// chunkserver/buffer.h
#include <unordered_map>
#include <list>
#include <mutex>

struct BufferedData {
    int64_t              chunk_handle;
    std::vector<uint8_t> data;
    std::chrono::steady_clock::time_point inserted_at;
};

class WriteBuffer {
public:
    // Store incoming data keyed by (chunk_handle, client_id, serial)
    void put(int64_t chunk_handle, const std::string& key,
             const std::vector<uint8_t>& data);

    // Retrieve and remove buffered data for a commit
    std::vector<uint8_t> take(const std::string& key);

    // Evict entries older than max_age_seconds (background cleanup)
    void evict_stale(int max_age_seconds = 60);

private:
    std::unordered_map<std::string, BufferedData> buffer_;
    std::mutex mutex_;
};
```

---

#### Step 2.4 — Heartbeat loop (`chunkserver/heartbeat.cpp`)

The chunkserver sends a heartbeat to the master every 5 seconds containing all chunk handles it stores.

```cpp
// chunkserver/heartbeat.cpp
void HeartbeatSender::run() {
    while (running_) {
        std::this_thread::sleep_for(std::chrono::seconds(HEARTBEAT_INTERVAL));

        auto handles  = storage_.list_all();
        auto versions = version_store_.get_all_versions();

        HeartBeatRequest req;
        req.set_chunkserver_address(my_address_);
        for (auto h : handles)  req.add_chunk_handles(h);
        for (auto v : versions) req.add_chunk_versions(v);

        HeartBeatResponse resp;
        grpc::ClientContext ctx;
        auto status = master_stub_->HeartBeat(&ctx, req, &resp);

        if (status.ok()) {
            // Master told us to delete these chunks (garbage collection)
            for (auto handle : resp.chunks_to_delete()) {
                storage_.remove(handle);
            }
        }
    }
}
```

---

#### Step 2.5 — ChunkService gRPC server (`chunkserver/main.cpp`)

Wire storage + checksum + buffer into the gRPC servicer:

```cpp
class ChunkServiceImpl final : public ChunkService::Service {
    grpc::Status ReadChunk(grpc::ServerContext* ctx,
                           const ReadRequest* req,
                           ReadResponse* resp) override {
        try {
            auto data = storage_.read(req->chunk_handle(),
                                      req->offset(), req->length());
            // Verify checksum for each block in range
            int start_block = req->offset() / BLOCK_SIZE_BYTES;
            int end_block   = (req->offset() + req->length()) / BLOCK_SIZE_BYTES;
            for (int b = start_block; b <= end_block; ++b) {
                auto block_data = /* slice data for block b */ ;
                if (!checksum_.verify(req->chunk_handle(), b, block_data)) {
                    // Report to master and reject read
                    report_corruption(req->chunk_handle());
                    return grpc::Status(grpc::StatusCode::DATA_LOSS,
                                        "Checksum mismatch on block " + std::to_string(b));
                }
            }
            resp->set_data(std::string(data.begin(), data.end()));
            resp->set_checksum_ok(true);
            return grpc::Status::OK;
        } catch (...) {
            return grpc::Status(grpc::StatusCode::INTERNAL, "Read failed");
        }
    }
    // ... WriteChunk, AppendChunk, DeleteChunk, ForwardWrite
};
```

**Test for Phase 2:** Without a master running, directly call `WriteChunk` and then `ReadChunk` on a chunkserver via grpcurl. Write 1 MB of data, read it back, verify the bytes match. Then corrupt the raw file on disk and confirm the next read returns an error.

---

### Phase 3 — Write Pipeline & Leases

**Owner:** Amisha (suggested — reassign as needed)  
**Depends on:** Phase 1 + Phase 2 complete  
**Goal:** End-to-end writes where data flows correctly through all replicas in the correct order.

---

#### Step 3.1 — Lease management (`master/lease.py`)

A lease grants one replica the role of **primary** for a chunk for a 60-second window. The primary serializes all mutations to that chunk.

```python
# master/lease.py
import time, threading

LEASE_DURATION = 60   # seconds

class LeaseManager:
    def __init__(self, metadata_store):
        self.store = metadata_store
        self._lock = threading.Lock()

    def grant_lease(self, chunk_handle: int) -> str | None:
        """Pick a primary and grant it a lease. Increments chunk version."""
        with self._lock:
            chunk = self.store.chunk_map.get(chunk_handle)
            if not chunk or not chunk.replicas:
                return None

            # Increment version BEFORE notifying replicas
            self.store.chunk_versions[chunk_handle] += 1
            new_version = self.store.chunk_versions[chunk_handle]

            primary = chunk.replicas[0]
            chunk.primary      = primary
            chunk.lease_expiry = time.time() + LEASE_DURATION

            # TODO: notify all up-to-date replicas of new version
            # (in practice done via the next RPC call that carries version)
            return primary

    def has_valid_lease(self, chunk_handle: int) -> bool:
        chunk = self.store.chunk_map.get(chunk_handle)
        if not chunk:
            return False
        return chunk.primary is not None and time.time() < chunk.lease_expiry

    def extend_lease(self, chunk_handle: int):
        """Called when primary requests extension via heartbeat."""
        with self._lock:
            chunk = self.store.chunk_map.get(chunk_handle)
            if chunk and chunk.lease_expiry > time.time():
                chunk.lease_expiry = time.time() + LEASE_DURATION

    def revoke_lease(self, chunk_handle: int):
        """Used before snapshot or rename operations."""
        with self._lock:
            chunk = self.store.chunk_map.get(chunk_handle)
            if chunk:
                chunk.primary      = None
                chunk.lease_expiry = 0.0
```

---

#### Step 3.2 — Client-side write pipeline (`client/pipeline.py`)

This implements the exact 7-step write flow from Figure 2 of the GFS paper.

```python
# client/pipeline.py

class WritePipeline:
    def write(self, filename: str, offset: int, data: bytes):
        # Translate (filename, offset) → (chunk_index, offset_within_chunk)
        chunk_size   = 64 * 1024 * 1024
        chunk_index  = offset // chunk_size
        chunk_offset = offset % chunk_size

        # Step 1 & 2: Ask master for primary + replica locations
        loc = self.master_stub.GetChunkLocations(ChunkLocRequest(
            filename=filename,
            chunk_index=chunk_index,
            create_if_missing=True
        ))
        primary    = loc.primary_address
        secondaries = list(loc.secondary_addresses)
        all_replicas = [primary] + secondaries

        # Step 3: Push data to ALL replicas (pipelined — order doesn't matter)
        # Forward the data in a chain: client → CS1 → CS2 → CS3
        push_req = WriteRequest(
            chunk_handle=loc.chunk_handle,
            offset=chunk_offset,
            data=data,
            forward_to=secondaries[1:] if secondaries else []
        )
        # Send to primary first; primary forwards down the chain
        stub = self._get_chunk_stub(primary)
        stub.ForwardWrite(push_req)    # this just buffers, does not commit

        # Step 4: Send write commit to PRIMARY only
        commit_req = WriteRequest(
            chunk_handle=loc.chunk_handle,
            offset=chunk_offset,
            data=b'',                  # data already in buffer
            serial_number=self._next_serial()
        )
        resp = stub.WriteChunk(commit_req)

        # Step 7: Check for errors
        if not resp.success:
            raise IOError(f"Write failed: {resp.error_message}")
```

---

#### Step 3.3 — Primary commit logic (chunkserver)

When the primary receives a `WriteChunk` RPC (the commit, step 4):

```cpp
grpc::Status WriteChunk(grpc::ServerContext* ctx,
                        const WriteRequest* req,
                        WriteResponse* resp) override {
    // Step 4: Retrieve buffered data
    auto data = buffer_.take(make_key(req->chunk_handle(), req->serial_number()));

    // Assign this write a serial number (primary role)
    int serial = serial_counter_++;

    // Step 5: Forward write to ALL secondaries in serial order
    for (const auto& secondary_addr : secondary_addresses_for(req->chunk_handle())) {
        auto sec_stub = get_stub(secondary_addr);
        WriteRequest fwd;
        fwd.set_chunk_handle(req->chunk_handle());
        fwd.set_offset(req->offset());
        fwd.set_data(std::string(data.begin(), data.end()));
        fwd.set_serial_number(serial);
        WriteResponse sec_resp;
        grpc::ClientContext fwd_ctx;
        sec_stub->WriteChunk(&fwd_ctx, fwd, &sec_resp);  // Step 5
        // Step 6: wait for ack from each secondary
    }

    // Apply locally
    storage_.write(req->chunk_handle(), req->offset(), data);
    checksum_.update(req->chunk_handle(), block_index(req->offset()),
                     ChecksumStore::compute(data));

    // Step 7: reply to client
    resp->set_success(true);
    return grpc::Status::OK;
}
```

**Test for Phase 3:** Write a 200 MB file end-to-end. Read it back using the client. Verify byte-perfect reproduction. Check that the data appears correctly on all 3 chunkservers (the file should exist on each with identical content).

---

### Phase 4 — Read Path

**Owner:** Any team member (good for parallelizing with Phase 3)  
**Depends on:** Phase 1 + Phase 2 complete  
**Goal:** Client can read any file, with chunk location caching and retry on stale cache.

---

#### Step 4.1 — Client chunk location cache (`client/cache.py`)

```python
# client/cache.py
import time
from dataclasses import dataclass, field

CACHE_TTL_SECONDS = 60

@dataclass
class CacheEntry:
    chunk_handle:  int
    primary:       str
    replicas:      list[str]
    version:       int
    expires_at:    float = field(default_factory=lambda: time.time() + CACHE_TTL_SECONDS)

class ChunkLocationCache:
    def __init__(self):
        self._cache: dict[tuple, CacheEntry] = {}  # (filename, chunk_index) → entry

    def get(self, filename: str, chunk_index: int) -> CacheEntry | None:
        key   = (filename, chunk_index)
        entry = self._cache.get(key)
        if entry and time.time() < entry.expires_at:
            return entry
        self._cache.pop(key, None)   # evict expired entry
        return None

    def put(self, filename: str, chunk_index: int, entry: CacheEntry):
        self._cache[(filename, chunk_index)] = entry

    def invalidate(self, filename: str, chunk_index: int):
        """Call this when a read gets a stale-version error."""
        self._cache.pop((filename, chunk_index), None)
```

---

#### Step 4.2 — Client read logic (`client/gfs_client.py`)

```python
def read(self, filename: str, offset: int, length: int) -> bytes:
    chunk_size   = 64 * 1024 * 1024
    result       = bytearray()
    remaining    = length
    current_off  = offset

    while remaining > 0:
        chunk_index  = current_off // chunk_size
        chunk_offset = current_off % chunk_size
        read_len     = min(remaining, chunk_size - chunk_offset)

        # 1. Check location cache
        loc = self.cache.get(filename, chunk_index)
        if loc is None:
            raw = self.master_stub.GetChunkLocations(ChunkLocRequest(
                filename=filename, chunk_index=chunk_index
            ))
            loc = CacheEntry(raw.chunk_handle, raw.primary_address,
                             list(raw.secondary_addresses), raw.chunk_version)
            self.cache.put(filename, chunk_index, loc)

        # 2. Try reading from any replica (prefer primary, fallback to others)
        for replica_addr in [loc.primary] + loc.replicas:
            stub = self._get_chunk_stub(replica_addr)
            try:
                resp = stub.ReadChunk(ReadRequest(
                    chunk_handle=loc.chunk_handle,
                    offset=chunk_offset,
                    length=read_len,
                    chunk_version=loc.version
                ))
                if resp.checksum_ok:
                    result.extend(resp.data)
                    break
            except grpc.RpcError as e:
                if e.code() == grpc.StatusCode.NOT_FOUND:
                    self.cache.invalidate(filename, chunk_index)
                continue   # try next replica
        else:
            raise IOError(f"All replicas failed for chunk {loc.chunk_handle}")

        current_off += read_len
        remaining   -= read_len

    return bytes(result)
```

---

### Phase 5 — Atomic Record Append

**Owner:** Amisha / Aaryan  
**Depends on:** Phase 3 complete  
**Goal:** Multiple clients can append to the same file concurrently without external locking.

---

#### Step 5.1 — Client append API

```python
def record_append(self, filename: str, data: bytes) -> int:
    """
    Atomically appends data to filename.
    Returns the offset at which data was written.
    GFS guarantees: at-least-once, at GFS-chosen offset.
    """
    MAX_APPEND_SIZE = 16 * 1024 * 1024    # 16 MB = 1/4 of chunk size
    if len(data) > MAX_APPEND_SIZE:
        raise ValueError(f"Append data exceeds max size ({MAX_APPEND_SIZE} bytes)")

    # Get location of the LAST chunk of the file (where appends go)
    loc = self.master_stub.GetChunkLocations(ChunkLocRequest(
        filename=filename,
        chunk_index=-1,              # -1 = last chunk
        create_if_missing=True
    ))

    stub = self._get_chunk_stub(loc.primary_address)
    resp = stub.AppendChunk(AppendRequest(
        chunk_handle=loc.chunk_handle,
        data=data,
        forward_to=list(loc.secondary_addresses)
    ))

    if resp.retry_on_next_chunk:
        # Primary padded this chunk to max size, retry on next chunk
        return self.record_append(filename, data)

    return resp.offset_written
```

---

#### Step 5.2 — Primary append logic (chunkserver)

```cpp
grpc::Status AppendChunk(grpc::ServerContext* ctx,
                         const AppendRequest* req,
                         AppendResponse* resp) override {
    int64_t handle      = req->chunk_handle();
    int32_t current_sz  = storage_.get_size(handle);
    int32_t record_sz   = req->data().size();
    int32_t max_sz      = CHUNK_SIZE_BYTES;

    // Check if record fits in this chunk
    if (current_sz + record_sz > max_sz) {
        // Pad this chunk to max size, tell client to retry on next chunk
        auto padding = std::vector<uint8_t>(max_sz - current_sz, 0);
        storage_.write(handle, current_sz, padding);
        // Tell all secondaries to pad too
        forward_pad_to_secondaries(handle, current_sz, max_sz);
        resp->set_retry_on_next_chunk(true);
        return grpc::Status::OK;
    }

    // Append at current end
    int32_t offset = storage_.append(handle, {req->data().begin(), req->data().end()});

    // Tell secondaries to write at the SAME offset
    forward_append_to_secondaries(handle, offset,
                                   {req->data().begin(), req->data().end()});

    resp->set_offset_written(offset);
    resp->set_retry_on_next_chunk(false);
    return grpc::Status::OK;
}
```

**Test for Phase 5:** Launch 10 concurrent Python threads all calling `record_append` on the same file. After all appends complete, read the full file back and verify all 10 records are present (though possibly with padding between them). Checksums must pass.

---

### Phase 6 — Fault Tolerance

**Owner:** All three (test together)  
**Depends on:** Phase 3–5 complete  
**Goal:** The system survives chunkserver failures without data loss or client-visible errors.

---

#### Step 6.1 — Re-replication (`master/replication.py`)

```python
# master/replication.py
import threading, queue

class ReplicationManager:
    def __init__(self, metadata_store, chunk_stubs_getter):
        self.store       = metadata_store
        self.get_stubs   = chunk_stubs_getter
        self._queue      = queue.PriorityQueue()
        self._running    = True
        threading.Thread(target=self._worker, daemon=True).start()

    def enqueue(self, chunk_handle: int, priority: str = 'normal'):
        prio_val = 0 if priority == 'high' else 1
        self._queue.put((prio_val, chunk_handle))

    def _worker(self):
        while self._running:
            prio, handle = self._queue.get()
            try:
                self._rereplicate(handle)
            except Exception as e:
                print(f"Re-replication failed for chunk {handle}: {e}")
                self._queue.put((prio, handle))  # retry

    def _rereplicate(self, chunk_handle: int):
        chunk = self.store.chunk_map.get(chunk_handle)
        if not chunk or len(chunk.replicas) >= 3:
            return   # already healthy

        # Pick a source replica (any healthy one)
        source = chunk.replicas[0] if chunk.replicas else None
        if not source:
            print(f"WARNING: Chunk {chunk_handle} has no replicas — LOST")
            return

        # Pick a target chunkserver (one that doesn't already have this chunk)
        all_servers = list(self.store.chunk_map.keys())  # simplified
        targets     = [s for s in all_servers if s not in chunk.replicas]
        if not targets:
            return

        target = targets[0]
        # Instruct source to copy chunk to target (chunkserver-to-chunkserver copy)
        source_stub = self.get_stubs(source)
        source_stub.CopyChunkTo(CopyRequest(
            chunk_handle=chunk_handle,
            target_address=target
        ))
        chunk.replicas.append(target)
        print(f"Re-replicated chunk {chunk_handle} from {source} to {target}")
```

---

#### Step 6.2 — Stale replica detection

This is already partially handled in the heartbeat (Step 1.5). Ensure that:
1. When `GetChunkLocations` is called, stale replicas are **never** included in the response.
2. Stale replicas are added to the GC queue (will be deleted on next heartbeat reply).

```python
def GetChunkLocations(self, request, context):
    # ... (lookup chunk) ...
    master_version = self.store.chunk_versions[chunk_handle]
    healthy_replicas = [
        r for r in chunk.replicas
        if r not in chunk.stale_replicas
    ]
    # ... (grant lease on healthy replicas, return response) ...
```

---

#### Step 6.3 — Lazy garbage collection (`master/gc.py`)

```python
# master/gc.py
import time, threading

SOFT_DELETE_TTL  = 60        # seconds (use short TTL for testing; paper uses 3 days)
GC_SCAN_INTERVAL = 30        # seconds between scans

class GarbageCollector:
    def __init__(self, metadata_store, oplog):
        self.store  = metadata_store
        self.oplog  = oplog
        threading.Thread(target=self._run, daemon=True).start()

    def soft_delete(self, filepath: str):
        """Rename file to hidden name with timestamp. Does NOT free storage yet."""
        file_meta = self.store.namespace.get(filepath)
        if not file_meta:
            return
        hidden = f"/.trash/{filepath.replace('/', '_')}_{int(time.time())}"
        self.store.namespace[hidden] = file_meta
        file_meta.deleted    = True
        file_meta.hidden_name = hidden
        file_meta.deleted_at  = time.time()
        del self.store.namespace[filepath]
        self.oplog.append('DELETE_FILE', {'path': filepath, 'hidden': hidden})

    def _run(self):
        while True:
            time.sleep(GC_SCAN_INTERVAL)
            self._scan_and_collect()

    def _scan_and_collect(self):
        now = time.time()

        # Phase 1: find expired hidden files and erase their chunk metadata
        orphaned_handles = []
        for path, meta in list(self.store.namespace.items()):
            if meta.deleted and (now - meta.deleted_at) > SOFT_DELETE_TTL:
                handles = self.store.file_chunks.pop(path, [])
                orphaned_handles.extend(handles)
                del self.store.namespace[path]

        # Phase 2: remove orphaned chunks from chunk_map
        # Chunkservers are told to delete these on next heartbeat reply
        for handle in orphaned_handles:
            self.store.chunk_map.pop(handle, None)
            self.store.chunk_versions.pop(handle, None)
            self.store._gc_pending.add(handle)   # picked up by heartbeat handler
```

---

#### Step 6.4 — Fault injection tests (`tests/test_e2e.py`)

```python
def test_chunkserver_failure_during_write():
    """
    Scenario: Start a write, kill one chunkserver mid-way, verify:
    1. Write completes (or retries and completes).
    2. Master detects failure within HEARTBEAT_TIMEOUT seconds.
    3. Under-replicated chunks are re-replicated.
    4. Final replication count returns to 3.
    """
    client = GFSClient(master_addr="localhost:50051")
    client.create_file("/test/fault_test.bin")

    # Start writing large file in background thread
    write_thread = threading.Thread(
        target=lambda: client.write("/test/fault_test.bin", 0, os.urandom(200 * 1024 * 1024))
    )
    write_thread.start()

    # Kill chunkserver2 mid-write
    time.sleep(2)
    subprocess.run(["docker", "stop", "gfs-chunkserver2-1"])

    write_thread.join(timeout=60)

    # Wait for re-replication
    time.sleep(HEARTBEAT_TIMEOUT + 10)

    # Verify all chunks now have 3 replicas again
    for chunk_handle in master.get_chunk_handles("/test/fault_test.bin"):
        assert len(master.get_replicas(chunk_handle)) == 3

    # Verify data integrity
    data_back = client.read("/test/fault_test.bin", 0, 200 * 1024 * 1024)
    assert hashlib.md5(data_back).hexdigest() == expected_md5
```

---

### Phase 7 — Benchmarking Suite

**Owner:** All three (run together for demo)  
**Depends on:** Phase 6 complete  
**Goal:** Reproduce the micro-benchmarks from Section 6.1 of the GFS paper.

---

#### Step 7.1 — Aggregate read throughput (`benchmarks/bench_read.py`)

```python
# benchmarks/bench_read.py
"""
N clients reading simultaneously. Measure aggregate MB/s.
Mirrors GFS paper Section 6.1.1.
"""
import threading, time, random
from client.gfs_client import GFSClient

FILE   = "/bench/read_target.bin"
FILE_SZ = 320 * 1024 * 1024   # 320 MB
READS_PER_CLIENT = 10
READ_SZ = 4 * 1024 * 1024     # 4 MB per read

def client_worker(client_id: int, results: list):
    client = GFSClient(master_addr="localhost:50051")
    total_bytes = 0
    start = time.time()
    for _ in range(READS_PER_CLIENT):
        offset = random.randint(0, FILE_SZ - READ_SZ)
        data   = client.read(FILE, offset, READ_SZ)
        total_bytes += len(data)
    elapsed = time.time() - start
    results[client_id] = total_bytes / elapsed / (1024 * 1024)  # MB/s

for N in [1, 2, 4, 8, 16]:
    results = [0.0] * N
    threads = [threading.Thread(target=client_worker, args=(i, results)) for i in range(N)]
    [t.start() for t in threads]
    [t.join()  for t in threads]
    aggregate = sum(results)
    print(f"N={N:>3} clients | Aggregate read: {aggregate:.1f} MB/s")
```

Run all three benchmarks and record results:
```bash
python benchmarks/bench_read.py   > results/read_throughput.txt
python benchmarks/bench_write.py  > results/write_throughput.txt
python benchmarks/bench_append.py > results/append_throughput.txt
python benchmarks/bench_fault.py  > results/recovery_time.txt
```

---

## Running the Project

### Prerequisites

```bash
# Python dependencies
pip install grpcio grpcio-tools protobuf

# C++ dependencies (Ubuntu/Debian)
sudo apt install -y build-essential cmake libgrpc++-dev libprotobuf-dev protobuf-compiler-grpc
```

### Start the cluster

```bash
# Build and start all containers
docker-compose -f docker/docker-compose.yml up --build

# Or start just 1 master + 3 chunkservers
docker-compose -f docker/docker-compose.yml up --scale chunkserver=3
```

### Quick smoke test

```python
from client.gfs_client import GFSClient

c = GFSClient(master_addr="localhost:50051")
c.create_file("/hello.txt")
c.write("/hello.txt", 0, b"Hello, GFS!")
data = c.read("/hello.txt", 0, 11)
print(data)   # b'Hello, GFS!'
```

### Kill a chunkserver (fault test)

```bash
docker stop gfs-chunkserver2-1
# Watch master logs for re-replication activity
docker logs -f gfs-master-1
```

---

## Feature Checklist

> Tick items as they are completed. The first unticked item tells the next contributor exactly where to start.

### Phase 0 — Setup
- [ ] Repo folder structure created
- [ ] `proto/master.proto` finalized and reviewed by team
- [ ] `proto/chunk.proto` finalized and reviewed by team
- [ ] Python gRPC stubs generated (`*_pb2.py`, `*_pb2_grpc.py`)
- [ ] C++ gRPC stubs generated (`.pb.cc`, `.pb.h`, `.grpc.pb.cc`)
- [ ] `docker-compose.yml` spins up master + 3 chunkservers without errors

### Phase 1 — Master
- [ ] `MetadataStore` class with namespace + file_chunks + chunk_map
- [ ] `OperationLog.append()` — writes and fsyncs before returning
- [ ] `OperationLog.replay()` — correctly rebuilds state on startup
- [ ] `OperationLog.write_checkpoint()` + `load_checkpoint()`
- [ ] `NamespaceLockManager` — read locks on parents, write lock on leaf
- [ ] `HeartbeatMonitor.handle_heartbeat()` — updates replica lists
- [ ] `HeartbeatMonitor.check_dead_servers()` — detects failures, triggers re-replication
- [ ] Master gRPC server starts and handles `CreateFile`, `GetChunkLocations`, `HeartBeat`
- [ ] **Test:** Master crash-recovery — file visible after restart, log replayed correctly

### Phase 2 — Chunkserver
- [ ] `ChunkStorage` — read/write/append/remove/list chunks as disk files
- [ ] `ChecksumStore` — 64KB block CRC32, verify on read, update on write
- [ ] `WriteBuffer` — LRU in-memory buffer, put/take, eviction
- [ ] `HeartbeatSender` — sends heartbeat every 5s, processes `chunks_to_delete`
- [ ] ChunkService gRPC: `ReadChunk`, `WriteChunk`, `AppendChunk`, `DeleteChunk`
- [ ] **Test:** Write → corrupt raw file → read returns checksum error (not corrupt data)

### Phase 3 — Write Pipeline
- [ ] `LeaseManager.grant_lease()` — picks primary, increments version, sets expiry
- [ ] `LeaseManager.extend_lease()` — via heartbeat
- [ ] `LeaseManager.revoke_lease()`
- [ ] Client `WritePipeline` — Steps 1–7 from GFS paper Figure 2
- [ ] Chunkserver `ForwardWrite` — buffer-only, no commit
- [ ] Chunkserver `WriteChunk` (commit) — forwards to secondaries, applies locally
- [ ] **Test:** Write 200 MB file, read back, verify all 3 replicas have identical data

### Phase 4 — Read Path
- [ ] `ChunkLocationCache` — get/put/invalidate with TTL
- [ ] Client `read()` — chunk index translation, replica fallback, cache invalidation on stale
- [ ] **Test:** Read while one chunkserver is down — falls back to another replica transparently

### Phase 5 — Atomic Record Append
- [ ] Client `record_append()` — sends to last chunk, handles retry-on-next-chunk
- [ ] Chunkserver `AppendChunk` — fit check, padding, same-offset forwarding to secondaries
- [ ] **Test:** 10 concurrent appenders on same file — all records present, no corruption

### Phase 6 — Fault Tolerance
- [ ] `ReplicationManager` — priority queue, worker thread, source→target copy
- [ ] Stale replica excluded from `GetChunkLocations` response
- [ ] Stale replica added to GC pending set
- [ ] `GarbageCollector.soft_delete()` — renames to hidden path, logs deletion
- [ ] `GarbageCollector._scan_and_collect()` — expires hidden files, orphans chunks
- [ ] **Test:** Kill chunkserver mid-write → re-replication completes → chunk count = 3
- [ ] **Test:** Delete file → wait TTL → chunkservers confirm chunks are gone

### Phase 7 — Benchmarks
- [ ] `bench_read.py` — aggregate read MB/s for N = 1, 2, 4, 8, 16 clients
- [ ] `bench_write.py` — aggregate write MB/s for N = 1, 2, 4, 8, 16 clients
- [ ] `bench_append.py` — aggregate append MB/s for N = 1, 2, 4, 8, 16 clients
- [ ] `bench_fault.py` — time-to-recovery after single chunkserver failure
- [ ] Results saved under `results/` and included in presentation
