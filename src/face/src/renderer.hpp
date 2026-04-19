
#pragma once

#include <expected>
#include <functional>
#include <string>

#include <SDL2/SDL.h>
#include <GLES3/gl3.h>

#include "nanovg.h"
#include "nanovg_gl.h"


template <typename T>
class Renderer
{
public:

    using FaceTappedCallback = std::function<void(int, int)>;

    // Construct with optional background color (NanoVG `NVGcolor`).
    Renderer():
        background_color(nvgRGBAf(0.902f, 0.737f, 0.776f, 1.0f))
    {}

    Renderer(NVGcolor bg):
        background_color(bg)
    {}

    auto init(int requested_width = 0, int requested_height = 0) -> std::expected<void, std::string>
    {
        if (SDL_Init(SDL_INIT_VIDEO) != 0) {
            return std::unexpected{"Failed to init SDL video subsystem: " + std::string(SDL_GetError())};
        }

        if (SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_ES) != 0) {
            return std::unexpected{"Failed to set SDL GL profile: " + std::string(SDL_GetError())};
        }

        if (SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 3) != 0) {
            return std::unexpected{"Failed to set GLES major version: " + std::string(SDL_GetError())};
        }

        if (SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 0) != 0) {
            return std::unexpected{"Failed to set GLES minor version: " + std::string(SDL_GetError())};
        }

        if (SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1) != 0) {
            return std::unexpected{"Failed to enable doublebuffer: " + std::string(SDL_GetError())};
        }

        Uint32 window_flags = SDL_WINDOW_OPENGL | SDL_WINDOW_SHOWN;
        int initial_width = 0;
        int initial_height = 0;

        if (requested_width > 0 && requested_height > 0) {
            initial_width = requested_width;
            initial_height = requested_height;
        } else {
            // Default to fullscreen desktop if no explicit size is provided.
            window_flags |= SDL_WINDOW_FULLSCREEN_DESKTOP;
        }

        window = SDL_CreateWindow(
            "NanoVG Eye FBO",
            SDL_WINDOWPOS_CENTERED,
            SDL_WINDOWPOS_CENTERED,
            initial_width,
            initial_height,
            window_flags
        );
        if (!window) {
            SDL_Quit();
            return std::unexpected{"Failed to create SDL window: " + std::string(SDL_GetError())};
        }

        SDL_ShowCursor(SDL_DISABLE);

        gl_context = SDL_GL_CreateContext(window);
        if (!gl_context) {
            destroy();
            return std::unexpected{"Failed to create OpenGL ES context: " + std::string(SDL_GetError())};
        }

        SDL_GL_GetDrawableSize(window, &drawable_width, &drawable_height);

        // VSYNC support varies by backend/driver; do not fail startup if unavailable.
        if (SDL_GL_SetSwapInterval(-1) != 0 && SDL_GL_SetSwapInterval(1) != 0) {
            SDL_GL_SetSwapInterval(0);
            SDL_LogWarn(
                SDL_LOG_CATEGORY_APPLICATION,
                "VSYNC unsupported for this driver, continuing with swap interval 0: %s",
                SDL_GetError()
            );
        }

        vg = nvgCreateGLES3(NVG_ANTIALIAS | NVG_STENCIL_STROKES);
        if (!vg) {
            return std::unexpected{"Failed to create NanoVG context"};
        }

        return {};
    }

    auto window_closed() -> bool
    {
        return should_close;
    }

    auto render(T& picture) -> void
    {
        picture.draw_offscreen(vg);

        SDL_Event event;
        while (SDL_PollEvent(&event) == 1) {
            handle_event(event);
        }

        SDL_GL_GetDrawableSize(window, &drawable_width, &drawable_height);

        if constexpr (requires(T& drawable) { drawable.set_size(0, 0); }) {
            picture.set_size(drawable_width, drawable_height);
        }

        glViewport(0, 0, drawable_width, drawable_height);
        // Use configured NanoVG color for background.
        glClearColor(background_color.r, background_color.g, background_color.b, background_color.a);
        glClear(GL_COLOR_BUFFER_BIT | GL_STENCIL_BUFFER_BIT);

        nvgBeginFrame(vg, drawable_width, drawable_height, 1.0f);
        picture.draw(vg);
        nvgEndFrame(vg);

        SDL_GL_SwapWindow(window);
    }

    auto destroy() -> void
    {
        if (vg) {
            nvgDeleteGLES3(vg);
            vg = nullptr;
        }

        if (gl_context) {
            SDL_GL_DeleteContext(gl_context);
            gl_context = nullptr;
        }

        if (window) {
            SDL_DestroyWindow(window);
            window = nullptr;
        }

        SDL_Quit();
    }

    auto context() -> NVGcontext*
    {
        return vg;
    }

    auto width() const -> int
    {
        return drawable_width;
    }

    auto height() const -> int
    {
        return drawable_height;
    }

    auto set_on_face_tapped(FaceTappedCallback callback) -> void
    {
        on_face_tapped = std::move(callback);
    }

private:

    auto emit_face_tapped(int x, int y) -> void
    {
        if (on_face_tapped) {
            on_face_tapped(x, y);
        }
    }

    auto handle_event(const SDL_Event& event) -> void
    {
        if (event.type == SDL_QUIT) {
            should_close = true;
        }

        if (event.type == SDL_KEYDOWN && event.key.keysym.sym == SDLK_ESCAPE) {
            should_close = true;
        }

        if (event.type == SDL_MOUSEBUTTONDOWN && event.button.button == SDL_BUTTON_LEFT) {
            // Ignore synthetic mouse events produced by touch to avoid duplicate logs.
            if (event.button.which != SDL_TOUCH_MOUSEID) {
                SDL_LogInfo(
                    SDL_LOG_CATEGORY_APPLICATION,
                    "Face click detected (mouse): x=%d y=%d",
                    event.button.x,
                    event.button.y
                );
                emit_face_tapped(event.button.x, event.button.y);
            }
        }

        if (event.type == SDL_FINGERDOWN) {
            const int tap_x = static_cast<int>(event.tfinger.x * static_cast<float>(drawable_width));
            const int tap_y = static_cast<int>(event.tfinger.y * static_cast<float>(drawable_height));
            SDL_LogInfo(
                SDL_LOG_CATEGORY_APPLICATION,
                "Face click detected (touch): x=%d y=%d",
                tap_x,
                tap_y
            );
            emit_face_tapped(tap_x, tap_y);
        }
    }

protected:

    SDL_Window* window{};
    SDL_GLContext gl_context{};
    NVGcontext* vg{};
    NVGcolor background_color{};
    FaceTappedCallback on_face_tapped{};
    bool should_close{false};
    int drawable_width{0};
    int drawable_height{0};

};