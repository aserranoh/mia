
# Face

## Dependencies

sudo apt install \
  build-essential \
  cmake \
  pkg-config \
  libsdl2-dev \
  libegl1-mesa-dev \
  libgles2-mesa-dev \
  libzmq3-dev \
  cppzmq-dev

## Build

cmake -S . -B build
cmake --build build/ -j

## Run

./face --video-driver=kmsdrm