from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cairo

from manana.gui import MAX_PREVIEW_ZOOM, MIN_PREVIEW_ZOOM, NewspaperApp, preview_ppm


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.app = NewspaperApp.__new__(NewspaperApp)
        self.app.root = Mock()
        self.app.root.tk.call.return_value = "x11"
        self.app.preview = Mock()
        self.app.preview.winfo_width.return_value = 600
        self.app.preview.winfo_height.return_value = 800
        self.app.latest_pdf = Path("edition.pdf")
        self.app.preview_image = None
        self.app.preview_item = None
        self.app.preview_origin = None
        self.app.preview_frame = None
        self.app.preview_controls = None
        self.app.preview_surface = cairo.ImageSurface(cairo.FORMAT_RGB24, 1000, 1400)
        context = cairo.Context(self.app.preview_surface)
        context.set_source_rgb(1, 1, 1)
        context.paint()
        context.set_source_rgb(0, 0, 0)
        context.rectangle(180, 330, 40, 40)
        context.fill()
        self.app.preview_render_job = None
        self.app.preview_refine_job = None
        self.app.preview_zoom = 1.0
        self.app.preview_offset = (0.0, 0.0)
        self.app.preview_drag_point = None
        self.app.zoom_status = Mock()
        self.app.reset_zoom_button = Mock()

        self.app.preview.create_image.side_effect = self.show_image
        self.app.preview.coords.side_effect = self.move_image
        self.app.preview.itemconfigure.side_effect = self.update_image
        # Decode actual RGB data in place of a display-dependent Tk image.
        photo = patch("manana.gui.tk.PhotoImage", side_effect=self.decode_image)
        self.photo = photo.start()
        self.addCleanup(photo.stop)

    def decode_image(self, **kwargs):
        image = SimpleNamespace()

        def configure(**options):
            self.assertEqual(options["format"], "PPM")
            magic, dimensions, maximum, pixels = options["data"].split(b"\n", 3)
            self.assertEqual((magic, maximum), (b"P6", b"255"))
            width, height = map(int, dimensions.split())
            self.assertEqual(len(pixels), width * height * 3)
            if "width" in options:
                self.assertEqual((options["width"], options["height"]), (width, height))
            image.width, image.height, image.pixels = width, height, pixels

        configure(**kwargs)
        image.configure = Mock(side_effect=configure)
        return image

    def show_image(self, x, y, *, image, anchor):
        self.image_origin = (x, y)
        self.display_image = image
        self.assertEqual(anchor, "nw")
        return "page"

    def move_image(self, _item, x, y):
        self.image_origin = (x, y)

    def update_image(self, _item, *, image):
        self.display_image = image

    def pixel_at(self, x, y):
        image = self.display_image
        column, row = x - self.image_origin[0], y - self.image_origin[1]
        index = (row * image.width + column) * 3
        return int.from_bytes(image.pixels[index:index + 3], "big")

    def test_wheel_keeps_the_point_under_the_pointer_visible(self):
        # This point starts inside the black marker, away from page boundaries.
        self.app.draw_preview()
        self.assertEqual(self.pixel_at(135, 208), 0)
        for _ in range(5):
            self.assertEqual(self.app.zoom_preview(SimpleNamespace(num=4, x=135, y=208)), "break")
            self.app.draw_preview(interactive=True)
            self.assertEqual(self.pixel_at(135, 208), 0)
        self.assertGreater(self.app.preview_zoom, 2)
        for _ in range(5):
            self.app.zoom_preview(SimpleNamespace(num=5, x=135, y=208))
        self.assertAlmostEqual(self.app.preview_zoom, 1.0)

    def test_native_wheel_events_and_zoom_limits(self):
        for system, delta in (("win32", 120), ("aqua", 1)):
            with self.subTest(system=system):
                self.app.reset_preview_zoom()
                self.app.root.tk.call.return_value = system
                self.app.zoom_preview(SimpleNamespace(delta=delta, x=300, y=400))
                self.assertAlmostEqual(self.app.preview_zoom, 1.2)
        for _ in range(4):
            self.app.zoom_preview(SimpleNamespace(delta=12000, x=300, y=400))
        self.assertEqual(self.app.preview_zoom, MAX_PREVIEW_ZOOM)
        for _ in range(5):
            self.app.zoom_preview(SimpleNamespace(delta=-12000, x=300, y=400))
        self.assertEqual(self.app.preview_zoom, MIN_PREVIEW_ZOOM)

    def test_drag_reaches_page_edges_and_fit_restores_the_whole_page(self):
        self.app.preview_zoom = 3.0
        self.app.draw_preview()
        self.app.start_preview_drag(SimpleNamespace(x=300, y=400))
        self.app.drag_preview(SimpleNamespace(x=-10000, y=-10000))
        width, height, scale, left, top = self.app.preview_geometry()
        self.assertAlmostEqual(left + 1000 * scale, width - 16)
        self.assertAlmostEqual(top + 1400 * scale, height - 16)
        self.app.drag_preview(SimpleNamespace(x=10000, y=10000))
        _, _, _, left, top = self.app.preview_geometry()
        self.assertEqual((left, top), (16, 16))
        self.app.end_preview_drag(None)
        self.assertIsNone(self.app.preview_drag_point)
        self.app.reset_preview_zoom()
        width, height, scale, left, top = self.app.preview_geometry()
        self.assertEqual(self.app.preview_zoom, 1.0)
        self.assertEqual(self.app.preview_offset, (0.0, 0.0))
        self.assertAlmostEqual(left + 500 * scale, width / 2)
        self.assertAlmostEqual(top + 700 * scale, height / 2)
        self.assertLessEqual(1000 * scale, width - 32)
        self.assertLessEqual(1400 * scale, height - 32)

    def test_zoomed_rendering_stays_within_viewport_dimensions(self):
        self.app.preview_zoom = MAX_PREVIEW_ZOOM
        self.app.draw_preview()
        self.assertLessEqual(self.app.preview_image.width, 600)
        self.assertLessEqual(self.app.preview_image.height, 800)

    def test_wheel_burst_renders_latest_state_once_then_refines_when_idle(self):
        pending = {}
        next_id = 0

        def after(delay, callback):
            nonlocal next_id
            next_id += 1
            pending[next_id] = (delay, callback)
            return next_id

        self.app.root.after.side_effect = after
        self.app.root.after_cancel.side_effect = lambda key: pending.pop(key, None)
        for number in (4, 5) * 40:
            self.app.zoom_preview(SimpleNamespace(num=number, x=135, y=208))
        self.photo.assert_not_called()
        self.assertEqual(sorted(delay for delay, _ in pending.values()), [16, 150])
        frame = next(callback for delay, callback in pending.values() if delay == 16)
        frame()
        self.assertEqual(self.photo.call_count, 1)
        self.assertAlmostEqual(self.app.preview_zoom, 1.0)
        self.assertEqual(self.pixel_at(135, 208), 0)
        refine = next(callback for delay, callback in pending.values() if delay == 150)
        refine()
        self.assertEqual(self.photo.call_count, 1)
        self.app.preview_image.configure.assert_called_once()
        self.assertFalse(pending)
        self.app.preview.create_image.assert_called_once()
        self.app.preview.itemconfigure.assert_not_called()

        self.app.zoom_preview(SimpleNamespace(num=4, x=135, y=208))
        self.app.reset_preview_zoom()
        self.assertFalse(pending)
        self.assertEqual(self.app.preview_zoom, 1.0)

    def test_pan_zoom_and_refinement_reuse_one_image_and_shrink_its_pixel_buffer(self):
        self.app.preview_zoom = 3.0
        self.app.preview_offset = (400.0, 400.0)
        self.app.draw_preview(interactive=True)
        image = self.app.preview_image
        self.assertEqual((image.width, image.height), (600, 800))
        self.assertEqual(self.pixel_at(200, 220), 0)
        self.app.start_preview_drag(SimpleNamespace(x=300, y=400))
        self.app.drag_preview(SimpleNamespace(x=360, y=450))
        self.app.draw_preview(interactive=True)
        self.assertIs(self.app.preview_image, image)
        self.assertEqual(self.pixel_at(200, 220), 0xffffff)
        self.assertEqual(self.pixel_at(260, 270), 0)
        self.app.end_preview_drag(None)
        self.app.draw_preview()
        self.app.reset_preview_zoom()
        self.assertLess(image.width, 600)
        self.assertLess(image.height, 800)
        self.assertEqual(self.pixel_at(135, 208), 0)
        self.photo.assert_called_once()
        self.app.preview.create_image.assert_called_once()
        self.app.preview.itemconfigure.assert_not_called()

    def test_unchanged_page_does_not_upload_pixels_or_reconfigure_controls(self):
        self.app.draw_preview()
        self.app.preview.configure.reset_mock()
        self.app.reset_zoom_button.configure.reset_mock()
        self.app.zoom_status.set.reset_mock()
        for _ in range(10):
            self.app.draw_preview(interactive=True)
            self.app.draw_preview()
        self.photo.assert_called_once()
        self.app.preview_image.configure.assert_not_called()
        self.app.preview.configure.assert_not_called()
        self.app.reset_zoom_button.configure.assert_not_called()
        self.app.zoom_status.set.assert_not_called()

    def test_loading_a_different_page_at_the_same_size_replaces_cached_pixels(self):
        self.app.draw_preview()
        image = self.app.preview_image
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "replacement.png"
            surface = cairo.ImageSurface(cairo.FORMAT_RGB24, 1000, 1400)
            context = cairo.Context(surface)
            context.set_source_rgb(0, 0, 1)
            context.paint()
            surface.write_to_png(str(path))
            self.app.show_preview(path)
        self.assertIs(self.app.preview_image, image)
        self.assertEqual(self.pixel_at(135, 208), 0x0000ff)
        self.photo.assert_called_once()

    def test_raw_rgb_encoding_preserves_color_order(self):
        surface = cairo.ImageSurface(cairo.FORMAT_RGB24, 2, 1)
        context = cairo.Context(surface)
        context.set_source_rgb(1, 0, 0)
        context.rectangle(0, 0, 1, 1)
        context.fill()
        context.set_source_rgb(0, 0, 1)
        context.rectangle(1, 0, 1, 1)
        context.fill()
        self.assertEqual(preview_ppm(surface), b"P6\n2 1\n255\n\xff\x00\x00\x00\x00\xff")

    def test_loading_another_preview_resets_zoom_and_empty_preview_ignores_mouse(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preview.png"
            self.app.preview_surface.write_to_png(str(path))
            self.app.preview_zoom = 4.0
            self.app.preview_offset = (-500, -300)
            self.app.show_preview(path)
        self.assertEqual(self.app.preview_zoom, 1.0)
        self.assertEqual(self.app.preview_offset, (0.0, 0.0))
        self.app.preview_surface = None
        self.app.zoom_preview(SimpleNamespace(num=4, x=300, y=400))
        self.app.start_preview_drag(SimpleNamespace(x=300, y=400))
        self.assertIsNone(self.app.preview_drag_point)
        self.app.draw_preview()
        self.assertIsNone(self.app.preview_image)
        self.app.reset_zoom_button.configure.assert_called_with(state="disabled")


if __name__ == "__main__":
    unittest.main()
