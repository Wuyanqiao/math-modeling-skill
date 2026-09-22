"""Create the synthetic demo's TeX source from its actual result table."""
import csv
from pathlib import Path

with Path("results/solution.csv").open(encoding="utf-8", newline="") as stream:
    row = next(csv.DictReader(stream))
x, y, objective = (float(row[key]) for key in ("x", "y", "objective"))
if max(abs(x - 2), abs(y - 2), abs(objective - 10)) > 1e-9:
    raise ValueError("Demo result disagrees with the independent analytic solution")

source = r"""\documentclass[11pt,a4paper]{article}
\usepackage[margin=22mm]{geometry}
\usepackage{amsmath,booktabs,graphicx,xcolor,fancyhdr}
\definecolor{accent}{HTML}{216C68}
\pagestyle{fancy}\fancyhf{}
\fancyhead[L]{\small MathModel Workbench / Verification case}
\fancyhead[R]{\small Synthetic data}
\fancyfoot[C]{\thepage}
\setlength{\headheight}{14pt}
\setlength{\parindent}{0pt}
\setlength{\parskip}{6pt}
\begin{document}
{\LARGE\bfseries\color{accent} A small resource allocation model}\par
{\large Reproducible optimization and evidence review}\par
\textbf{Scope.} This deterministic synthetic case tests the modeling workflow.
It does not represent a competition entry or establish performance on real data.

\section*{1. Model and assumptions}
Let $x,y$ be continuous, divisible allocations in resource units. With fixed,
additive value coefficients, solve
\[
\max_{x,y\geq0}\;z=3x+2y,\qquad x+y\leq4,\quad x\leq2,\quad y\leq3.
\]
There is no uncertainty model or integer restriction. These assumptions are part
of this test, not a recommendation for other allocation problems.

\section*{2. Independent bound and numerical solution}
For every feasible point, $3x+2y=2(x+y)+x\leq2(4)+2=10$.
Equality forces $x=2$ and $x+y=4$, so the unique optimum is $(2,2)$.
SciPy's HiGHS solver returned the values below from the registered CSV.
\begin{center}
\begin{tabular}{rrrr}
\toprule
$x$ & $y$ & Objective value & Maximum constraint violation\\
\midrule
@X@ & @Y@ & @OBJECTIVE@ & 0\\
\bottomrule
\end{tabular}
\end{center}
\begin{figure}[h!]
\centering\includegraphics[width=.76\textwidth]{figures/result_q1_region.png}
\caption{Feasible region and the unique optimum. The shaded polygon is defined
by the model inequalities, and the highlighted point attains the analytic bound.}
\end{figure}
\clearpage
\section*{3. Resource use and interpretation}
At the computed optimum, the shared resource and the $x$ capacity are binding.
The $y$ capacity has one unused unit. Figure 2 compares use with capacity in
the same resource units; it does not display statistical uncertainty.
\begin{figure}[h!]
\centering\includegraphics[width=.84\textwidth]{figures/result_q1_usage.png}
\caption{Resource use at the optimum. Capacities are $(4,2,3)$ and actual use is
$(4,2,2)$. A nonzero slack is feasible and should not be presented as an error.}
\end{figure}

\section*{4. Reproduction and verification}
The solver reads the synthetic coefficient file, minimizes the negative objective
with HiGHS and writes a one-row result table. The execution record binds inputs,
source code and outputs by SHA-256, records the actual executable and environment,
and retains process exit status and logs. The two figures are exported as SVG and
300-DPI PNG; each format pair represents one logical figure.

The independent acceptance check compares the numerical solution against the
analytic bound using absolute tolerance $10^{-9}$. Model, minimal execution,
full numerical evidence, evidence outline and rendered paper are reviewed at
separate gates. A rendered file alone does not establish scientific correctness.

\section*{5. Limitations}
The case contains two variables and three upper-bound constraints. It tests
workflow integrity and one small linear program. It provides no evidence for
large-scale robustness, stochastic modeling, integer decisions, noisy forecasting
or literature-supported scientific claims. No external literature is required
for the elementary proof given here.
\end{document}
"""
for key, value in {"@X@": x, "@Y@": y, "@OBJECTIVE@": objective}.items():
    source = source.replace(key, f"{value:g}")
Path("paper.tex").write_text(source, encoding="utf-8")
print("Created paper.tex from results/solution.csv")
