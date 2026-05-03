#include "heartbeat.h"
#include <chrono>
#include <iostream>

#define HEARTBEAT_INTERVAL 5

HeartbeatSender::HeartbeatSender(std::shared_ptr<gfs::MasterService::Stub> master_stub,
                                 ChunkStorage& storage,
                                 const std::string& my_address)
    : master_stub_(master_stub), storage_(storage), my_address_(my_address) {}

HeartbeatSender::~HeartbeatSender() { stop(); }

void HeartbeatSender::start() {
    running_ = true;
    thread_ = std::thread(&HeartbeatSender::run, this);
}

void HeartbeatSender::stop() {
    running_ = false;
    if (thread_.joinable()) thread_.join();
}

void HeartbeatSender::run() {
    while (running_) {
        std::this_thread::sleep_for(std::chrono::seconds(HEARTBEAT_INTERVAL));

        auto handles = storage_.list_all();
        
        gfs::HeartBeatRequest req;
        req.set_chunkserver_address(my_address_);
        for (auto h : handles) {
            req.add_chunk_handles(h);
            req.add_chunk_versions(storage_.get_version(h));
        }

        gfs::HeartBeatResponse resp;
        grpc::ClientContext ctx;
        auto status = master_stub_->HeartBeat(&ctx, req, &resp);

        if (status.ok()) {
            for (auto handle : resp.chunks_to_delete()) {
                std::cout << "[Chunkserver] Garbage collecting orphaned chunk " << handle << std::endl;
                storage_.remove(handle);
            }
        } else {
            std::cerr << "[Chunkserver] Heartbeat failed to reach Master: " << status.error_message() << std::endl;
        }
    }
}