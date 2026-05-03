#include "storage.h"
#include <fstream>
#include <filesystem>
#include <stdexcept>
#include <iostream>

namespace fs = std::filesystem;

ChunkStorage::ChunkStorage(const std::string& data_dir) : data_dir_(data_dir) {
    if (!fs::exists(data_dir_)) {
        fs::create_directories(data_dir_);
    }
}

std::string ChunkStorage::chunk_path(int64_t handle) const {
    return data_dir_ + "/chunk_" + std::to_string(handle) + ".bin";
}

std::vector<uint8_t> ChunkStorage::read(int64_t handle, int32_t offset, int32_t length) {
    std::string path = chunk_path(handle);
    std::ifstream file(path, std::ios::binary);
    
    if (!file) {
        throw std::runtime_error("Chunk not found");
    }

    file.seekg(offset, std::ios::beg);
    std::vector<uint8_t> buffer(length);
    file.read(reinterpret_cast<char*>(buffer.data()), length);
    
    // Resize buffer if we read less than requested (e.g., EOF)
    buffer.resize(file.gcount());
    return buffer;
}

void ChunkStorage::write(int64_t handle, int32_t offset, const std::vector<uint8_t>& data) {
    std::string path = chunk_path(handle);
    // Open for read/write, create if it doesn't exist
    std::fstream file(path, std::ios::binary | std::ios::in | std::ios::out);
    
    if (!file) {
        // File doesn't exist, create it
        file.open(path, std::ios::binary | std::ios::out);
        file.close();
        file.open(path, std::ios::binary | std::ios::in | std::ios::out);
    }

    file.seekp(offset, std::ios::beg);
    file.write(reinterpret_cast<const char*>(data.data()), data.size());
}

int32_t ChunkStorage::append(int64_t handle, const std::vector<uint8_t>& data) {
    std::string path = chunk_path(handle);
    int32_t offset = get_size(handle);
    
    std::ofstream file(path, std::ios::binary | std::ios::app);
    file.write(reinterpret_cast<const char*>(data.data()), data.size());
    
    return offset;
}

void ChunkStorage::remove(int64_t handle) {
    fs::remove(chunk_path(handle));
    std::lock_guard<std::mutex> lock(version_mutex_);
    versions_.erase(handle);
}

std::vector<int64_t> ChunkStorage::list_all() {
    std::vector<int64_t> handles;
    for (const auto& entry : fs::directory_iterator(data_dir_)) {
        if (entry.is_regular_file()) {
            std::string filename = entry.path().filename().string();
            if (filename.find("chunk_") == 0 && filename.find(".bin") != std::string::npos) {
                // Extract handle from "chunk_<handle>.bin"
                std::string handle_str = filename.substr(6, filename.find(".bin") - 6);
                handles.push_back(std::stoll(handle_str));
            }
        }
    }
    return handles;
}

int32_t ChunkStorage::get_size(int64_t handle) {
    std::string path = chunk_path(handle);
    if (!fs::exists(path)) return 0;
    return static_cast<int32_t>(fs::file_size(path));
}

void ChunkStorage::set_version(int64_t handle, int32_t version) {
    std::lock_guard<std::mutex> lock(version_mutex_);
    versions_[handle] = version;
}

int32_t ChunkStorage::get_version(int64_t handle) {
    std::lock_guard<std::mutex> lock(version_mutex_);
    auto it = versions_.find(handle);
    if (it == versions_.end()) {
        return 0;
    }
    return it->second;
}