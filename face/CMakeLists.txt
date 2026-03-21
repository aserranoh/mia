
cmake_minimum_required(VERSION 3.16)
project(face)

set(CMAKE_CXX_STANDARD 23)

find_package(SDL2 REQUIRED)

find_package(PkgConfig REQUIRED)
pkg_check_modules(EGL REQUIRED egl)
pkg_check_modules(GLES2 REQUIRED glesv2)

# cppzmq is header-only; we still link libzmq (below).
include(CheckIncludeFileCXX)
check_include_file_cxx("zmq.hpp" HAVE_CPPZMQ_HEADER)
if (NOT HAVE_CPPZMQ_HEADER)
    message(FATAL_ERROR "cppzmq header <zmq.hpp> not found. Install cppzmq-dev (or your distro equivalent).")
endif()

find_package(cppzmq QUIET)

# ZeroMQ (libzmq)
find_package(ZeroMQ QUIET)
if (NOT ZeroMQ_FOUND)
    find_package(PkgConfig QUIET)
    if (PkgConfig_FOUND)
        pkg_check_modules(ZMQ QUIET libzmq)
    endif()
endif()

add_executable(face src/main.cpp)

target_include_directories(face PRIVATE
    libs/nanovg/src
)

target_sources(face PRIVATE
    libs/nanovg/src/nanovg.c
    src/nanovg_gl_impl.cpp
)

target_compile_definitions(face PRIVATE
    NANOVG_GLES3
)

target_link_libraries(face PRIVATE
    SDL2::SDL2
    ${EGL_LINK_LIBRARIES}
    ${GLES2_LINK_LIBRARIES}
)

target_include_directories(face PRIVATE
    ${EGL_INCLUDE_DIRS}
    ${GLES2_INCLUDE_DIRS}
)

target_compile_options(face PRIVATE
    ${EGL_CFLAGS_OTHER}
    ${GLES2_CFLAGS_OTHER}
)

if (cppzmq_FOUND)
    if (TARGET cppzmq)
        target_link_libraries(face PRIVATE cppzmq)
    elseif (TARGET cppzmq::cppzmq)
        target_link_libraries(face PRIVATE cppzmq::cppzmq)
    endif()
endif()

if (ZeroMQ_FOUND)
    if (TARGET ZeroMQ::libzmq)
        target_link_libraries(face PRIVATE ZeroMQ::libzmq)
    elseif (TARGET libzmq)
        target_link_libraries(face PRIVATE libzmq)
    else()
        target_link_libraries(face PRIVATE zmq)
    endif()
elseif (ZMQ_FOUND)
    target_include_directories(face PRIVATE ${ZMQ_INCLUDE_DIRS})
    target_link_directories(face PRIVATE ${ZMQ_LIBRARY_DIRS})
    target_compile_options(face PRIVATE ${ZMQ_CFLAGS_OTHER})
    target_link_libraries(face PRIVATE ${ZMQ_LINK_LIBRARIES})
else()
    message(FATAL_ERROR "ZeroMQ (libzmq) not found. Install libzmq3-dev (or your distro equivalent).")
endif()
