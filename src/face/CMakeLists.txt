
cmake_minimum_required(VERSION 3.16)
project(face)

set(CMAKE_CXX_STANDARD 23)

find_package(SDL2 REQUIRED)

find_package(PkgConfig REQUIRED)
pkg_check_modules(EGL REQUIRED egl)
pkg_check_modules(GLES2 REQUIRED glesv2)

find_path(NATS_INCLUDE_DIR nats/nats.h)
find_library(NATS_LIBRARY nats)
if (NOT NATS_INCLUDE_DIR OR NOT NATS_LIBRARY)
    message(FATAL_ERROR "NATS C client not found. Install libnats (header nats/nats.h and library libnats).")
endif()

add_executable(face src/main.cpp)

target_include_directories(face PRIVATE ${NATS_INCLUDE_DIR})
target_link_libraries(face PRIVATE ${NATS_LIBRARY})

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
