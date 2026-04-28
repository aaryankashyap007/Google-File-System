#pragma once
#include <vector>
#include <cstdint>
#include <string>
#include <unordered_map>
#include <mutex>

class ChecksumStore {
public:
    explicit ChecksumStore(const std::string& data_dir);

    // Compute CRC32 of a data block
    static uint32_t compute(const std::vector<uint8_t>& data);

    // Update checksum for the block at block_index after a write
    void update(int64_t handle, int32_t block_index, uint32_t checksum);

    // Verify a block's data against stored checksum
    bool verify(int64_t handle, int32_t block_index, const std::vector<uint8_t>& block_data);

    // Save all checksums for a chunk to disk
    void save_to_disk(int64_t handle);

private:
    std::string data_dir_;
    std::mutex mutex_;
    // In-memory cache: chunk_handle -> vector of block checksums
    std::unordered_map<int64_t, std::vector<uint32_t>> checksum_cache_;

    std::string checksum_path(int64_t handle) const;
    void load_from_disk_if_needed(int64_t handle);
};