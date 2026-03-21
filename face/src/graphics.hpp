
#pragma once

#include <algorithm>
#include <cmath>
#include <expected>
#include <memory>
#include <string>

#include <GLES3/gl3.h>

#include "nanovg.h"
#include "nanovg_gl_utils.h"


constexpr float K_MIN_EYE_SCALE_Y = 0.05f;
constexpr float K_MIN_MOUTH_SCALE_Y = 0.001f;


/**
 * Represents a single eye graphic.
 */
class EyeGraphic
{
public:

    /**
     * Initializes the eye graphic by creating an offscreen framebuffer (FBO)
     * to render the eye into.
     */
    auto init(
        NVGcontext *vg,
        int width,
        int height,
        float pupil_diameter,
        float corner_radius
    ) -> std::expected<void, std::string>
    {
        this->width = width;
        this->height = height;
        this->pupil_diameter = pupil_diameter;
        this->corner_radius = corner_radius;

        destroy(); // Clean up existing FBO if it exists

        const int image_flags = 0;
        fbo = nvgluCreateFramebuffer(vg, width, height, image_flags);
        if (!fbo) {
            return std::unexpected{"Failed to create FBO for eye"};
        }
        return {};
    }

    /**
     * Draws the eye into the offscreen framebuffer. This involves two steps:
     * 1️⃣ Drawing the white eye shape, which defines the alpha mask for the eye.
     * 2️⃣ Drawing the black pupil, but only keeping pixels that are inside the existing
     * alpha mask (using NVG_SOURCE_IN composite operation).
     */
    auto draw_offscreen(NVGcontext *vg) -> void
    {
        nvgluBindFramebuffer(fbo);
        glViewport(0, 0, width, height);
        glClearColor(0, 0, 0, 0);
        glClear(GL_COLOR_BUFFER_BIT | GL_STENCIL_BUFFER_BIT);

        const float device_pixel_ratio = 1.0f;
        nvgBeginFrame(vg, width, height, device_pixel_ratio);

        // Ensure we start from a known compositing state.
        nvgGlobalCompositeOperation(vg, NVG_SOURCE_OVER);

        // 1️⃣ Draw white eye shape (defines alpha mask)
        const NVGcolor eyeball_color = nvgRGB(255, 255, 255);

        // Scale only the eye mask in Y based on eye openness.
        // closed_factor: 0 = open, 1 = closed
        const float openness = 1.0f - closed_factor;
        const float eye_scale_y = std::max(openness, K_MIN_EYE_SCALE_Y);

        nvgSave(vg);
        // Scale around the vertical center so the eyelid closes symmetrically.
        nvgTranslate(vg, 0.0f, height * 0.5f);
        nvgScale(vg, 1.0f, eye_scale_y);
        nvgTranslate(vg, 0.0f, -height * 0.5f);

        nvgBeginPath(vg);
        nvgRoundedRect(vg, 0, 0, width, height, corner_radius);
        nvgFillColor(vg, eyeball_color);
        nvgFill(vg);

        // Restore transform so only the mask is scaled.
        nvgRestore(vg);

        // 2️⃣ Only keep pixels inside existing alpha
        nvgGlobalCompositeOperation(vg, NVG_SOURCE_IN);

        const float pupil_center_x = width * 0.5f + pupil_offset_x;
        const float pupil_center_y = height * 0.5f + pupil_offset_y;

        nvgBeginPath(vg);
        nvgCircle(vg, pupil_center_x, pupil_center_y, pupil_diameter * 0.5f);
        nvgFillColor(vg, nvgRGB(0, 0, 0));
        nvgFill(vg);

        nvgEndFrame(vg);
        nvgluBindFramebuffer(nullptr);
    }

    /**
     * Draws the eye by using the offscreen framebuffer's texture as an image pattern.
     */
    auto draw(NVGcontext *vg) -> void
    {
        const float eye_x = -width/2;
        const float eye_y = -height/2;
        const float angle = 0.0f;
        const float alpha = 1.0f;

        NVGpaint image = nvgImagePattern(vg, eye_x, eye_y, width, height, angle, fbo->image, alpha);

        nvgBeginPath(vg);
        nvgRect(vg, eye_x, eye_y, width, height);
        nvgFillPaint(vg, image);
        nvgFill(vg);
    }

    /**
     * Cleans up resources by deleting the offscreen framebuffer (FBO) if it exists.
     */
    auto destroy() -> void
    {
        if (fbo) {
            nvgluDeleteFramebuffer(fbo);
            fbo = nullptr;
        }
    }

    /**
     * Set the closeness of the eye. 0 = fully open, 1 = fully closed.
     * This will affect the alpha mask
     */
    auto set_closed(float closed_factor) -> void
    {
        this->closed_factor = std::clamp(closed_factor, 0.0f, 1.0f);
    }

private:

    int width;
    int height;
    float corner_radius;
    float pupil_diameter;
    float pupil_offset_x{};
    float pupil_offset_y{};
    float closed_factor{0.0f}; // 0 = fully open, 1 = fully closed
    NVGLUframebuffer *fbo{};

};


/**
 * Represents a simple mouth graphic.
 *
 * The mouth is drawn as a rounded rectangle, centered at the origin.
 * closed_factor: 0 = fully open (max height), 1 = fully closed (height ~ 0).
 */
class MouthGraphic
{
public:

    /**
     * Draw the mouth centered at the current transform origin.
     */
    auto draw(NVGcontext *vg) -> void
    {
        if (speaking) {
            draw_speaking(vg);
        } else {
            draw_idle(vg);
        }
    }

    /**
     * Set whether the mouth is in a speaking state. When speaking, the mouth
     * will be drawn as a filled shape that scales vertically based on the
     * closed_factor to simulate opening and closing.
     */
    auto set_speaking(bool speaking) -> void
    {
        this->speaking = speaking;
    }

    /**
     * Set how closed the mouth is. 0 = fully open, 1 = fully closed.
     */
    auto set_closed(float closed_factor) -> void
    {
        this->closed_factor = std::clamp(closed_factor, 0.0f, 1.0f);
    }

    /**
     * Configure the shape of the mouth by setting its width, height, corner radius,
     * and color.
     */
    auto set_shape(
        int width,
        int height,
        float corner_radius,
        float lips_thickness,
        NVGcolor mouth_color
    ) -> void
    {
        this->width = width;
        this->height = height;
        this->corner_radius = corner_radius;
        this->lips_thickness = lips_thickness;
        this->mouth_color = mouth_color;
    }

private:

    /**
     * Draw the mouth in a speaking state, where the mouth shape is filled and scales
     * vertically based on the closed_factor to simulate opening and closing. When nearly
     * closed, a minimum scale is applied to ensure the mouth remains visible as a thin
     * line.
     */
    auto draw_speaking(NVGcontext *vg) -> void
    {
        const float openness = 1.0f - closed_factor;
        const float scale_y = std::max(openness, K_MIN_MOUTH_SCALE_Y);
        const float scaled_height = static_cast<float>(height) * scale_y;
        const float mouth_x = -static_cast<float>(width) * 0.5f;
        const float mouth_y = -scaled_height * 0.5f;
        const float safe_corner_radius = std::min(corner_radius, scaled_height * 0.5f);

        nvgSave(vg);
        nvgBeginPath(vg);
        nvgRoundedRect(
            vg,
            mouth_x,
            mouth_y,
            static_cast<float>(width),
            scaled_height,
            safe_corner_radius
        );
        nvgFillColor(vg, mouth_color);
        nvgFill(vg);

        // Draw a constant-width contour so the mouth remains visible when nearly closed.
        nvgStrokeColor(vg, mouth_color);
        nvgStrokeWidth(vg, lips_thickness);
        nvgLineJoin(vg, NVG_ROUND);
        nvgBeginPath(vg);
        nvgRoundedRect(
            vg,
            mouth_x,
            mouth_y,
            static_cast<float>(width),
            scaled_height,
            safe_corner_radius
        );
        nvgStroke(vg);
        nvgRestore(vg);
    }

    /**
     * Draw the mouth in an idle state, where the mouth is just a stroked outline
     * (e.g. a smile).
     */
    auto draw_idle(NVGcontext *vg) -> void
    {
        const float rx = static_cast<float>(width) * 0.5f;
        const float ry = static_cast<float>(height) * 0.5f;
        constexpr int k_segments = 32;
        constexpr float k_pi = 3.14159265358979323846f;

        nvgSave(vg);
        nvgStrokeColor(vg, mouth_color);
        nvgStrokeWidth(vg, lips_thickness);
        nvgLineCap(vg, NVG_ROUND);

        // Lower half of an ellipse to look like a smile.
        nvgBeginPath(vg);
        for (int i = 0; i <= k_segments; ++i) {
            const float t = (k_pi * static_cast<float>(i)) / static_cast<float>(k_segments);
            const float x = rx * std::cos(t);
            const float y = ry * std::sin(t);
            if (i == 0) {
                nvgMoveTo(vg, x, y);
            } else {
                nvgLineTo(vg, x, y);
            }
        }
        nvgStroke(vg);
        nvgRestore(vg);
    }

    int width{0};
    int height{0};
    float corner_radius{0.0f};
    float lips_thickness{0.0f};
    NVGcolor mouth_color{nvgRGB(0, 0, 0)};
    float closed_factor{0.0f};
    bool speaking{false};

};


/**
 * Represents the entire face graphic, which consists of two eyes (for now).
 * Later we can extend this to include more facial features like a mouth, nose, etc.
 */
class FaceGraphic
{
public:

    FaceGraphic(int width, int height):
        width(width),
        height(height),
        left_eye(std::make_shared<EyeGraphic>()),
        right_eye(std::make_shared<EyeGraphic>()),
		mouth(std::make_shared<MouthGraphic>())
    {}

    /**
     * Draws the face graphic by first drawing each eye into their respective
     * offscreen framebuffers (FBOs),
     */
    auto draw_offscreen(NVGcontext *vg) -> void
    {
        left_eye->draw_offscreen(vg);
        right_eye->draw_offscreen(vg);
    }

    /**
     * Draws the face by using the offscreen framebuffer textures from each eye and
     * drawing them at the correct positions on the face. The eyes are positioned
     * based on the specified distance between them and their vertical offset
     * from the center of the face
     */
    auto draw(NVGcontext *vg) -> void
    {
        nvgSave(vg);
        nvgTranslate(vg, width * 0.5f, height * 0.5f);

        // Eyes
        nvgSave(vg);
        nvgTranslate(vg, 0.0f, eyes_offset_y);
        nvgSave(vg);
        nvgTranslate(vg, -eyes_distance * 0.5f, 0.0f);
        left_eye->draw(vg);
        nvgRestore(vg);
        nvgSave(vg);
        nvgTranslate(vg, eyes_distance * 0.5f, 0.0f);
        right_eye->draw(vg);
        nvgRestore(vg);
        nvgRestore(vg);

        // Mouth
        nvgSave(vg);
        nvgTranslate(vg, 0.0f, mouth_offset_y);
        mouth->draw(vg);
        nvgRestore(vg);

        nvgRestore(vg);
    }

    /**
     * Cleans up resources by destroying each eye graphic, which will delete their
     * offscreen framebuffers (FBOs) if they exist.
     */
    auto destroy() -> void
    {
        left_eye->destroy();
        right_eye->destroy();
    }

    /**
     * Return a shared pointer to the left eye graphic.
     */
    auto get_left_eye() const -> std::shared_ptr<EyeGraphic>
    {
        return left_eye;
    }

    /**
     * Return a shared pointer to the right eye graphic.
     */
    auto get_right_eye() const -> std::shared_ptr<EyeGraphic>
    {
        return right_eye;
    }

    /**
     * Return a shared pointer to the mouth graphic.
     */
    auto get_mouth() const -> std::shared_ptr<MouthGraphic>
    {
        return mouth;
    }

    /**
     * Configure the shape of both eyes at once. This is a convenience method
     * that updates the shape of both eyes based on the specified parameters.
     * The eyes will be configured with the same width, height, pupil diameter,
     * and corner radius, but their positions will still be determined
     * by the eyes_distance and eyes_offset_y parameters.
     */
    auto set_eyes_shape(
        NVGcontext *vg,
        int eye_width,
        int eye_height,
        float pupil_diameter,
        float eyes_distance,
        float eyes_offset_y,
        float corner_radius = 0.0f
    ) -> std::expected<void, std::string>
    {
        this->eyes_distance = eyes_distance;
        this->eyes_offset_y = eyes_offset_y;

        std::expected<void, std::string> left_eye_init_result = left_eye->init(
            vg,
            eye_width,
            eye_height,
            pupil_diameter,
            corner_radius
        );
        if (!left_eye_init_result) {
            return std::unexpected{left_eye_init_result.error()};
        }

        std::expected<void, std::string> right_eye_init_result = right_eye->init(
            vg,
            eye_width,
            eye_height,
            pupil_diameter,
            corner_radius
        );
        if (!right_eye_init_result) {
            return std::unexpected{right_eye_init_result.error()};
        }

        return {};
    }

    /**
     * Configure the mouth shape. This sets the mouth's geometry, color,
     * and its vertical offset from the face center.
     */
    auto set_mouth_shape(
        int mouth_width,
        int mouth_height,
        float corner_radius,
        float lips_thickness,
        float mouth_offset_y,
        NVGcolor mouth_color
    ) -> void
    {
        this->mouth_offset_y = mouth_offset_y;
        mouth->set_shape(
            mouth_width,
            mouth_height,
            corner_radius,
            lips_thickness,
            mouth_color
        );
        mouth->set_closed(1.0f); // Start with mouth closed by default
    }

private:

    int width;
    int height;
    float eyes_distance{1.0f};
    float eyes_offset_y{0.0f};
	float mouth_offset_y{0.0f};
    std::shared_ptr<EyeGraphic> left_eye;
    std::shared_ptr<EyeGraphic> right_eye;
	std::shared_ptr<MouthGraphic> mouth;

};