
# Face

## Dependencies

```bash
sudo apt install \
  build-essential \
  cmake \
  pkg-config \
  libsdl2-dev \
  libegl1-mesa-dev \
  libgles2-mesa-dev \
  libzmq3-dev \
  cppzmq-dev \
  libnats-dev
```

## Build

```bash
cmake -S . -B build
cmake --build build/ -j
```

## Run

```bash
./face --video-driver=kmsdrm
```


# Piper

## Dependencies

```bash
sudo apt install libportaudio2
```

## Download voices

```bash
uv run python -m piper.download_voices VOICE
# You can do this for the following voices:
# es_MX-claude-high
# ca_ES-upc_ona-medium
# en_GB-cori-high
```


# Other util things

## Connect bluetooth speaker

1. Install things:

```bash
sudo apt install -y bluez bluez-alsa-utils libasound2-plugin-bluez
```

2. Pair and connect the speaker:

```bash
bluetoothctl

# Tape the following commands:
power on
agent on
default-agent
scan on
# Locate your device and remember its MAC address
pair YOUR_MAC
trust YOUR_MAC
connect YOUR_MAC
scan off
exit
```

3. Test an audio file:

```bash
aplay -D bluealsa:DEV=YOUR_MAC,PROFILE=a2dp your_file.wav
```