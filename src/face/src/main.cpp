
#include <expected>
#include <iostream>
#include <list>
#include <memory>
#include <optional>
#include <string>

#include <SDL2/SDL.h>

#include "nanovg.h"

#include "animations.hpp"
#include "graphics.hpp"
#include "nats.hpp"
#include "renderer.hpp"


Renderer<FaceGraphic> renderer;
FaceGraphic face;
std::shared_ptr<AnimationController> animation_controller = std::make_shared<AnimationController>();
NatsConnectionManager nats_connection{"nats://127.0.0.1:4222"};


auto parse_video_driver(int argc, char** argv) -> std::expected<std::optional<std::string>, std::string>
{
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg.rfind("--video-driver=", 0) == 0) {
            const std::string value = arg.substr(std::string("--video-driver=").size());
            if (value == "auto") {
                return std::optional<std::string>{};
            }
            if (value == "x11" || value == "wayland" || value == "kmsdrm") {
                return value;
            }
            return std::unexpected{"Invalid --video-driver value: " + value + ". Use auto|x11|wayland|kmsdrm."};
        }

        if (arg == "--video-driver") {
            if (i + 1 >= argc) {
                return std::unexpected{"Missing value for --video-driver. Use auto|x11|wayland|kmsdrm."};
            }

            const std::string value = argv[++i];
            if (value == "auto") {
                return std::optional<std::string>{};
            }
            if (value == "x11" || value == "wayland" || value == "kmsdrm") {
                return value;
            }
            return std::unexpected{"Invalid --video-driver value: " + value + ". Use auto|x11|wayland|kmsdrm."};
        }
    }

    return std::optional<std::string>{};
}


auto configure_video_driver(const std::optional<std::string>& driver) -> std::expected<void, std::string>
{
    if (!driver.has_value()) {
        return {};
    }

    if (SDL_setenv("SDL_VIDEODRIVER", driver->c_str(), 1) != 0) {
        return std::unexpected{"Failed to set SDL_VIDEODRIVER: " + std::string(SDL_GetError())};
    }

    return {};
}


auto parse_window_size(int argc, char** argv, int& window_width, int& window_height) -> std::expected<void, std::string>
{
    auto parse_size = [](const std::string& value, int& width, int& height) -> std::expected<void, std::string> {
        const std::size_t separator_pos = value.find('x');
        if (separator_pos == std::string::npos) {
            return std::unexpected{"Invalid --window-size format: " + value + ". Use WIDTHxHEIGHT, e.g. 800x480."};
        }

        try {
            width = std::stoi(value.substr(0, separator_pos));
            height = std::stoi(value.substr(separator_pos + 1));
        } catch (const std::exception&) {
            return std::unexpected{"Invalid --window-size format: " + value + ". Use WIDTHxHEIGHT, e.g. 800x480."};
        }

        if (width <= 0 || height <= 0) {
            return std::unexpected{"Invalid --window-size values: " + value + ". Width and height must be > 0."};
        }

        return {};
    };

    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg.rfind("--window-size=", 0) == 0) {
            const std::string value = arg.substr(std::string("--window-size=").size());
            auto parsed_result = parse_size(value, window_width, window_height);
            if (!parsed_result) {
                return std::unexpected{parsed_result.error()};
            }
            return {};
        }

        if (arg == "--window-size") {
            if (i + 1 >= argc) {
                return std::unexpected{"Missing value for --window-size. Use WIDTHxHEIGHT, e.g. 800x480."};
            }

            const std::string value = argv[++i];
            auto parsed_result = parse_size(value, window_width, window_height);
            if (!parsed_result) {
                return std::unexpected{parsed_result.error()};
            }
            return {};
        }
    }

    return {};
}


/**
 * Initialization.
 */
auto init(int window_width, int window_height) -> std::expected<void, std::string>
{
    std::expected<void, std::string> result = renderer.init(window_width, window_height);
    if (!result) {
        return std::unexpected{result.error()};
    }

    face.set_size(renderer.width(), renderer.height());

    std::expected<void, std::string> eyes_shape_result = face.set_eyes_shape(
        renderer.context(),
        150, // Eye width
        100, // Eye height
        50,  // Pupil diameter
        200, // Distance between eyes
        -50, // Vertical offset of eyes from center
        50   // Eye corner radius
    );
    if (!eyes_shape_result) {
        return std::unexpected{eyes_shape_result.error()};
    }

    face.set_mouth_shape(
        130,                 // Mouth width
        70,                  // Mouth height
        35.0f,               // Mouth corner radius
        10.0f,               // Lips thickness
        160.0f,              // Vertical offset of mouth from center
        nvgRGB(30, 30, 30)   // Mouth color
    );

    animation_controller->add(std::make_unique<EyesBlinkAnimation>(
        "blink-animation",
        face.get_left_eye(),
        face.get_right_eye(),
        std::chrono::milliseconds(400), // Blink duration
        std::chrono::milliseconds(3000) // Average time between blinks
    ));

    nats_connection.register_handler(
        "maia.mouth",
        std::make_unique<SpeechMessageHandler>(animation_controller, face.get_mouth())
    );

    renderer.set_on_face_tapped(
        [](int x, int y) {
            nats_connection.face_tapped(x, y);
        }
    );

    return {};
}


/**
 * Main loop.
 */
auto main_loop() -> void
{
    while (!renderer.window_closed()) {
        nats_connection.tick();
        animation_controller->step();
        renderer.render(face);
    }
}


/**
 * Cleanup resources.
 */
auto destroy() -> void
{
    face.destroy();
    renderer.destroy();
}


int main(int argc, char** argv)
{
    int window_width = 0;
    int window_height = 0;

    auto video_driver_result = parse_video_driver(argc, argv);
    if (!video_driver_result) {
        std::cerr << video_driver_result.error() << std::endl;
        return -1;
    }

    auto configure_driver_result = configure_video_driver(video_driver_result.value());
    if (!configure_driver_result) {
        std::cerr << configure_driver_result.error() << std::endl;
        return -1;
    }

    auto window_size_result = parse_window_size(argc, argv, window_width, window_height);
    if (!window_size_result) {
        std::cerr << window_size_result.error() << std::endl;
        return -1;
    }

    std::expected<void, std::string> init_result = init(window_width, window_height);
    if (!init_result) {
        std::cerr << init_result.error() << std::endl;
        return -1;
    }

    main_loop();

    destroy();
    return 0;
}
