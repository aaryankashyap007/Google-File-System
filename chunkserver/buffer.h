#pragma once
#include <unordered_map>
#include <vector>
#include <string>
#include <mutex>
#include <chrono>
#include <cstdint>

struct BufferedData {
    int64_t chunk_handle;
    std::vector<uint8_t> data;
    std::chrono::steady_clock::time_point inserted_at;
};

class WriteBuffer {
public:
    // Store incoming data
    void put(const std::string& key, int64_t chunk_handle, const std::vector<uint8_t>& data);

    // Retrieve and remove buffered data for a commit
    std::vector<uint8_t> take(const std::string& key);

    // Evict entries older than max_age_seconds (background cleanup)
    void evict_stale(int max_age_seconds = 60);

private:
    std::unordered_map<std::string, BufferedData> buffer_;
    std::mutex mutex_;
};