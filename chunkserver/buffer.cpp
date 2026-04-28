#include "buffer.h"
#include <stdexcept>

void WriteBuffer::put(const std::string& key, int64_t chunk_handle, const std::vector<uint8_t>& data) {
    std::lock_guard<std::mutex> lock(mutex_);
    buffer_[key] = {
        chunk_handle,
        data,
        std::chrono::steady_clock::now()
    };
}

std::vector<uint8_t> WriteBuffer::take(const std::string& key) {
    std::lock_guard<std::mutex> lock(mutex_);
    auto it = buffer_.find(key);
    if (it == buffer_.end()) {
        throw std::runtime_error("Data not found in buffer (it may have expired or was never pushed)");
    }
    
    std::vector<uint8_t> data = std::move(it->second.data);
    buffer_.erase(it);
    return data;
}

void WriteBuffer::evict_stale(int max_age_seconds) {
    std::lock_guard<std::mutex> lock(mutex_);
    auto now = std::chrono::steady_clock::now();
    
    for (auto it = buffer_.begin(); it != buffer_.end(); ) {
        auto age = std::chrono::duration_cast<std::chrono::seconds>(now - it->second.inserted_at).count();
        if (age > max_age_seconds) {
            it = buffer_.erase(it);
        } else {
            ++it;
        }
    }
}