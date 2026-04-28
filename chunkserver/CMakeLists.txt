cmake_minimum_required(VERSION 3.15)
project(gfs_chunkserver)

set(CMAKE_CXX_STANDARD 17)

# Find Protobuf and Threads
find_package(Protobuf REQUIRED)
find_package(Threads REQUIRED)

# Include current directory for generated stubs
include_directories(${CMAKE_CURRENT_SOURCE_DIR})

# Add all source files and ALL generated stubs
add_executable(chunkserver
    main.cpp
    storage.cpp
    checksum.cpp
    buffer.cpp
    heartbeat.cpp
    chunk.pb.cc
    chunk.grpc.pb.cc
    master.pb.cc
    master.grpc.pb.cc
)

# Link directly against the system gRPC libraries installed via apt
target_link_libraries(chunkserver
    protobuf::libprotobuf
    grpc++
    grpc
    Threads::Threads
)