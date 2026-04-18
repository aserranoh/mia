
#pragma once

#include <chrono>
#include <memory>
#include <list>
#include <algorithm>
#include <optional>
#include <random>
#include <string>
#include <vector>

#include "graphics.hpp"


using TimePoint = std::chrono::high_resolution_clock::time_point;
using Duration = std::chrono::high_resolution_clock::duration;


/**
 * Base class for animations.
 */
class Animation {
public:

    std::string name;

    explicit Animation(const std::string& name) : name(name) {}
    virtual ~Animation() = default;

    /**
     * Advance the animation to the current time.
     * Returns true if the animation is complete and should be removed.
     */
    virtual auto step(const TimePoint& now) -> bool = 0;

    /**
     * Reset the animation state.
     */
    virtual auto reset() -> void {}

};



/**
 * Controller for managing multiple animations.
 */
class AnimationController {
public:

    /**
     * Add a new animation to the controller.
     */
    auto add(std::unique_ptr<Animation> animation) -> void
    {
        animations.emplace_back(std::move(animation));
    }

    /**
     * Remove an animation by name.
     * Returns true if an animation was removed, false if not found.
     */
    auto remove(const std::string& animation_name) -> bool
    {
        auto it = std::find_if(
            animations.begin(),
            animations.end(),
            [&](const auto& animation){ return animation->name == animation_name; }
        );
        if (it == animations.end()) {
            return false;
        }
        animations.erase(it);
        return true;
    }

    /**
     * Advance all animations using the current timestamp.
     * Animations whose step(...) returns true are removed.
     */
    auto step() -> void
    {
        const TimePoint now = std::chrono::high_resolution_clock::now();
        animations.remove_if([&](auto& animation) {
            return animation && animation->step(now);
        });
    }

    /**
     * Clear all animations.
     */
    auto clear() noexcept -> void
    {
        animations.clear();
    }

private:

    std::list<std::unique_ptr<Animation>> animations;

};


/**
 * An animation that produces a triangle wave pattern.
 * The value oscillates between 0 and max_value over the specified period.
 * If repeat is true, the animation will loop indefinitely;
 * otherwise, it will complete after one cycle.
 */
class TriangleWaveAnimation final : public Animation {
public:
    
    TriangleWaveAnimation(Duration period, float max_value, bool repeat):
        Animation("TriangleWaveAnimation"),
        period(period),
        max_value(max_value),
        repeat(repeat),
        start_time(std::chrono::high_resolution_clock::now())
    {
        value = 0.0f;
    }

    /**
     * Get the current value of the animation.
     */
    auto get_value() const -> float
    {
        return value;
    }

    auto reset() -> void override
    {
        value = 0.0f;
        start_time = std::chrono::high_resolution_clock::now();
    }

    /**
     * Advance the animation to the current time and update the value.
     * Returns true if the animation is complete and should be removed.
     */
    auto step(const TimePoint& now) -> bool override
    {
        if (period <= Duration::zero()) {
            value = 0.0f;
            return !repeat;
        }

        auto elapsed = now - start_time;
        if (!repeat && elapsed >= period) {
            value = 0.0f;
            return true;
        }

        if (repeat) {
            elapsed = elapsed % period;
        }

        const auto half_period = period / 2;
        if (half_period <= Duration::zero()) {
            value = 0.0f;
            return false;
        }

        const float t = std::chrono::duration<float>(elapsed).count();
        const float half_t = std::chrono::duration<float>(half_period).count();

        if (t <= half_t) {
            value = (t / half_t) * max_value;
        } else {
            const float descending_t = (2.0f * half_t) - t;
            value = (descending_t / half_t) * max_value;
        }

        return false;
    }

private:

    float value = 0.0f;
    Duration period;
    float max_value = 0.0f;
    bool repeat = false;
    TimePoint start_time;

};


/**
 * An animation that linearly interpolates a value between a start and target
 * value over a specified period.
 *
 * The value progresses from start_value to target_value as time advances.
 * When the period has elapsed, the animation completes and step(...) returns true.
 */
class LinearAnimation final : public Animation {
public:

    LinearAnimation(Duration period, float start_value, float target_value):
        Animation("LinearAnimation"),
        value(start_value),
        period(period),
        start_value(start_value),
        target_value(target_value),
        start_time(std::chrono::high_resolution_clock::now())
    {}

    /**
     * Get the current value of the animation.
     */
    auto get_value() const -> float
    {
        return value;
    }

    /**
     * Reset the animation to the starting value.
     */
    auto reset() -> void override
    {
        reset(std::chrono::high_resolution_clock::now());
    }

	/**
	 * Reset the animation to the starting value, using an explicit timestamp.
	 */
	auto reset(const TimePoint& now) -> void
	{
		value = start_value;
		start_time = now;
	}

    /**
     * Update the animation parameters and reset it.
     */
    auto set_values(
        Duration new_period,
        float new_start_value,
        float new_target_value
    ) -> void {
        period = new_period;
        start_value = new_start_value;
        target_value = new_target_value;
        reset();
    }

    /**
     * Advance the animation to the current time and update the value.
     * Returns true if the animation is complete and should be removed.
     */
    auto step(const TimePoint& now) -> bool override
    {
        if (period <= Duration::zero()) {
            value = target_value;
            return true;
        }

        const auto elapsed = now - start_time;
        if (elapsed >= period) {
            value = target_value;
            return true;
        }

        const float t = std::chrono::duration<float, std::milli>(elapsed).count();
        const float total = std::chrono::duration<float, std::milli>(period).count();
        if (total <= 0.0f) {
            value = target_value;
            return true;
        }

        const float alpha = t / total;
        value = start_value + (target_value - start_value) * alpha;
        return false;
    }

private:

    float value = 0.0f;
    Duration period;
    float start_value = 0.0f;
    float target_value = 0.0f;
    TimePoint start_time;

};


/**
 * A piecewise linear animation defined by keyframe samples.
 *
 * The constructor receives a vector of (absolute_time, value) samples.
 * The first sample's absolute_time is forced to zero.
 *
 * For each segment between samples S[n] and S[n+1], the animation linearly
 * interpolates from S[n].value to S[n+1].value over
 * (S[n+1].absolute_time - S[n].absolute_time).
 */
class KeyframeLinearAnimation final : public Animation {
public:

    using Sample = std::pair<Duration, float>;

    KeyframeLinearAnimation(const std::string& name, std::vector<Sample> samples):
        Animation(name),
        samples(std::move(samples)),
		segment(Duration::zero(), 0.0f, 0.0f)
    {
        normalize_samples();
        reset();
    }

    /**
     * Get the current value of the animation.
     */
    auto get_value() const -> float
    {
        return value;
    }

    /**
     * Reset the animation to the first sample.
     */
    auto reset() -> void override
    {
        segment_index = 0;
        value = samples.empty() ? 0.0f : samples.front().second;
		segment_start = std::chrono::high_resolution_clock::now();
		finished = (samples.size() <= 1);
        if (!finished) {
            setup_segment(segment_start);
        }
    }

    /**
     * Advance the animation. Returns true once the last sample is reached.
     */
    auto step(const TimePoint& now) -> bool override
    {
		if (finished) {
			return true;
		}
		if (samples.size() <= 1) {
			finished = true;
			return true;
		}

		while (true) {
			if (segment_index + 1 >= samples.size()) {
				value = samples.back().second;
				finished = true;
				return true;
			}

            const bool segment_finished = segment.step(now);
            value = segment.get_value();
			if (!segment_finished) {
				return false;
			}

			segment_index++;
			if (segment_index + 1 >= samples.size()) {
				value = samples.back().second;
				finished = true;
				return true;
			}

			segment_start = now;
			setup_segment(segment_start);
			// Continue the loop to naturally skip 0-duration segments.
		}
    }

private:

    /**
    * Ensure the first sample has an absolute_time of zero, and if there are no samples,
     * add a default sample with value 0.0f.
     */
    auto normalize_samples() -> void
    {
        if (samples.empty()) {
            samples.emplace_back(Duration::zero(), 0.0f);
            return;
        }
        samples.front().first = Duration::zero();
    }

    auto setup_segment(const TimePoint& now) -> void
    {
        const float start_value = samples[segment_index].second;
        const float target_value = samples[segment_index + 1].second;

        const Duration start_time = samples[segment_index].first;
        const Duration target_time = samples[segment_index + 1].first;
        const Duration segment_duration = std::max(
            Duration::zero(),
            target_time - start_time
        );

		segment.set_values(segment_duration, start_value, target_value);
		segment.reset(now);
    }

    std::vector<Sample> samples;
    std::size_t segment_index = 0;
    float value = 0.0f;
    TimePoint segment_start;
    bool finished = false;
	LinearAnimation segment;

};


/**
 * An animation that simulates eye blinking by controlling the closed factor
 * of an EyeGraphic.
 */
class EyesBlinkAnimation final : public Animation {
public:

    EyesBlinkAnimation(
        const std::string& name,
        std::shared_ptr<EyeGraphic> left_eye,
        std::shared_ptr<EyeGraphic> right_eye,
        Duration blink_duration,
        Duration time_between_blinks
    ):
        Animation(name),
        left_eye(std::move(left_eye)),
        right_eye(std::move(right_eye)),
        blink_duration(blink_duration),
        time_between_blinks(time_between_blinks),
        triangle(blink_duration, 1.0f, false),
        state(State::not_blinking),
        next_delay(compute_random_delay()),
        state_start(std::chrono::high_resolution_clock::now())
    {}

    /**
     * Advance the animation to the current time, updating the eye's closed factor.
     */
    auto step(const TimePoint& now) -> bool override
    {
        if (!left_eye || !right_eye) {
            return false;
        }

        if (state == State::blinking) {
            do_state_blinking(now);
        } else {
            do_state_not_blinking(now);
        }
        return false;
    }

private:

    enum class State {
        blinking,
        not_blinking,
    };

    /**
     * Compute a random delay for the next blink, based on the configured time_between_blinks.
     * The actual delay is jittered by ±10% to create a more natural blinking pattern.
     * If time_between_blinks is zero or negative, returns zero (no delay).
     */
    auto compute_random_delay() -> Duration
    {
        if (time_between_blinks <= Duration::zero()) {
            return Duration::zero();
        }
        std::uniform_real_distribution<double> dist(0.9, 1.1);
        const double factor = dist(rng);
        const auto base_seconds = std::chrono::duration<double>(time_between_blinks).count();
        const auto jittered_seconds = base_seconds * factor;
        return std::chrono::duration_cast<Duration>(std::chrono::duration<double>(jittered_seconds));
    }

    /**
     * Perform the blinking step, updating the eye's closed factor based on the triangle
     * wave.
     * If the triangle animation is finished, transition back to the not_blinking state.
     */
    auto do_state_blinking(const TimePoint& now) -> void
    {
        const bool finished = triangle.step(now);
        left_eye->set_closed(triangle.get_value());
        right_eye->set_closed(triangle.get_value());
        if (finished) {
            state = State::not_blinking;
            state_start = now;
            next_delay = compute_random_delay();
        }
    }

    /**
     * Perform the not_blinking step, checking if it's time to start a new blink.
     * If the next_delay has elapsed, transition to the blinking state
     * and reset the triangle animation.
     */
    auto do_state_not_blinking(const TimePoint& now) -> void
    {
        const auto elapsed = now - state_start;
        if (elapsed >= next_delay) {
            triangle.reset();
            state = State::blinking;
            state_start = now;
        }
    }

    std::shared_ptr<EyeGraphic> left_eye;
    std::shared_ptr<EyeGraphic> right_eye;
    Duration blink_duration;
    Duration time_between_blinks;
    TriangleWaveAnimation triangle;
    State state;
    TimePoint state_start;
    Duration next_delay;
    std::mt19937 rng{std::random_device{}()};

};


/**
 * An animation that drives a MouthGraphic using a KeyframeLinearAnimation.
 */
class MouthAnimation final : public Animation {
public:

    MouthAnimation(
        std::shared_ptr<MouthGraphic> mouth,
        std::vector<KeyframeLinearAnimation::Sample> samples
    ):
        Animation("MouthAnimation"),
        mouth(std::move(mouth)),
        keyframes("MouthKeyframes", std::move(samples))
    {
        if (this->mouth) {
            this->mouth->set_speaking(true);
        }
    }

    auto step(const TimePoint& now) -> bool override
    {
        if (!mouth) {
            return true;
        }

        const bool finished = keyframes.step(now);
        mouth->set_closed(keyframes.get_value());
        if (finished) {
            // Ensure mouth is fully closed at the end of the animation.
            mouth->set_closed(1.0f);
            mouth->set_speaking(false);
        }
        return finished;
    }

private:

    std::shared_ptr<MouthGraphic> mouth;
    KeyframeLinearAnimation keyframes;

};
