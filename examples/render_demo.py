"""Render every page of the actual demo PDF with Poppler for visual review."""
from pathlib import Path
import shutil
import subprocess

from pypdf import PdfReader

pdf = Path("完整论文.pdf")
pages = len(PdfReader(pdf).pages)
if pages != 2:
    raise ValueError(f"Expected this demo's two-page layout, found {pages}; inspect before accepting")
renderer = shutil.which("pdftoppm")
if not renderer:
    raise RuntimeError("Poppler pdftoppm is required for this render step")
Path("render").mkdir(exist_ok=True)
subprocess.run([renderer, "-scale-to", "1600", "-png", str(pdf), "render/page"], check=True)
print(f"Rendered all {pages} PDF pages with {renderer}")
