"""Project preference isolation, real export dimensions, fonts and style behavior."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import warnings
from unittest.mock import patch
import xml.etree.ElementTree as ET

import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ft2font import FT2Font
import matplotlib.font_manager as fm
import numpy as np
from PIL import Image
from pypdf import PdfReader


SCRIPTS = Path(__file__).resolve().parents[1] / "tools" / "figure" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import export_figure
import project_style
import setup_style


class ScopedStyleTests(unittest.TestCase):
    def test_false_never_loads_optional_style_and_scope_restores_every_rcparam(self):
        before = mpl.rcParams.copy()
        with patch.object(setup_style, "_try_sciencplots", side_effect=AssertionError("must not load")):
            with project_style.project_style({"graphicsTools": {"scienceplots": False}}) as applied:
                self.assertEqual(applied["sciplots_status"], "disabled")
                cycle = list(mpl.rcParams["axes.prop_cycle"])
                self.assertEqual(cycle[0]["color"], "#0072B2")
                self.assertNotEqual(cycle[0]["linestyle"], cycle[1]["linestyle"])
                self.assertFalse(mpl.rcParams["text.usetex"])
        self.assertEqual(dict(before), dict(mpl.rcParams))

    def test_scope_restores_after_failure_and_missing_chinese_font(self):
        before = mpl.rcParams.copy()
        with self.assertRaisesRegex(RuntimeError, "test failure"):
            with project_style.project_style():
                mpl.rcParams["font.size"] = 99
                raise RuntimeError("test failure")
        self.assertEqual(dict(before), dict(mpl.rcParams))
        with patch.object(setup_style, "_available_fonts", return_value=set()), self.assertRaises(RuntimeError):
            with project_style.project_style(lang="zh"):
                self.fail("Must refuse missing Chinese font")
        self.assertEqual(dict(before), dict(mpl.rcParams))

    def test_selected_optional_style_is_honest_about_missing_dependency(self):
        with patch.object(setup_style, "_try_sciencplots", return_value=False):
            with self.assertWarnsRegex(RuntimeWarning, "unavailable"):
                with project_style.project_style({"graphicsTools": {"scienceplots": True}}) as applied:
                    self.assertEqual(applied["sciplots_status"], "unavailable")
                    self.assertFalse(applied["sciplots_used"])

    def test_actual_optional_package_when_available_and_no_latex_required(self):
        before = mpl.rcParams.copy()
        if importlib.util.find_spec("scienceplots") is None:
            with self.assertWarns(RuntimeWarning):
                with project_style.project_style({"graphicsTools": {"scienceplots": True}}) as applied:
                    self.assertEqual(applied["sciplots_status"], "unavailable")
        else:
            with project_style.project_style({"graphicsTools": {"scienceplots": True}}) as applied:
                self.assertEqual(applied["sciplots_status"], "used")
                self.assertFalse(mpl.rcParams["text.usetex"])
                fig, ax = plt.subplots()
                ax.plot([0, 1], [1, 2])
                fig.canvas.draw()
                plt.close(fig)
        self.assertEqual(dict(before), dict(mpl.rcParams))

    def test_project_root_reads_fresh_preferences_without_following_metadata_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / ".math-modeling" / "state.json"
            state.parent.mkdir()
            for enabled in (False, True, False):
                state.write_text(json.dumps({"project": {"projectRoot": "must-not-be-followed",
                                 "graphicsTools": {"scienceplots": enabled}}}), encoding="utf-8")
                with patch.object(setup_style, "_try_sciencplots", return_value=True) as optional:
                    with project_style.project_style(project_root=root) as applied:
                        self.assertEqual(applied["sciplots_requested"], enabled)
                    self.assertEqual(optional.call_count, int(enabled))
        with self.assertRaises(ValueError):
            with project_style.project_style({"graphicsTools": {"scienceplots": "false"}}):
                pass

    def test_sparse_markers_change_encoding_without_changing_data(self):
        x = np.arange(101)
        y = np.sin(x / 20)
        with project_style.project_style():
            fig, ax = plt.subplots()
            first, = ax.plot(x, y, **project_style.series_style(0, sample_count=len(x)))
            second, = ax.plot(x, y, **project_style.series_style(1, sample_count=len(x)))
            np.testing.assert_array_equal(first.get_xdata(), x)
            np.testing.assert_array_equal(first.get_ydata(), y)
            self.assertEqual(first.get_markevery(), 11)
            self.assertNotEqual(first.get_marker(), second.get_marker())
            self.assertNotEqual(first.get_linestyle(), second.get_linestyle())
            self.assertNotEqual(first.get_color(), second.get_color())
            plt.close(fig)


class ExactExportTests(unittest.TestCase):
    def test_declared_size_is_preserved_in_png_pdf_svg_and_grayscale(self):
        with tempfile.TemporaryDirectory() as directory, mpl.rc_context({"savefig.bbox": "tight", "pdf.fonttype": 3}):
            before = mpl.rcParams.copy()
            fig, ax = plt.subplots(figsize=(6, 4))
            ax.plot([0, 1, 2], [-1, 2, 1], color="#0072B2")
            ax.set(xlabel="Time (s)", ylabel="Response", title="Exact canvas")
            stem = str(Path(directory) / "figure")
            outputs = export_figure.export_figure(fig, stem, size_inches=(6, 4), dpi=150, grayscale_preview=True)
            self.assertEqual(len(outputs), 4)
            with Image.open(stem + ".png") as image, Image.open(stem + "_grayscale.png") as grayscale:
                self.assertEqual(image.size, (900, 600))
                self.assertEqual(grayscale.size, image.size)
                self.assertAlmostEqual(grayscale.info["dpi"][0], 150, delta=.02)
                self.assertEqual(grayscale.mode, "L")
                rgb = np.asarray(image.convert("RGB"))
                self.assertTrue(np.any(rgb[:, :, 0] != rgb[:, :, 2]))
            page = PdfReader(stem + ".pdf").pages[0]
            self.assertAlmostEqual(float(page.mediabox.width), 432, delta=1e-8)
            self.assertAlmostEqual(float(page.mediabox.height), 288, delta=1e-8)
            fonts = page["/Resources"]["/Font"].get_object()
            self.assertTrue(fonts)
            self.assertTrue(all(font.get_object()["/Subtype"] != "/Type3" for font in fonts.values()))
            svg = ET.parse(stem + ".svg").getroot()
            self.assertEqual(svg.attrib["viewBox"], "0 0 432 288")
            self.assertTrue(svg.findall(".//{http://www.w3.org/2000/svg}text"))
            self.assertEqual(dict(before), dict(mpl.rcParams))
            plt.close(fig)

    def test_grayscale_never_creates_or_overwrites_an_unrequested_color_png(self):
        with tempfile.TemporaryDirectory() as directory:
            stem = str(Path(directory) / "figure")
            existing = Path(stem + ".png")
            existing.write_bytes(b"unrelated existing file")
            fig, ax = plt.subplots()
            ax.plot([0, 1], [0, 1])
            export_figure.export_figure(fig, stem, formats=["pdf"], size_inches=(3, 2), grayscale_preview=True)
            self.assertEqual(existing.read_bytes(), b"unrelated existing file")
            plt.close(fig)

    def test_explicit_legacy_tight_mode_still_crops_and_restores_rc_on_export_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            fig, ax = plt.subplots()
            ax.plot([0, 1], [0, 1])
            stem = str(Path(directory) / "tight")
            export_figure.export_figure(fig, stem, formats=["png"], size_inches=(6, 4), dpi=100, tight=True)
            with Image.open(stem + ".png") as image:
                self.assertNotEqual(image.size, (600, 400))
            before = mpl.rcParams.copy()
            with patch.object(fig, "savefig", side_effect=OSError("disk failure")), self.assertRaises(OSError):
                export_figure.export_figure(fig, stem, formats=["png"], size_inches=(6, 4))
            self.assertEqual(dict(before), dict(mpl.rcParams))
            plt.close(fig)

    def test_available_chinese_font_has_real_glyphs_and_renders_mixed_labels(self):
        if not setup_style.list_cjk_fonts():
            with self.assertRaises(RuntimeError):
                with project_style.project_style(lang="zh"):
                    pass
            return
        with tempfile.TemporaryDirectory() as directory, project_style.project_style(lang="zh") as applied:
            font = fm.findfont(fm.FontProperties(family=applied["cjk_font"]), fallback_to_default=False)
            charmap = FT2Font(font).get_charmap()
            for character in "时间温度冷却曲线":
                self.assertIn(ord(character), charmap)
            fig, ax = plt.subplots()
            ax.plot([0, 1], [-1, 2])
            ax.set(xlabel="时间 (min)", ylabel="温度 (°C)", title="冷却曲线")
            with warnings.catch_warnings(record=True) as observed:
                warnings.simplefilter("always")
                export_figure.export_figure(fig, str(Path(directory) / "chinese"), size_inches=(6, 4))
            self.assertFalse(any("Glyph" in str(item.message) and "missing" in str(item.message) for item in observed))
            plt.close(fig)


if __name__ == "__main__":
    unittest.main()
