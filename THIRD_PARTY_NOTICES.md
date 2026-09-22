# Component provenance and distribution status

This fork preserves the history and attribution of [XiaoMaColtAI/math-modeling-skill](https://github.com/XiaoMaColtAI/math-modeling-skill). The audited baseline is commit `3c4bd1927663327812665941a445281b9c008a78` (2026-09-22 review). No repository-wide license was supplied at that baseline. Public visibility and the ability to fork are not treated here as permission to relicense or redistribute every bundled component.

| Component | Source evidence | Current build treatment |
| --- | --- | --- |
| Original Skill, algorithm references, templates and tool changes | Upstream Git history; root license absent | Authorization unverified; release blocked |
| `tools/docx/` | [Bundled license](tools/docx/LICENSE.txt), attributed to Anthropic, PBC | Restricted; excluded from release selection |
| `tools/xlsx/` | [Bundled license](tools/xlsx/LICENSE.txt), attributed to Anthropic, PBC | Restricted; excluded from release selection |
| `tools/pdf/` | [Bundled license](tools/pdf/LICENSE.txt), attributed to Anthropic, PBC | Restricted; excluded from release selection |
| DSH preset, host adapter and bundled knowledge | Upstream `dsh-plugin/`; each transitive resource retains its own source | Authorization unverified; release blocked |
| Original DSH UI subpackage | The upstream UI `package.json` declared `MIT`; that declaration is not a whole-repository license | Preserve that historical provenance. The expanded local bundle now includes restricted/unverified resources and is marked `private: true`, `UNLICENSED`; no blanket authorization is inferred |
| Figure references and inherited examples | Upstream change history identifies external figure skills; complete per-file provenance not yet established | Included in upstream-content block |
| Fork runtime, build system, documentation and tests | Current fork commit history; owner has not selected a distribution license | Local development; release blocked until an explicit license is supplied |
| Python/Node packages installed separately | Package metadata from the relevant package registry | Not vendored into Skill or DSH archives; users install declared optional dependencies |

The three bundled Anthropic license files include restrictions on copying, derivative works and distribution. They remain intact; editing an inherited file does not erase its source or those terms. No MIT, Apache or other blanket license has been added to this repository.

`distribution-policy.json` is the machine-readable counterpart of this inventory. Every included path must match a component. Release mode excludes restricted components and rejects unclassified or unverified components. Changing a decision to `allow` also requires a license identifier and a repository-local evidence file; this records an actual authorization, rather than creating one. Rights clearance and replacement implementations remain necessary before a release build can succeed.

`--mode local-development` creates a labelled copy for verification of the existing local checkout. The filename, top-level notice and manifest all state that it is **not approved for redistribution**. That switch makes no legal claim and grants no new rights. CI does not upload these bundles. Building a Python wheel for local installation likewise does not imply publication approval.

For the distinction between viewing/forking and open source licensing, see [GitHub's licensing documentation](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository). This document records the evidence available in this checkout; it is not a substitute for a missing grant from a rights holder.

## Visualization additions in 2.1

- The four skill packages under `tools/figure/skills/` come from [K-Dense-AI/scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills/tree/49c6e97775eaa18ba791bebe23162a70ae601c18/skills), pinned at that commit. The upstream [MIT license](tools/figure/skills/LICENSE.md) and [per-file source hashes/adaptations](tools/figure/skills/UPSTREAM.json) are retained. Library licenses linked in skill frontmatter remain separate from the skill documentation license.
- SciencePlots and seaborn are separately installed optional Python dependencies; no library code is vendored.
- [SciVisAgentSkills](https://github.com/KuangshiAi/SciVisAgentSkills/tree/5c9ce7d28905af949dc4192b8984a44a7a5d9402) is referenced by an original integration guide and a fixed-commit/hash-checked loader for local use. Its full skill texts are not redistributed in this repository; upstream has no repository license file in the inspected snapshot.
- The drawio integration creates original editable XML from project-provided nodes and edges; it does not bundle the draw.io application.
