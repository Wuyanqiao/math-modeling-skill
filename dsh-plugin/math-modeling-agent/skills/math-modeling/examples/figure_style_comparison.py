"""Render identical synthetic cooling data with default/project/SciencePlots styles.

Run from any directory:
  python <SKILL_ROOT>/examples/figure_style_comparison.py --output-dir <OUTPUT_DIR>
  Add --scienceplots to verify the installed optional backend; missing packages are reported.
"""
import argparse
from contextlib import contextmanager
import csv
import hashlib
from io import StringIO
import importlib.metadata
import json
from pathlib import Path
import sys
import warnings
import xml.etree.ElementTree as ET

import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "tools" / "figure" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from export_figure import export_figure
from project_style import project_style, series_style
from setup_style import configure_chinese_fonts


@contextmanager
def default_style(language):
    with plt.style.context("default"):
        font = configure_chinese_fonts() if language == "zh" else None
        yield {"style": "matplotlib default", "lang": language, "cjk_font": font,
               "sciplots_requested": False, "sciplots_used": False}


def cooling_data():
    """One physical family, two disclosed parameter settings, no measurements or noise."""
    time = np.linspace(0, 20, 41)
    return time, np.column_stack((20 + 60 * np.exp(-.18 * time), 20 + 60 * np.exp(-.10 * time)))


def render_comparison(output_dir, include_scienceplots=False):
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    time, temperature = cooling_data()
    csv_buffer = StringIO(newline="")
    writer = csv.writer(csv_buffer, lineterminator="\n")
    writer.writerow(["time_min", "temperature_k018_C", "temperature_k010_C"])
    writer.writerows(zip(time, temperature[:, 0], temperature[:, 1]))
    dataset = csv_buffer.getvalue().encode("utf-8")
    (output / "cooling-data.csv").write_bytes(dataset)
    before = mpl.rcParams.copy()
    records = []
    cases = [(language, style) for language in ("en", "zh") for style in ("default", "enhanced")]
    if include_scienceplots:
        cases.append(("en", "scienceplots"))
    for language, style in cases:
        context = default_style(language) if style == "default" else project_style(
            {"graphicsTools": {"scienceplots": style == "scienceplots"}}, lang=language)
        with warnings.catch_warnings(record=True) as observed, context as applied:
            warnings.simplefilter("always")
            fig, ax = plt.subplots(figsize=(6, 4), layout="constrained")
            for column in range(2):
                kwargs = {} if style == "default" else series_style(column, sample_count=len(time), max_markers=9)
                ax.plot(time, temperature[:, column], label=(r"$k=0.18\;\mathrm{min}^{-1}$" if column == 0
                        else r"$k=0.10\;\mathrm{min}^{-1}$"), **kwargs)
            ax.set(xlim=(-.3, 20.3), ylim=(20, 82),
                   xlabel="时间 (min)" if language == "zh" else "Time (min)",
                   ylabel="温度 (°C)" if language == "zh" else "Temperature (°C)",
                   title="合成冷却曲线" if language == "zh" else "Synthetic cooling trajectories")
            ax.set_xticks([0, 5, 10, 15, 20])
            ax.set_yticks([20, 30, 40, 50, 60, 70, 80])
            ax.legend(loc="upper right")
            if style != "default":
                ax.grid(axis="y")
            for index, line in enumerate(ax.lines):
                np.testing.assert_array_equal(line.get_xdata(), time)
                np.testing.assert_array_equal(line.get_ydata(), temperature[:, index])
            stem = output / f"{style}-{language}"
            paths = export_figure(fig, str(stem), size_inches=(6, 4), dpi=300, grayscale_preview=True)
            plt.close(fig)
        missing_glyphs = [str(w.message) for w in observed if "Glyph" in str(w.message) and "missing" in str(w.message)]
        if missing_glyphs:
            raise RuntimeError("Missing font glyphs: " + "; ".join(missing_glyphs))
        with Image.open(str(stem) + ".png") as raster:
            pixels, dpi = list(raster.size), list(raster.info["dpi"])
        pdf = PdfReader(str(stem) + ".pdf")
        box = pdf.pages[0].mediabox
        svg = ET.parse(str(stem) + ".svg").getroot()
        assert pixels == [1800, 1200]
        assert abs(float(box.width) - 432) < 1e-8 and abs(float(box.height) - 288) < 1e-8
        assert svg.attrib["viewBox"] == "0 0 432 288"
        records.append({"style": style, "lang": language, "applied": applied, "same_data_verified": True,
                        "png_pixels": pixels, "png_dpi": dpi, "pdf_points": [float(box.width), float(box.height)],
                        "svg_viewbox": svg.attrib["viewBox"], "missing_glyphs": missing_glyphs,
                        "warnings": [str(w.message) for w in observed],
                        "files": [{"path": str(Path(path).relative_to(output)),
                                   "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()} for path in paths]})
    assert dict(before) == dict(mpl.rcParams), "Style leaked outside its context"
    packages = {}
    for name in ("matplotlib", "numpy", "Pillow", "pypdf", "SciencePlots", "seaborn"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    report = {"data": {"source": "Synthetic analytic cooling family T=20+60*exp(-k*t), k=0.18/0.10 min^-1",
                       "samples_per_curve": len(time), "seed": None, "sha256": hashlib.sha256(dataset).hexdigest()},
              "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "dependencies": packages, "python": sys.version, "styles_restored": True, "cases": records}
    (output / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--scienceplots", action="store_true")
    options = parser.parse_args()
    result = render_comparison(options.output_dir, options.scienceplots)
    print(json.dumps({"output_dir": str(options.output_dir.resolve()), "cases": len(result["cases"]),
                      "data_sha256": result["data"]["sha256"], "styles_restored": result["styles_restored"]}))
