
#pragma once

#include <algorithm>
#include <chrono>
#include <cctype>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <expected>
#include <memory>
#include <span>
#include <string>
#include <unordered_map>
#include <vector>

#include <zmq.hpp>

#include "animations.hpp"


/**
 * Base class for handling incoming messages. Each message type (identified by a header)
 * should have a corresponding subclass of MessageHandler that implements the
 * handle(...) method.
 */
class MessageHandler {
public:

    virtual ~MessageHandler() = default;

    /**
     * Handle the incoming message payload. Returns an error message if handling fails.
     */
    virtual auto handle(const std::span<const std::byte> &payload)
        -> std::expected<void, std::string> = 0;
};


/**
 * Handles input from an external program via ZMQ.
 * Specifically, it subscribes to a PUB socket
 */
class Input {
public:

    Input(const std::string& endpoint):
        endpoint(endpoint)
    {}

    /**
     * Initializes the ZMQ subscriber socket. Returns an error message on failure.
     */
    auto init() -> std::expected<void, std::string>
    {
        try {
            zmq_socket.set(zmq::sockopt::subscribe, "");
            zmq_socket.connect(endpoint);
        } catch (const zmq::error_t& e) {
            return std::unexpected{std::string{"ZMQ init failed: "} + e.what()};
        }
        return {};
    }

    /**
     * Reads all available messages from the ZMQ socket and dispatches them to the
     * appropriate handlers. Returns an error message if message handling fails.
     */
    auto read() -> std::expected<void, std::string>
    {
        while (true) {
            zmq::message_t msg;
            try {
                const zmq::recv_result_t received = zmq_socket.recv(
                    msg,
                    zmq::recv_flags::dontwait
                );
                if (!received.has_value() || msg.size() == 0) {
                    break;
                }
            } catch (const zmq::error_t& e) {
                if (e.num() == EAGAIN) {
                    break;
                }
                return std::unexpected{std::string{"ZMQ receive failed: "} + e.what()};
            }
            return handle_message(msg);
        }
        return {};
    }

    /**
     * Registers a message handler for a specific header. When a message is received,
     * the header is parsed and the corresponding handler is invoked with the message
     * payload.
     */
    auto register_handler(const std::string& header, std::unique_ptr<MessageHandler> handler) -> void
    {
        handlers[header] = std::move(handler);
    }

private:

    /**
     * Parses the message header and payload, and dispatches to the appropriate handler.
     */
    auto handle_message(const zmq::message_t& msg) -> std::expected<void, std::string>
    {
        const auto* data = static_cast<const unsigned char*>(msg.data());

        // Header is everything until first whitespace.
        const auto* sep_it = std::find_if(
            data,
            data + msg.size(),
            [](unsigned char ch) {
                return std::isspace(ch) != 0;
            }
        );
        const std::size_t header_length = static_cast<std::size_t>(sep_it - data);

        if (header_length == msg.size()) {
            return std::unexpected{"Missing header/payload separator"};
        }

        const std::string header(reinterpret_cast<const char*>(data), header_length);

        auto it = handlers.find(header);
        if (it == handlers.end()) {
            return std::unexpected{"No handler for message header: " + header};
        }

        // Payload is bytes after the first whitespace.
        const std::byte* payload_data = reinterpret_cast<const std::byte*>(data + header_length + 1);
        const std::size_t payload_size = msg.size() - (header_length + 1);

        return it->second->handle(std::span<const std::byte>(payload_data, payload_size));
    }

    std::string endpoint;
    zmq::context_t zmq_context;
    zmq::socket_t zmq_socket{zmq_context, zmq::socket_type::sub};
    std::unordered_map<std::string, std::unique_ptr<MessageHandler>> handlers;

};


/**
 * Message handler for speech keyframe messages. It decodes the incoming payload
 * into a series of keyframes (timestamp and amplitude pairs) and adds a new
 * KeyframeLinearAnimation to the AnimationController with these keyframes.
 */
class SpeechMessageHandler final : public MessageHandler {
public:

    explicit SpeechMessageHandler(
        const std::shared_ptr<AnimationController> &animation_controller,
        const std::shared_ptr<MouthGraphic> &mouth_graphic
    ):
        animation_controller(animation_controller),
        mouth_graphic(mouth_graphic)
    {}

    /**
     * The payload format is expected to be:
     * [int32_t sample_count][int32_t timestamp_us][float amplitude]...
     * The first 4 bytes represent the number of samples, followed by that many
     * pairs of timestamp (in microseconds) and amplitude (float).
     */
    auto handle(const std::span<const std::byte> &payload)
        -> std::expected<void, std::string> override
    {
        if (!animation_controller) {
            return std::unexpected{"AnimationController is null"};
        }

        std::size_t offset = 0;
        auto count_result = read_value<int32_t>(payload, offset);
        if (!count_result) {
            return std::unexpected{count_result.error()};
        }

        const int32_t sample_count = *count_result;
        if (sample_count < 0) {
            return std::unexpected{"Invalid sample count: negative value"};
        }

        std::vector<KeyframeLinearAnimation::Sample> samples;
        samples.reserve(static_cast<std::size_t>(sample_count));

        for (int32_t i = 0; i < sample_count; ++i) {
            auto time_us_result = read_value<int32_t>(payload, offset);
            if (!time_us_result) {
                return std::unexpected{time_us_result.error()};
            }

            auto value_result = read_value<float>(payload, offset);
            if (!value_result) {
                return std::unexpected{value_result.error()};
            }

            const auto dt = std::chrono::microseconds(*time_us_result);
            samples.emplace_back(
                std::chrono::duration_cast<Duration>(dt),
                *value_result
            );
        }

        if (offset != payload.size()) {
            return std::unexpected{"Payload contains trailing bytes"};
        }

        animation_controller->add(
            std::make_unique<MouthAnimation>(mouth_graphic, std::move(samples))
        );

        return {};
    }

private:

    /**
     * Helper function to read a value of type T from the payload at the given offset.
     * It checks for sufficient bytes, copies the data into a T variable, and advances
     * the offset. Returns an error if the payload is too short.
     */
    template <typename T>
    auto read_value(const std::span<const std::byte>& payload, std::size_t& offset)
        -> std::expected<T, std::string>
    {
        if (offset + sizeof(T) > payload.size()) {
            return std::unexpected{"Payload too short while decoding"};
        }

        T value{};
        std::memcpy(&value, payload.data() + offset, sizeof(T));
        offset += sizeof(T);
        return value;
    }

    std::shared_ptr<AnimationController> animation_controller;
    std::shared_ptr<MouthGraphic> mouth_graphic;

};
