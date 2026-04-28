#pragma once
#include <string>
#include <vector>
#include <cstdint>

class ChunkStorage {
public:
    explicit ChunkStorage(const std::string& data_dir);

    // Read `length` bytes from chunk at `offset`.
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
    std::string chunk_path(int64_t handle) const;
};