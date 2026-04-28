#pragma once
#include <thread>
#include <atomic>
#include <string>
#include <memory>
#include <grpcpp/grpcpp.h>
#include "master.grpc.pb.h"
#include "storage.h"

class HeartbeatSender {
public:
    HeartbeatSender(std::shared_ptr<gfs::MasterService::Stub> master_stub,
                    ChunkStorage& storage,
                    const std::string& my_address);
    ~HeartbeatSender();

    void start();
    void stop();

private:
    void run();

    std::shared_ptr<gfs::MasterService::Stub> master_stub_;
    ChunkStorage& storage_;
    std::string my_address_;
    std::atomic<bool> running_{false};
    std::thread thread_;
};