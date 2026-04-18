#pragma once

#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <expected>
#include <iostream>
#include <memory>
#include <span>
#include <string>
#include <unordered_map>

#include <nats/nats.h>

#include "animations.hpp"


/**
 * Base class for handling incoming NATS message payloads.
 */
class MessageHandler {
public:

	virtual ~MessageHandler() = default;

	virtual auto handle(const std::span<const std::byte>& payload)
		-> std::expected<void, std::string> = 0;
};


/**
 * Message handler for speech keyframe messages.
 */
class SpeechMessageHandler final : public MessageHandler {
public:

	explicit SpeechMessageHandler(
		const std::shared_ptr<AnimationController>& animation_controller,
		const std::shared_ptr<MouthGraphic>& mouth_graphic
	):
		animation_controller(animation_controller),
		mouth_graphic(mouth_graphic)
	{}

	auto handle(const std::span<const std::byte>& payload)
		-> std::expected<void, std::string> override
	{
		if (!animation_controller) {
			return std::unexpected{"AnimationController is null"};
		}

		std::size_t offset = 0;
		auto count_result = read_value<std::int32_t>(payload, offset);
		if (!count_result) {
			return std::unexpected{count_result.error()};
		}

		const std::int32_t sample_count = *count_result;
		if (sample_count < 0) {
			return std::unexpected{"Invalid sample count: negative value"};
		}

		std::vector<KeyframeLinearAnimation::Sample> samples;
		samples.reserve(static_cast<std::size_t>(sample_count));

		for (std::int32_t i = 0; i < sample_count; ++i) {
			auto time_us_result = read_value<std::int32_t>(payload, offset);
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


class NatsConnectionManager {
public:

	explicit NatsConnectionManager(const std::string& server_url):
		server_url_(server_url)
	{}

	~NatsConnectionManager()
	{
		disconnect();
	}

	NatsConnectionManager(const NatsConnectionManager&) = delete;
	auto operator=(const NatsConnectionManager&) -> NatsConnectionManager& = delete;
	NatsConnectionManager(NatsConnectionManager&&) = delete;
	auto operator=(NatsConnectionManager&&) -> NatsConnectionManager& = delete;

	auto is_connected() const -> bool
	{
		return state_ == State::Connected;
	}

	auto face_tapped(int x, int y) -> void
	{
		if (state_ != State::Connected || connection_ == nullptr) {
			return;
		}

		const FaceTappedPayload payload{
			.x = static_cast<std::int32_t>(x),
			.y = static_cast<std::int32_t>(y),
		};

		const natsStatus status = natsConnection_Publish(
			connection_,
			"maia.interaction.toggle",
			reinterpret_cast<const char*>(&payload),
			static_cast<int>(sizeof(payload))
		);
		if (status != NATS_OK) {
			std::cerr << "NATS publish failed: " << natsStatus_GetText(status) << std::endl;
		}
	}

	auto register_handler(const std::string& subject, std::unique_ptr<MessageHandler> handler) -> void
	{
		if (!handler) {
			std::cerr << "NATS register_handler failed: null handler for subject " << subject << std::endl;
			return;
		}

		auto existing = handlers_.find(subject);
		if (existing != handlers_.end()) {
			if (existing->second.subscription != nullptr) {
				natsSubscription_Destroy(existing->second.subscription);
				existing->second.subscription = nullptr;
			}
			handlers_.erase(existing);
		}

		HandlerEntry entry{};
		entry.handler = std::move(handler);

		if (state_ == State::Connected && connection_ != nullptr) {
			auto subscribe_result = subscribe_subject(subject, entry);
			if (!subscribe_result) {
				std::cerr << subscribe_result.error() << std::endl;
			}
		}

		handlers_.emplace(subject, std::move(entry));
	}

	auto tick() -> void
	{
		switch (state_) {
			case State::Disconnected:
				handle_disconnected();
				return;

			case State::Connected:
				handle_connected();
				return;
		}
	}

private:

	enum class State {
		Disconnected,
		Connected,
	};

	struct FaceTappedPayload {
		std::int32_t x;
		std::int32_t y;
	};

	struct HandlerEntry {
		std::unique_ptr<MessageHandler> handler;
		natsSubscription* subscription{nullptr};
	};

	auto disconnect() -> void
	{
		for (auto& [subject, entry] : handlers_) {
			if (entry.subscription != nullptr) {
				natsSubscription_Destroy(entry.subscription);
				entry.subscription = nullptr;
			}
		}

		if (connection_ != nullptr) {
			natsConnection_Destroy(connection_);
			connection_ = nullptr;
		}
		set_state(State::Disconnected);
	}

	auto set_state(State new_state) -> void
	{
		if (state_ == new_state) {
			return;
		}

		const char* from = (state_ == State::Connected) ? "connected" : "disconnected";
		const char* to = (new_state == State::Connected) ? "connected" : "disconnected";
		std::cerr << "NATS state change: " << from << " -> " << to << std::endl;
		state_ = new_state;
	}

	auto handle_disconnected() -> void
	{
		const auto now = std::chrono::steady_clock::now();
		if (now < next_connect_attempt_) {
			return;
		}

		natsConnection* connection = nullptr;
		natsStatus status = natsConnection_ConnectTo(&connection, server_url_.c_str());
		if (status != NATS_OK) {
			next_connect_attempt_ = now + reconnect_interval_;
			return;
		}

		auto subscribe_all_result = subscribe_all_handlers(connection);
		if (!subscribe_all_result) {
			std::cerr << subscribe_all_result.error() << std::endl;
			natsConnection_Destroy(connection);
			next_connect_attempt_ = now + reconnect_interval_;
			return;
		}

		connection_ = connection;
		set_state(State::Connected);
	}

	auto handle_connected() -> void
	{
		if (natsConnection_Status(connection_) != NATS_CONN_STATUS_CONNECTED) {
			disconnect();
			next_connect_attempt_ = std::chrono::steady_clock::now() + reconnect_interval_;
			return;
		}

		constexpr int max_messages_per_tick = 32;

		int processed = 0;
		while (processed < max_messages_per_tick) {
			bool received_any = false;

			for (auto& [subject, entry] : handlers_) {
				if (entry.subscription == nullptr || entry.handler == nullptr) {
					continue;
				}

				natsMsg* msg = nullptr;
				natsStatus status = natsSubscription_NextMsg(&msg, entry.subscription, 0);
				if (status == NATS_TIMEOUT) {
					continue;
				}

				if (status != NATS_OK) {
					std::cerr << "NATS receive failed for subject " << subject << ": "
						<< natsStatus_GetText(status) << std::endl;
					disconnect();
					next_connect_attempt_ = std::chrono::steady_clock::now() + reconnect_interval_;
					return;
				}

				received_any = true;
				++processed;

				auto dispatch_result = dispatch_message(*entry.handler, msg);
				natsMsg_Destroy(msg);
				if (!dispatch_result) {
					std::cerr << "NATS message handling failed for subject " << subject
						<< ": " << dispatch_result.error() << std::endl;
				}

				if (processed >= max_messages_per_tick) {
					break;
				}
			}

			if (!received_any) {
				return;
			}
		}
	}

	auto subscribe_subject(const std::string& subject, HandlerEntry& entry)
		-> std::expected<void, std::string>
	{
		natsSubscription* subscription = nullptr;
		natsStatus status = natsConnection_SubscribeSync(&subscription, connection_, subject.c_str());
		if (status != NATS_OK) {
			return std::unexpected{
				"NATS subscribe failed for subject " + subject + ": " + natsStatus_GetText(status)
			};
		}

		entry.subscription = subscription;
		return {};
	}

	auto subscribe_all_handlers(natsConnection* connection) -> std::expected<void, std::string>
	{
		connection_ = connection;
		for (auto& [subject, entry] : handlers_) {
			auto subscribe_result = subscribe_subject(subject, entry);
			if (!subscribe_result) {
				for (auto& [cleanup_subject, cleanup_entry] : handlers_) {
					if (cleanup_entry.subscription != nullptr) {
						natsSubscription_Destroy(cleanup_entry.subscription);
						cleanup_entry.subscription = nullptr;
					}
				}
				connection_ = nullptr;
				return std::unexpected{subscribe_result.error()};
			}
		}
		return {};
	}

	auto dispatch_message(
		MessageHandler& handler,
		const natsMsg* msg
	) -> std::expected<void, std::string>
	{
		const char* raw_data = natsMsg_GetData(msg);
		const int raw_size = natsMsg_GetDataLength(msg);
		if (raw_size < 0) {
			return std::unexpected{"Received invalid message size"};
		}

		const auto* payload = reinterpret_cast<const std::byte*>(raw_data);
		return handler.handle(std::span<const std::byte>(payload, static_cast<std::size_t>(raw_size)));
	}

	std::string server_url_;
	State state_{State::Disconnected};
	std::chrono::milliseconds reconnect_interval_{1000};
	std::chrono::steady_clock::time_point next_connect_attempt_{};

	natsConnection* connection_{nullptr};
	std::unordered_map<std::string, HandlerEntry> handlers_;
};
