
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
#include "input.hpp"
#include "renderer.hpp"


Renderer<FaceGraphic> renderer;
FaceGraphic face(800, 600);
std::shared_ptr<AnimationController> animation_controller = std::make_shared<AnimationController>();
Input input{"tcp://127.0.0.1:5555"};


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


/**
 * Initialization.
 */
auto init() -> std::expected<void, std::string>
{
    std::expected<void, std::string> result = renderer.init();
    if (!result) {
        return std::unexpected{result.error()};
    }

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

    // Speech amplitude input (PUB on external program, SUB here).
    // Default endpoint can be adjusted later or made configurable.
    auto input_result = input.init();
    if (!input_result) {
        return std::unexpected{input_result.error()};
    }

    input.register_handler(
        "face/speech",
        std::make_unique<SpeechMessageHandler>(animation_controller, face.get_mouth())
    );

    return {};
}


/**
 * Main loop.
 */
auto main_loop() -> void
{
    while (!renderer.window_closed()) {
        const std::expected<void, std::string> input_result = input.read();
        if (!input_result) {
            std::cerr << input_result.error() << std::endl;
        }
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

    std::expected<void, std::string> init_result = init();
    if (!init_result) {
        std::cerr << init_result.error() << std::endl;
        return -1;
    }

    main_loop();

    destroy();
    return 0;
}
