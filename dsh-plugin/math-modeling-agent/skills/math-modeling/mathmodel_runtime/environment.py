"""Read-only, project-aware dependency checks in bounded isolated subprocesses."""
from concurrent.futures import ThreadPoolExecutor, wait
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import time

from .storage import now


IMPORT_TIMEOUT = 8
COMMAND_TIMEOUT = 4
REPORT_TIMEOUT = 60
MAX_WORKERS = 4
# These ranges match the installable feature extras in pyproject.toml.
DEPENDENCIES = {
    "numpy": ("numpy", "numpy>=1.26,<3", "基础数组运算与数据图表"),
    "pandas": ("pandas", "pandas>=2.2,<4", "表格数据处理与图表输入"),
    "matplotlib": ("matplotlib", "matplotlib>=3.8,<4", "基础科研绘图、坐标轴与多格式导出"),
    "pillow": ("PIL.Image", "Pillow>=10,<13", "图像读取、图表及文档渲染结果检查"),
    "python-docx": ("docx", "python-docx>=1.1,<2", "生成和检查 Word DOCX 论文"),
    "lxml": ("lxml.etree", "lxml>=5,<7", "Word XML 与公式结构处理"),
    "defusedxml": ("defusedxml.minidom", "defusedxml>=0.7.1,<1", "文档工具的安全 XML 解析"),
    "pypdf": ("pypdf", "pypdf>=5,<7", "PDF 材料文本提取、页数与结构检查"),
    "pymupdf": ("fitz", "PyMuPDF>=1.24,<2", "PDF 页面栅格化与图像检查，可作为 Poppler 的替代路线"),
    "openpyxl": ("openpyxl", "openpyxl>=3.1,<4", "读取 XLSX/XLSM 附件与工作簿处理"),
    "scipy": ("scipy", "scipy>=1.12,<2", "按模型需要进行优化、统计与数值计算"),
    "scikit-learn": ("sklearn", "scikit-learn>=1.4,<2", "按模型需要进行预测、预处理和交叉验证"),
    "networkx": ("networkx", "networkx>=3.2,<4", "按模型需要进行图与网络分析"),
    "salib": ("SALib", "SALib>=1.5,<2", "按需运行真实 Morris/Sobol 敏感性分析"),
    "jsonschema": ("jsonschema", "jsonschema>=4.21,<5", "额外 JSON Schema 工具；核心门禁已有标准库校验"),
    "scienceplots": ("scienceplots", "SciencePlots>=2.1,<3", "已选科研绘图样式；没有 LaTeX 时使用 no-latex"),
    "seaborn": ("seaborn", "seaborn>=0.13.2,<0.14", "已选统计比较、分布图与热图"),
}

_IMPORT_SCRIPT = r'''
import contextlib, importlib, importlib.metadata, json, os, sys
module, distribution = sys.argv[1:3]
try:
    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        importlib.import_module(module)
        version = importlib.metadata.version(distribution) if distribution else sys.version.split()[0]
    result = {"status": "ready", "version": version}
except importlib.metadata.PackageNotFoundError:
    result = {"status": "error", "reason": "metadata_missing"}
except ModuleNotFoundError as error:
    missing = error.name in {module, module.split(".")[0]}
    result = {"status": "missing" if missing else "error", "reason": "module_missing" if missing else "dependency_missing"}
except BaseException:
    result = {"status": "error", "reason": "import_failed"}
print(json.dumps(result))
'''


def shell_command(argv, platform=None):
    """Quote literal arguments for the platform shell without interpolation."""
    if (platform or sys.platform) == "win32":
        return "& " + " ".join("'" + str(value).replace("'", "''") + "'" for value in argv)
    return shlex.join([str(value) for value in argv])


def install_command(specifications, *, executable=None, platform=None):
    if not specifications:
        return None
    return shell_command([executable or sys.executable, "-m", "pip", "install", *specifications], platform)


def _remaining(deadline, timeout):
    return max(0, min(timeout, deadline - time.monotonic()))


def _run_probe(argv, timeout):
    """Bound runtime/output and keep cache files, project imports and secrets out."""
    if timeout <= 0:
        return {"status": "error", "reason": "deadline"}
    allowed = {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "HOME", "USERPROFILE",
               "APPDATA", "LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "LANG", "LC_ALL", "LD_LIBRARY_PATH",
               "DYLD_LIBRARY_PATH", "CONDA_PREFIX", "VIRTUAL_ENV", "PYTHONUSERBASE", "PYTHONNOUSERSITE"}
    environment = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    with tempfile.TemporaryDirectory(prefix="mathmodel-environment-") as directory:
        environment.update(MPLCONFIGDIR=directory, XDG_CACHE_HOME=directory, NUMBA_CACHE_DIR=directory,
                           MPLBACKEND="Agg", QT_QPA_PLATFORM="offscreen")
        with tempfile.TemporaryFile(dir=directory) as output, tempfile.TemporaryFile(dir=directory) as errors:
            try:
                process = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=output, stderr=errors, cwd=directory,
                                         env=environment, timeout=timeout, check=False,
                                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except subprocess.TimeoutExpired:
                return {"status": "error", "reason": "timeout"}
            except OSError:
                return {"status": "error", "reason": "start_failed"}
            output.seek(0)
            errors.seek(0)
            return {"returncode": process.returncode, "stdout": output.read(16384), "stderr": errors.read(16384)}


def probe_python(module, distribution, *, deadline=None):
    deadline = deadline if deadline is not None else time.monotonic() + IMPORT_TIMEOUT
    result = _run_probe([sys.executable, "-P", "-B", "-c", _IMPORT_SCRIPT, module, distribution], _remaining(deadline, IMPORT_TIMEOUT))
    if "reason" in result:
        return {"status": "error", "detail": _reason(result["reason"])}
    if result["returncode"] != 0:
        return {"status": "error", "detail": "隔离导入进程异常退出；未返回其输出或异常内容。"}
    try:
        value = json.loads(result["stdout"])
        if value.get("status") == "ready":
            version = value.get("version", "")
            if not isinstance(version, str) or not re.fullmatch(r"[0-9][A-Za-z0-9.!+_-]{0,79}", version):
                raise ValueError("Invalid version metadata")
            return {"status": "ready", "version": version, "detail": "当前解释器标准 site 路径（含已启用的用户安装）实际导入成功；排除项目目录和 PYTHONPATH。"}
        if value.get("status") in {"missing", "error"}:
            return {"status": value["status"], "detail": _reason(value.get("reason"))}
    except (ValueError, TypeError, AttributeError, UnicodeError):
        pass
    return {"status": "error", "detail": "隔离导入未返回有效报告；未展示导入输出。"}


def _reason(reason):
    return {
        "module_missing": "当前解释器的隔离环境缺少该模块。",
        "dependency_missing": "模块存在，但导入时缺少其内部依赖。",
        "metadata_missing": "模块可导入，但缺少可核验的发行版本元数据。",
        "import_failed": "实际导入失败，可能是二进制或依赖不兼容；原始异常未返回。",
        "timeout": "检测子进程超时，尚不能确认可用。",
        "deadline": "本次检测达到整体时间预算，尚不能确认可用。",
        "start_failed": "无法启动检测进程。",
    }.get(reason, "无法确认此依赖可用。")


def _in_range(version, specification):
    requirement = re.fullmatch(r"[A-Za-z0-9_.-]+>=([0-9.]+),<([0-9.]+)", specification)
    release = re.fullmatch(r"([0-9]+(?:\.[0-9]+)*)(?:\.post[0-9]+)?(?:\+[A-Za-z0-9.]+)?", version)
    if not release or not requirement:
        return False
    numbers = [tuple(int(part) for part in value.split(".")) for value in (release[1], requirement[1], requirement[2])]
    length = max(map(len, numbers))
    current, lower, upper = [parts + (0,) * (length - len(parts)) for parts in numbers]
    return lower <= current < upper


def probe_package(identifier, deadline):
    module, specification, _ = DEPENDENCIES[identifier]
    distribution = specification.split(">=", 1)[0]
    result = probe_python(module, distribution, deadline=deadline)
    if result["status"] == "ready" and not _in_range(result["version"], specification):
        result.update(status="error", detail="已安装版本不满足本项目声明范围：" + specification)
    return result


def _find_command(command, project_root=None):
    """Search absolute PATH directories without Windows' implicit cwd lookup."""
    project_root = Path(project_root).resolve() if project_root is not None else None
    extensions = [""] if sys.platform != "win32" else [".exe", ".com"]
    for value in os.get_exec_path():
        directory = Path(value)
        if not value or not directory.is_absolute():
            continue
        directory = directory.resolve()
        if project_root is not None and directory.is_relative_to(project_root):
            continue
        for extension in extensions:
            candidate = directory / (command + extension)
            if candidate.is_file() and os.access(candidate, os.X_OK):
                resolved = candidate.resolve()
                if project_root is None or not resolved.is_relative_to(project_root):
                    return str(candidate)
    return None


def probe_command(candidates, *, arguments=("--version",), deadline=None, project_root=None):
    deadline = deadline if deadline is not None else time.monotonic() + COMMAND_TIMEOUT
    previous = None
    for command in candidates:
        executable = _find_command(command, project_root)
        if not executable:
            continue
        result = _run_probe([executable, *arguments], _remaining(deadline, COMMAND_TIMEOUT))
        if "reason" in result:
            previous = {"status": "error", "detail": _reason(result["reason"])}
            continue
        # Return only a bounded numeric version token, never arbitrary command output.
        token = re.search(rb"\b\d+(?:\.\d+){1,5}\b", result["stdout"] + result["stderr"])
        if result["returncode"] == 0 and token:
            return {"status": "ready", "version": token[0].decode("ascii"), "detail": command + " 已实际响应本地版本查询。"}
        previous = {"status": "error", "detail": command + " 的本地版本查询未成功；未返回其输出。"}
    return previous or {"status": "missing", "detail": "当前 PATH 未发现 " + " / ".join(candidates) + "；也可能位于另一个专用环境。"}


def _item(identifier, label, purpose, requirement, result, prompt, command=None):
    return {"id": identifier, "label": label, "purpose": purpose, "requirement": requirement, **result,
            "install_command": command if result["status"] in {"missing", "error"} else None,
            "agent_prompt": prompt}


def environment_report(store, state):
    """Inspect saved preferences only; never migrate, invalidate or save a project."""
    project = state["project"]
    scope = project.get("scope", "full")
    paper_format = project.get("paperFormat", "word")
    graphics = project.get("graphicsTools", {})
    paper = scope in {"full", "paper"}
    word = paper and paper_format in {"word", "word+latex"}
    latex = paper and paper_format in {"latex", "word+latex"}
    plotting = scope in {"full", "programming"}
    suffixes = {Path(item.get("filename", item.get("path", ""))).suffix.lower() for item in state.get("inputs", {}).values()}
    rules = project.get("rules", {})
    word_render = word and (rules.get("require_render") or "max_pages" in rules)
    required = set()
    if plotting:
        required.update({"numpy", "pandas", "matplotlib", "pillow"})
    if word:
        required.update({"python-docx", "lxml", "defusedxml", "pillow"})
    if ".pdf" in suffixes or latex or word_render:
        required.add("pypdf")
    if suffixes & {".xlsx", ".xlsm"}:
        required.add("openpyxl")
    selected = {name for name in ("scienceplots", "seaborn") if graphics.get(name) is True}
    if selected:
        selected.update({"numpy", "matplotlib"})
    if graphics.get("seaborn") is True:
        selected.add("pandas")
    executable = os.path.abspath(sys.executable)
    python_supported = (3, 11) <= sys.version_info[:2] < (3, 14)
    project_arg = shell_command([str(store.root)])
    python_prompt = ("为此数学建模项目检查 Python 3.11–3.13 的独立环境。当前解释器为 " + shell_command([executable])
                     + "，项目目录为 " + project_arg + "。如需另建环境，先保留已有依赖与项目文件，再让宿主使用该解释器；不要卸载现有 Python。")
    items = [_item("python", "Python 3.11–3.13", "标准库运行时与所有 Python 工具的实际解释器", "required",
                   {"status": "ready" if python_supported else "error", "version": sys.version.split()[0],
                    "detail": "实际运行本次检测的解释器；-P 排除项目目录，保留标准 site 与已启用的用户安装，仅不加载 PYTHONPATH。" if python_supported else "当前 Python 超出已声明支持范围。"}, python_prompt)]

    deadline = time.monotonic() + REPORT_TIMEOUT
    command_checks = {"latex-engine": (("xelatex", "lualatex", "pdflatex"), ("--version",)),
                      "pandoc": (("pandoc",), ("--version",)), "libreoffice": (("soffice", "libreoffice"), ("--version",)),
                      "poppler": (("pdftoppm",), ("-v",)), "paraview": (("pvpython",), ("--version",)),
                      "napari": (("napari",), ("--version",))}
    results = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(probe_package, name, deadline): name for name in DEPENDENCIES}
        for name, (candidates, arguments) in command_checks.items():
            futures[executor.submit(probe_command, candidates, arguments=arguments, deadline=deadline, project_root=store.root)] = name
        done, pending = wait(futures, timeout=_remaining(deadline, REPORT_TIMEOUT))
        for future in done:
            try:
                results[futures[future]] = future.result()
            except Exception:
                results[futures[future]] = {"status": "error", "detail": "检测器未能完成此项检查；未展示原始异常。"}
        for future in pending:
            future.cancel()
            results[futures[future]] = {"status": "error", "detail": _reason("deadline")}

    for identifier, (_, specification, purpose) in DEPENDENCIES.items():
        label = specification.split(">=", 1)[0]
        requirement = "selected" if identifier in required or identifier in selected else "optional"
        command = install_command([specification], executable=executable) if python_supported else None
        prompt = ("请检查项目 " + project_arg + " 的 " + label + "（" + purpose + "）。使用解释器 " + shell_command([executable])
                  + "，先核对已有环境与依赖冲突；只处理此项声明范围 " + specification + "。")
        if command:
            prompt += " 可用命令：" + command + "。"
        prompt += " 遵循宿主授权，不使用 sudo、不卸载其他依赖、不执行远程安装脚本；完成后重新运行 environment 并实际导入验证。"
        items.append(_item(identifier, label, purpose, requirement, results[identifier], prompt, command))

    for identifier, label, purpose, requirement in (
        ("latex-engine", "LaTeX 编译引擎", "LaTeX 论文需要至少一个可运行的编译引擎", "selected" if latex else "optional"),
        ("pandoc", "Pandoc", "按需转换文档；原生 DOCX 写作无需强制安装", "optional"),
        ("libreoffice", "LibreOffice", "可选 DOCX→PDF 渲染路线；也可使用已授权的其他文档渲染器", "optional"),
        ("poppler", "Poppler / pdftoppm", "PDF 页面转图；可按任务选择 PyMuPDF 等替代路线", "optional"),
        ("paraview", "ParaView / pvpython", "仅在三维网格、流场或体数据任务中选择，通常使用专用环境", "optional"),
        ("napari", "napari", "仅在显微多通道或时序图像任务中选择，通常使用专用环境", "optional"),
    ):
        prompt = ("请按项目 " + project_arg + " 的实际任务检查 " + label + "。" + purpose
                  + "。核对操作系统、已有安装和官方安装方式，优先专用环境，遵循宿主授权；不要自动安装其他可选工具，不使用 sudo、卸载命令或远程下载执行脚本。安装后查询真实版本并重跑 environment。")
        items.append(_item(identifier, label, purpose, requirement, results[identifier], prompt))

    drawio_path = store.skill / "tools/figure/scripts/editable_diagram.py"
    items.append(_item("drawio", "drawio 可编辑源文件", "使用随 Skill 提供的 XML 生成脚本，桌面端仅为可选导出路线", "selected" if graphics.get("drawio") else "optional",
                       {"status": "ready" if drawio_path.is_file() else "missing", "detail": "内置 XML 生成脚本已找到；不要求安装 draw.io 桌面端，尚未验证实际渲染。" if drawio_path.is_file() else "当前 Skill 根缺少 XML 生成脚本，请检查是否仅安装了 runtime。"},
                       "请确认当前宿主加载完整 Skill，并读取 tools/figure/integrations/drawio/SKILL.md；优先使用内置 XML 生成器，不为创建 .drawio 强制安装桌面端。按交付格式再核验导出与字体。"))
    key_present = bool(os.environ.get("OPENROUTER_API_KEY", "").strip())
    items.append(_item("scientific-schematics", "scientific-schematics 服务", "概念或机制示意图；仅检查环境变量存在，不调用生成服务", "selected" if graphics.get("scientific-schematics") else "optional",
                       {"status": "manual", "detail": ("OPENROUTER_API_KEY 已配置" if key_present else "当前进程未配置 OPENROUTER_API_KEY") + "；未读取 .env、未返回密钥内容、未在线验证。可按宿主授权使用其他图像生成后端。"},
                       "请先读取 scientific-schematics 集成规范，确认已授权的生成后端及实际配置；不要打印或索取聊天中的密钥，不自动提交题目或图片。仅在获得该任务的服务调用授权后验证可用性，并记录实际后端。"))
    items.append(_item("scivis-agent-skills", "SciVisAgentSkills 路由", "按数据选择 ParaView、napari、VMD 或 TTK，不是一组必须同时安装的软件", "selected" if graphics.get("scivis-agent-skills") else "optional",
                       {"status": "manual", "detail": "尚需按网格/显微/分子等实际数据选择一种路线；下列软件检查不证明该项目已具备完整三维渲染能力。"},
                       "请读取 tools/figure/integrations/scivis-agent-skills/SKILL.md，先确认当前项目的数据类型和渲染目标，再只检查匹配的一项 ParaView/napari/VMD/TTK 及其专用环境。不要批量安装所有三维工具。"))
    items.append(_item("vmd", "VMD", "仅在分子结构与轨迹可视化任务中选择，通常使用专用环境", "optional",
                       {"status": "manual", "detail": "PATH 中已找到 VMD；版本、授权与文本模式执行需按平台核验。" if _find_command("vmd", store.root) else "当前 PATH 未发现 VMD；需要时检查专用安装或环境。"},
                       "仅在项目包含分子结构或轨迹时检查 VMD 及对应读取器，确认官方平台安装方式、现有许可和版本；不要因此安装其他三维软件，也不要把程序路径存在当作渲染通过。"))
    if word_render:
        renderer_ready = results["libreoffice"]["status"] == "ready"
        items.append(_item("word-renderer", "Word 页面渲染", "当前明确的页数或渲染规则需要 DOCX 对应的真实渲染产物", "selected",
                           {"status": "ready" if renderer_ready else "manual", "detail": "LibreOffice 已响应版本查询；仍须实际生成来源绑定的 PDF/渲染图。" if renderer_ready else "需要确认一种 DOCX 渲染路线；可用已授权的 Word、LibreOffice 或宿主转换服务。"},
                           "请根据当前论文页数/渲染规则选择已有的 DOCX 渲染器；若缺少，核验官方安装方式并遵循宿主授权。保留原 DOCX，实际生成 PDF/页面图并登记输入、输出和源码哈希，不能只凭程序存在声称完成。"))
    if suffixes & {".doc", ".xls"}:
        items.append(_item("legacy-office-input", "旧版 Office 材料", "保留原始 .doc/.xls，并按实际文件类型转换或读取", "selected",
                           {"status": "manual", "detail": "旧版二进制格式不能以安装 python-docx/openpyxl 冒充完成解析。"},
                           "请识别项目中旧 .doc/.xls 原件，使用已授权工具转换为新副本或提取内容；保留原件与哈希，检查公式、表格和编码，不覆盖原文件，不声称未执行的提取已完成。"))

    needs = [item for item in items if item["requirement"] != "optional" and item["status"] != "ready"]
    specs = [DEPENDENCIES[item["id"]][1] for item in needs if item["id"] in DEPENDENCIES and item["status"] in {"missing", "error"}]
    aggregate_command = install_command(specs, executable=executable) if python_supported else None
    aggregate_prompt = ("请按项目已保存配置修复以下必需或已选环境项；不要安装未选择的可选组件。项目：" + project_arg + "。\n"
                        + "\n".join("- " + item["label"] + "：" + item["detail"] + " " + item["agent_prompt"] for item in needs)
                        if needs else "当前已检测的必需与已选环境项可用，无需安装。实际求解、编译、材料提取和渲染仍须执行并验收。")
    return {"ok": True, "checked_at": now(), "executable": executable, "python": sys.version.split()[0], "platform": sys.platform,
            "ready": not needs, "items": items, "install_command": aggregate_command, "agent_prompt": aggregate_prompt}
