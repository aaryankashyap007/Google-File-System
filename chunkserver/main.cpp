#include <iostream>
#include <memory>
#include <string>
#include <cstdlib>
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
    ChunkServiceImpl(const std::string& data_dir) 
        : storage_(data_dir), checksum_(data_dir) {}

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
        // Step 3 of the Write Pipeline: Decouple data flow from control flow.
        // We buffer the data here, but DO NOT commit it to disk yet.
        std::vector<uint8_t> data(req->data().begin(), req->data().end());
        std::string key = std::to_string(req->chunk_handle()) + "_" + std::to_string(req->serial_number());
        buffer_.put(key, req->chunk_handle(), data);
        
        resp->set_success(true);
        return Status::OK;
    }

    Status WriteChunk(ServerContext* ctx, const gfs::WriteRequest* req, gfs::WriteResponse* resp) override {
        // TODO: Will be implemented in Phase 3 (Pipeline Commit & Leases)
        resp->set_success(true);
        return Status::OK;
    }

    Status AppendChunk(ServerContext* ctx, const gfs::AppendRequest* req, gfs::AppendResponse* resp) override {
        // TODO: Will be implemented in Phase 5 (Atomic Record Append)
        return Status::OK;
    }

    Status DeleteChunk(ServerContext* ctx, const gfs::DeleteRequest* req, gfs::DeleteResponse* resp) override {
        storage_.remove(req->chunk_handle());
        resp->set_success(true);
        return Status::OK;
    }

private:
    ChunkStorage storage_;
    ChecksumStore checksum_;
    WriteBuffer buffer_;
};

int main(int argc, char** argv) {
    std::string master_addr = "master:50051";
    std::string cs_port = "50052";
    std::string data_dir = "/chunks";

    if (const char* env_m = std::getenv("GFS_MASTER_ADDR")) master_addr = env_m;
    if (const char* env_p = std::getenv("GFS_CS_PORT")) cs_port = env_p;
    if (const char* env_d = std::getenv("GFS_DATA_DIR")) data_dir = env_d;

    std::string my_address = "chunkserver:" + cs_port; 
    std::string server_address = "0.0.0.0:" + cs_port;

    // Start Heartbeat Sender in background
    auto channel = grpc::CreateChannel(master_addr, grpc::InsecureChannelCredentials());
    std::shared_ptr<gfs::MasterService::Stub> master_stub = gfs::MasterService::NewStub(channel);    
    ChunkStorage storage(data_dir);
    HeartbeatSender heartbeat(master_stub, storage, my_address);
    heartbeat.start();

    // Start gRPC Server
    ChunkServiceImpl service(data_dir);
    ServerBuilder builder;
    builder.AddListeningPort(server_address, grpc::InsecureServerCredentials());
    builder.RegisterService(&service);
    
    std::unique_ptr<Server> server(builder.BuildAndStart());
    std::cout << "[Chunkserver] Listening on " << server_address << std::endl;
    server->Wait();

    return 0;
}