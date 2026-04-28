#include "checksum.h"
#include <fstream>
#include <filesystem>
#include <stdexcept>

namespace fs = std::filesystem;

ChecksumStore::ChecksumStore(const std::string& data_dir) : data_dir_(data_dir) {
    if (!fs::exists(data_dir_)) {
        fs::create_directories(data_dir_);
    }
}

std::string ChecksumStore::checksum_path(int64_t handle) const {
    return data_dir_ + "/chunk_" + std::to_string(handle) + ".checksum";
}

// Standard CRC32 algorithm implementation
uint32_t ChecksumStore::compute(const std::vector<uint8_t>& data) {
    uint32_t crc = 0xFFFFFFFF;
    for (uint8_t byte : data) {
        crc ^= byte;
        for (int i = 0; i < 8; i++) {
            crc = (crc >> 1) ^ (0xEDB88320 & (-(crc & 1)));
        }
    }
    return ~crc;
}

void ChecksumStore::load_from_disk_if_needed(int64_t handle) {
    if (checksum_cache_.find(handle) != checksum_cache_.end()) return;

    std::vector<uint32_t> checksums;
    std::string path = checksum_path(handle);
    if (fs::exists(path)) {
        std::ifstream file(path, std::ios::binary);
        uint32_t chk;
        while (file.read(reinterpret_cast<char*>(&chk), sizeof(chk))) {
            checksums.push_back(chk);
        }
    }
    checksum_cache_[handle] = checksums;
}

void ChecksumStore::update(int64_t handle, int32_t block_index, uint32_t checksum) {
    std::lock_guard<std::mutex> lock(mutex_);
    load_from_disk_if_needed(handle);
    
    if (block_index >= checksum_cache_[handle].size()) {
        checksum_cache_[handle].resize(block_index + 1, 0);
    }
    checksum_cache_[handle][block_index] = checksum;
    
    // In a real system, we might batch these writes. For the MVP, we persist immediately.
    save_to_disk(handle);
}

bool ChecksumStore::verify(int64_t handle, int32_t block_index, const std::vector<uint8_t>& block_data) {
    std::lock_guard<std::mutex> lock(mutex_);
    load_from_disk_if_needed(handle);

    if (block_index >= checksum_cache_[handle].size()) {
        return false; // No checksum exists for this block
    }

    uint32_t stored_checksum = checksum_cache_[handle][block_index];
    uint32_t computed_checksum = compute(block_data);
    
    return stored_checksum == computed_checksum;
}

void ChecksumStore::save_to_disk(int64_t handle) {
    std::string path = checksum_path(handle);
    std::ofstream file(path, std::ios::binary | std::ios::trunc);
    for (uint32_t chk : checksum_cache_[handle]) {
        file.write(reinterpret_cast<const char*>(&chk), sizeof(chk));
    }
}