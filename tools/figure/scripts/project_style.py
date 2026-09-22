"""Scoped plotting preferences from a supplied runtime project or trusted root.

    with project_style(project_root=project_root, lang="zh") as applied:
        fig, ax = plt.subplots()
        ax.plot(x, y, **series_style(0, sample_count=len(x)))
        export_figure(fig, output, size_inches=(6, 4))

Only graphicsTools.scienceplots=True enables SciencePlots. An installed package
never overrides an explicit false. This helper does not run optional agents/tools.
"""
from contextlib import contextmanager
import json
from pathlib import Path

from cycler import cycler
import matplotlib as mpl

from setup_style import style_context


# Okabe-Ito subset for white backgrounds, also documented by the bundled
# scientific-visualization/references/color_palettes.md; redundancy remains needed.
COLORS = ("#0072B2", "#D55E00", "#009E73", "#CC79A7", "#000000")
MARKERS = ("o", "s", "^", "D", "v")
LINESTYLES = ("-", "--", "-.", ":", (0, (5, 2, 1, 2)))


def read_project(project=None, *, project_root=None):
    """Accept runtime project/context/state, or read state at an explicit root.

    A path found inside metadata is never followed. No root means builtin defaults.
    """
    if project is not None and project_root is not None:
        raise ValueError("Pass project or project_root, not both")
    if project_root is not None:
        state_path = Path(project_root).resolve() / ".math-modeling" / "state.json"
        project = json.loads(state_path.read_text(encoding="utf-8"))
    if project is None:
        return {}
    if not isinstance(project, dict):
        raise ValueError("Project must be a runtime project/context/state object")
    result = project.get("project", project)
    if not isinstance(result, dict):
        raise ValueError("Invalid project object")
    return result


def series_style(index, *, sample_count=None, max_markers=10):
    """A stable color/marker/line identity; decimate markers, never the data line."""
    if not isinstance(index, int) or index < 0:
        raise ValueError("Series index must be a nonnegative integer")
    if not isinstance(max_markers, int) or max_markers < 1:
        raise ValueError("max_markers must be a positive integer")
    if sample_count is not None and (not isinstance(sample_count, int) or sample_count < 1):
        raise ValueError("sample_count must be a positive integer")
    slot = index % len(COLORS)
    style = {"color": COLORS[slot], "marker": MARKERS[slot], "linestyle": LINESTYLES[slot],
             "markerfacecolor": "white", "markeredgewidth": .9}
    if sample_count is not None:
        style["markevery"] = max(1, (sample_count + max_markers - 1) // max_markers)
    return style


@contextmanager
def project_style(project=None, *, project_root=None, journal="general", lang="en", serif_for_zh=False):
    """Apply required base style and the selected optional SciencePlots overlay.

    Keep figure creation, plotting and export inside the context. Settings are read
    once per context; the next figure sees subsequent project settings changes.
    """
    config = read_project(project, project_root=project_root)
    tools = config.get("graphicsTools", {})
    if not isinstance(tools, dict) or not isinstance(tools.get("scienceplots", False), bool):
        raise ValueError("project.graphicsTools.scienceplots must be a boolean")
    requested = tools.get("scienceplots", False)
    with style_context(journal=journal, lang=lang, use_sciplots=requested, serif_for_zh=serif_for_zh) as applied:
        mpl.rcParams.update({
            "axes.prop_cycle": cycler(color=COLORS) + cycler(linestyle=LINESTYLES),
            "axes.axisbelow": True, "axes.grid": False,
            "legend.frameon": False, "legend.handlelength": 2.5,
            "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white",
            "text.color": "#222222", "axes.labelcolor": "#222222", "axes.edgecolor": "#444444",
            "xtick.color": "#444444", "ytick.color": "#444444",
            "xtick.top": mpl.rcParams["axes.spines.top"], "ytick.right": mpl.rcParams["axes.spines.right"],
            "grid.color": "#D9D9D9", "grid.linewidth": .5,
        })
        yield {**applied, "graphicsTools": dict(tools), "colors": list(COLORS),
               "encoding": "color plus line style; series_style adds sparse markers"}
