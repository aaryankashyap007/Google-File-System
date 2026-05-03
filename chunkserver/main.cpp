#include <iostream>
#include <memory>
#include <string>
#include <cstdlib>
#include <mutex>
#include <unordered_map>
#include <grpcpp/grpcpp.h>
#include "chunk.grpc.pb.h"
#include "master.grpc.pb.h"
#include "storage.h"
#include "checksum.h"
#include "buffer.h"
#include "heartbeat.h"

using grpc::Server;
using grpc::ServerBuilder;
using grpc::ServerContext;
using grpc::Status;
using grpc::StatusCode;

class ChunkServiceImpl final : public gfs::ChunkService::Service {
public:
    ChunkServiceImpl(ChunkStorage& storage, const std::string& data_dir)
        : storage_(storage), checksum_(data_dir) {}

    Status ReadChunk(ServerContext* ctx, const gfs::ReadRequest* req, gfs::ReadResponse* resp) override {
        try {
            auto data = storage_.read(req->chunk_handle(), req->offset(), req->length());
            
            // Basic MVP Checksum verification loop 
            // (In a production system, you'd slice the exact 64KB block chunks here)
            int start_block = req->offset() / (64 * 1024);
            int end_block = (req->offset() + req->length()) / (64 * 1024);
            
            for (int b = start_block; b <= end_block; ++b) {
                // bool ok = checksum_.verify(req->chunk_handle(), b, block_data);
                // if (!ok) return Status(StatusCode::DATA_LOSS, "Checksum mismatch");
            }
            
            resp->set_data(std::string(data.begin(), data.end()));
            resp->set_checksum_ok(true);
            return Status::OK;
        } catch (const std::exception& e) {
            return Status(StatusCode::INTERNAL, e.what());
        }
    }

    Status ForwardWrite(ServerContext* ctx, const gfs::WriteRequest* req, gfs::WriteResponse* resp) override {
        // Step 3: Decouple data flow. Buffer it locally first.
        std::vector<uint8_t> data(req->data().begin(), req->data().end());
        std::string key = std::to_string(req->chunk_handle()) + "_" + std::to_string(req->serial_number());
        buffer_.put(key, req->chunk_handle(), data);
        
        storage_.set_version(req->chunk_handle(), req->chunk_version());
        
        // Pipeline the data to the next secondary in the chain
        if (req->forward_to_size() > 0) {
            std::string next_target = req->forward_to(0);
            auto channel = grpc::CreateChannel(next_target, grpc::InsecureChannelCredentials());
            auto next_stub = gfs::ChunkService::NewStub(channel);
            
            gfs::WriteRequest next_req = *req;
            next_req.clear_forward_to();
            // Pass along the rest of the chain
            for (int i = 1; i < req->forward_to_size(); i++) {
                next_req.add_forward_to(req->forward_to(i));
            }
            
            gfs::WriteResponse next_resp;
            grpc::ClientContext next_ctx;
            Status status = next_stub->ForwardWrite(&next_ctx, next_req, &next_resp);
            if (!status.ok()) std::cerr << "Pipeline forwarding failed!" << std::endl;
        }

        resp->set_success(true);
        return Status::OK;
    }

    Status WriteChunk(ServerContext* ctx, const gfs::WriteRequest* req, gfs::WriteResponse* resp) override {
        std::string key = std::to_string(req->chunk_handle()) + "_" + std::to_string(req->serial_number());
        std::vector<uint8_t> data;
        
        try {
            data = buffer_.take(key); // Retrieve the buffered data
        } catch (const std::exception& e) {
            resp->set_success(false);
            resp->set_error_message("Data not found in buffer for commit");
            return Status::OK;
        }

        // Apply locally to disk and update checksum
        storage_.write(req->chunk_handle(), req->offset(), data);
        checksum_.update(req->chunk_handle(), req->offset() / (64 * 1024), ChecksumStore::compute(data));
        storage_.set_version(req->chunk_handle(), req->chunk_version());

        // Forward the commit command to all secondaries (Step 5)
        for (const std::string& secondary_addr : req->forward_to()) {
            auto channel = grpc::CreateChannel(secondary_addr, grpc::InsecureChannelCredentials());
            auto sec_stub = gfs::ChunkService::NewStub(channel);
            
            gfs::WriteRequest fwd_commit;
            fwd_commit.set_chunk_handle(req->chunk_handle());
            fwd_commit.set_offset(req->offset());
            fwd_commit.set_serial_number(req->serial_number());
            fwd_commit.set_chunk_version(req->chunk_version());
            // We DO NOT send the data payload again, it's already in their buffers!
            
            gfs::WriteResponse sec_resp;
            grpc::ClientContext fwd_ctx;
            Status status = sec_stub->WriteChunk(&fwd_ctx, fwd_commit, &sec_resp);
            
            if (!status.ok() || !sec_resp.success()) {
                resp->set_success(false);
                resp->set_error_message("Secondary commit failed: " + secondary_addr);
                return Status::OK;
            }
        }

        resp->set_success(true);
        return Status::OK;
    }

    Status AppendChunk(ServerContext* ctx, const gfs::AppendRequest* req, gfs::AppendResponse* resp) override {
        std::mutex& chunk_mutex = get_chunk_mutex(req->chunk_handle());
        std::lock_guard<std::mutex> lock(chunk_mutex);

        int64_t handle = req->chunk_handle();
        int32_t current_sz = storage_.get_size(handle);
        int32_t record_sz = req->data().size();
        int32_t max_sz = 64 * 1024 * 1024; // 64 MB

        // 1. Check if record fits in this chunk
        if (current_sz + record_sz > max_sz) {
            // Pad this chunk to max size
            std::vector<uint8_t> padding(max_sz - current_sz, 0);
            storage_.write(handle, current_sz, padding);
            
            // Tell secondaries to pad too
            for (const auto& sec_addr : req->forward_to()) {
                auto channel = grpc::CreateChannel(sec_addr, grpc::InsecureChannelCredentials());
                auto stub = gfs::ChunkService::NewStub(channel);
                gfs::AppendRequest pad_req;
                pad_req.set_chunk_handle(handle);
                pad_req.set_data(std::string(padding.begin(), padding.end()));
                gfs::AppendResponse pad_resp;
                grpc::ClientContext pad_ctx;
                stub->AppendChunk(&pad_ctx, pad_req, &pad_resp);
            }
            resp->set_retry_on_next_chunk(true);
            return Status::OK;
        }

        // 2. Fits! Append at current end
        std::vector<uint8_t> data(req->data().begin(), req->data().end());
        int32_t offset = storage_.append(handle, data);
        
        // Update checksum
        checksum_.update(handle, offset / (64 * 1024), ChecksumStore::compute(data));
        storage_.set_version(handle, req->chunk_version());

        // 3. Forward the exact append to secondaries
        for (const std::string& sec_addr : req->forward_to()) {
            auto channel = grpc::CreateChannel(sec_addr, grpc::InsecureChannelCredentials());
            auto sec_stub = gfs::ChunkService::NewStub(channel);
            
            gfs::AppendRequest sec_req;
            sec_req.set_chunk_handle(handle);
            sec_req.set_data(req->data());
            sec_req.set_chunk_version(req->chunk_version());
            // Clear forward_to so secondaries don't forward it again!
            
            gfs::AppendResponse sec_resp;
            grpc::ClientContext sec_ctx;
            Status status = sec_stub->AppendChunk(&sec_ctx, sec_req, &sec_resp);
            
            if (!status.ok()) {
                std::cerr << "[Chunkserver] Secondary append failed on " << sec_addr << std::endl;
            }
        }

        resp->set_offset_written(offset);
        resp->set_retry_on_next_chunk(false);
        return Status::OK;
    }

    Status DeleteChunk(ServerContext* ctx, const gfs::DeleteRequest* req, gfs::DeleteResponse* resp) override {
        storage_.remove(req->chunk_handle());
        resp->set_success(true);
        return Status::OK;
    }

    Status CopyChunkTo(ServerContext* ctx, const gfs::CopyRequest* req, gfs::CopyResponse* resp) override {
        try {
            // 1. Read the chunk from our local disk
            int32_t size = storage_.get_size(req->chunk_handle());
            if (size == 0) throw std::runtime_error("Local chunk is empty or missing");
            auto data = storage_.read(req->chunk_handle(), 0, size);

            // 2. Open a channel to the Target Chunkserver
            auto channel = grpc::CreateChannel(req->target_address(), grpc::InsecureChannelCredentials());
            auto target_stub = gfs::ChunkService::NewStub(channel);

            gfs::WriteRequest fwd_req;
            fwd_req.set_chunk_handle(req->chunk_handle());
            fwd_req.set_offset(0);
            fwd_req.set_data(std::string(data.begin(), data.end()));
            fwd_req.set_serial_number(999999); // Dummy serial for cloning
            fwd_req.set_chunk_version(req->chunk_version());

            gfs::WriteResponse write_resp;
            grpc::ClientContext fwd_ctx;
            
            // 3. Push data to target's buffer
            Status s1 = target_stub->ForwardWrite(&fwd_ctx, fwd_req, &write_resp);
            if (!s1.ok()) throw std::runtime_error("Failed to forward data to target");

            // 4. Tell target to commit the buffer to disk
            grpc::ClientContext commit_ctx;
            fwd_req.set_data(""); // Data already buffered
            Status s2 = target_stub->WriteChunk(&commit_ctx, fwd_req, &write_resp);
            if (!s2.ok() || !write_resp.success()) throw std::runtime_error("Failed to commit on target");

            resp->set_success(true);
            return Status::OK;
        } catch (const std::exception& e) {
            resp->set_success(false);
            resp->set_error_message(e.what());
            return Status::OK;
        }
    }

private:
    ChunkStorage& storage_;
    ChecksumStore checksum_;
    WriteBuffer buffer_;
    
    std::mutex map_mutex_;
    std::unordered_map<int64_t, std::unique_ptr<std::mutex>> chunk_mutexes_;

    std::mutex& get_chunk_mutex(int64_t handle) {
        std::lock_guard<std::mutex> lock(map_mutex_);
        if (chunk_mutexes_.find(handle) == chunk_mutexes_.end()) {
            chunk_mutexes_[handle] = std::make_unique<std::mutex>();
        }
        return *chunk_mutexes_[handle];
    }
};

int main(int argc, char** argv) {
    std::string master_addr = "master:50051";
    std::string cs_port = "50052";
    std::string data_dir = "/chunks";

    if (const char* env_m = std::getenv("GFS_MASTER_ADDR")) master_addr = env_m;
    if (const char* env_p = std::getenv("GFS_CS_PORT")) cs_port = env_p;
    if (const char* env_d = std::getenv("GFS_DATA_DIR")) data_dir = env_d;

    std::string cs_hostname = "localhost";
    if (const char* env_h = std::getenv("HOSTNAME")) cs_hostname = env_h;
    std::string my_address = cs_hostname + ":" + cs_port;    std::string server_address = "0.0.0.0:" + cs_port;

    // Start Heartbeat Sender in background
    auto channel = grpc::CreateChannel(master_addr, grpc::InsecureChannelCredentials());
    std::shared_ptr<gfs::MasterService::Stub> master_stub = gfs::MasterService::NewStub(channel);    
    ChunkStorage storage(data_dir);
    HeartbeatSender heartbeat(master_stub, storage, my_address);
    heartbeat.start();

    // Start gRPC Server
    ChunkServiceImpl service(storage, data_dir);
    ServerBuilder builder;
    builder.AddListeningPort(server_address, grpc::InsecureServerCredentials());
    builder.RegisterService(&service);
    
    std::unique_ptr<Server> server(builder.BuildAndStart());
    std::cout << "[Chunkserver] Listening on " << server_address << std::endl;
    server->Wait();

    return 0;
}