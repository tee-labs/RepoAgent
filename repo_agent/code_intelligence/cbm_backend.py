"""codebase-memory-mcp 后端：通过 CLI subprocess 调用 CBM 二进制。

调用方式::

    codebase-memory-mcp cli <tool> --json --flag value ...

CBM 会对仓库建索引（tree-sitter + SQLite 知识图谱），然后通过
``search_graph`` / ``trace_path`` / ``get_code_snippet`` 等工具查询。
所有查询结果映射为与 ``code_info`` 字典格式一致的输出，
确保下游消费者（``DocItem``、``ChatEngine`` 等）无需修改。

MCP CLI 响应信封格式::

    {"content":[{"type":"text","text":"<内嵌 JSON>"}],
     "structuredContent":{<实际工具结果>},
     "isError":false}

``_run_cli`` 会自动解包 ``structuredContent``，调用方直接拿到工具结果。
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from repo_agent.code_intelligence.base import CodeIntelligenceBackend
from repo_agent.log import logger
from repo_agent.utils.meta_info_utils import _is_latest_version_file

# CBM node label → RepoAgent code type
_LABEL_TO_TYPE = {
    "Function": "FunctionDef",
    "Method": "FunctionDef",
    "AsyncFunction": "FunctionDef",
    "Class": "ClassDef",
    "Struct": "ClassDef",
    "Interface": "ClassDef",
}

# 合法的 search_graph label 过滤值（只关注可生成文档的代码对象）
_STRUCTURE_LABELS = ["Function", "Method", "Class"]

# 非项目内文件的标识符（内置库、第三方包等），需要过滤
_NON_PROJECT_FILE_MARKERS = ("<python-builtins>", "<unknown>", "<builtin>")


def _is_project_file(file_path: str) -> bool:
    """判断 file_path 是否是项目内文件（非内置/第三方）。"""
    if not file_path:
        return False
    return not file_path.startswith(_NON_PROJECT_FILE_MARKERS)


def _configured_file_extensions() -> Optional[List[str]]:
    """从 settings 读取已配置的源文件扩展名列表。

    返回 ``None`` 表示 Settings 尚未初始化（如单元测试直接调用后端时），
    调用方据此决定是否按扩展名过滤。
    """
    try:
        from repo_agent.settings import SettingsManager

        settings = SettingsManager.get_setting()
        extensions = settings.project.file_extensions
    except Exception:
        return None
    if not extensions:
        return None
    return [ext.lstrip(".") for ext in extensions]


def _parse_params_from_signature(signature: str) -> List[str]:
    """从 CBM 的 signature 字段解析参数名列表。

    CBM signature 格式如 ``(a, b)`` 或 ``(self, name, age=18)``。
    """
    if not signature:
        return []
    # 提取括号内的内容
    match = re.match(r"\((.*)\)", signature.strip())
    if not match:
        return []
    inner = match.group(1).strip()
    if not inner:
        return []
    params = []
    for part in inner.split(","):
        part = part.strip()
        if not part:
            continue
        # 去掉默认值和类型注解: "name=value" → "name", "name: type" → "name"
        param_name = re.split(r"[=:]", part)[0].strip()
        # 去掉 *args/**kwargs 的星号
        param_name = param_name.lstrip("*")
        if param_name:
            params.append(param_name)
    return params


class CodebaseMemoryBackend(CodeIntelligenceBackend):
    """通过 CLI 调用 codebase-memory-mcp 的代码智能后端。"""

    def __init__(self, binary_path: str = "codebase-memory-mcp"):
        self.binary = binary_path
        # 缓存: (file_path, obj_name, start_line) → qualified_name
        # 在 get_file_structure / get_overall_structure 时填充，
        # find_references 时查用，避免每次 trace_path 都先 search_graph。
        self._qn_cache: Dict[Tuple[str, str, int], str] = {}
        # qualified_name → (file_path, start_line, end_line) 缓存
        # 用于 find_references 中补全 caller 的文件路径和行号
        self._node_info_cache: Dict[str, Tuple[str, int, int]] = {}
        # 标记是否已对当前仓库建过索引
        self._indexed_repo: Optional[str] = None
        # CBM 派生的项目名缓存：repo_str → derived project name。
        # index_repository 接受 repo_path（原始路径），但 search_graph /
        # index_status / get_code_snippet / trace_path 的 project 字段在某些
        # CBM 版本（如 0.8.1）只认派生名（如 "D:\a\b" → "D-a-b"），不做
        # 路径→名解析。派生规则与路径格式相关（\ : / 处理不同），不能本地复刻，
        # 故从 index 响应里读出并缓存。
        self._project_name_cache: Dict[str, str] = {}

    # ── CLI 调用基础设施 ──────────────────────────────────────────

    def _run_cli(self, tool: str, args: dict) -> Any:
        """调用 ``codebase-memory-mcp cli <tool> '<json>' --json``，返回解包结果。

        参数以**单个位置参数 raw-JSON** 传递，而非逐个 ``--flag value`` 或
        ``--args-file``。这是唯一在实测中同时兼容 CBM **0.8.1 与 0.9.0** 的形式：

        - ``--flag value``：0.9.0 接受连字符 flag（``--repo-path``），0.8.1 不认；
          下划线 flag 两个版本行为不一致。不可靠。
        - ``--args-file``：**0.8.1 完全不支持**（实测 Windows 0.8.1 报
          ``repo_path is required``，0.9.0 才有此 flag）。不可靠。
        - raw-JSON 位置参数：0.8.1 和 0.9.0 都接受，且 JSON key 用**下划线**
          （``repo_path``、``file_pattern``），与调用点的 snake_case 一致。

        （上述结论由 ``scripts/diagnose_cbm.py`` 在 Windows 0.8.1 与 Linux 0.9.0
        上对四种形式逐一实测得出。）

        单个 JSON 字符串由 ``subprocess.run(list)`` 作为一个 argv token 传递，
        无需关心各平台的命令行 tokenize 差异。

        自动解包 MCP 响应信封，返回 ``structuredContent``（或退回到
        ``content[0].text`` 解析出的 JSON）。

        Args:
            tool: MCP 工具名（如 ``"search_graph"``）。
            args: 工具参数字典。

        Returns:
            解包后的工具结果（通常是 dict）。

        Raises:
            RuntimeError: 如果二进制不存在、调用失败或返回错误。
        """
        # 过滤 None；空 dict 也允许（某些工具无必填参数）。
        payload = {
            key: value for key, value in args.items() if value is not None
        }
        payload_json = json.dumps(payload, ensure_ascii=False)

        # raw-JSON 作为单个位置参数放在 tool 之后、--json 之前。
        cmd = [self.binary, "cli", tool, payload_json, "--json"]

        logger.debug(
            "CBM CLI: " + cmd[0] + " " + cmd[1] + " " + cmd[2] + " PAYLOAD_JSON --json"
        )
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                # CBM 始终输出 UTF-8。Windows 上 text=True 默认用 locale 编码
                # （中文 Windows 是 GBK）解码，遇到非 ASCII 字节会抛
                # UnicodeDecodeError 并损坏输出。强制 UTF-8 + 替换非法字节。
                encoding="utf-8",
                errors="replace",
                timeout=600,
            )
        except FileNotFoundError:
            raise RuntimeError(
                f"codebase-memory-mcp binary not found at '{self.binary}'. "
                f"Install it via `pip install codebase-memory-mcp` or "
                f"download from https://github.com/DeusData/codebase-memory-mcp/releases."
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"codebase-memory-mcp CLI timed out (600s) for tool '{tool}'."
            )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            raise RuntimeError(
                f"codebase-memory-mcp CLI failed (exit {result.returncode}) "
                f"for tool '{tool}': {stderr}"
            )

        stdout = result.stdout.strip()
        if not stdout:
            raise RuntimeError(
                f"codebase-memory-mcp CLI returned empty output for tool '{tool}'."
            )

        try:
            envelope = json.loads(stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"codebase-memory-mcp CLI returned invalid JSON for tool '{tool}': {e}\n"
                f"Output: {stdout[:500]}"
            )

        # 解包 MCP 响应信封
        if isinstance(envelope, dict):
            # 检查是否是错误响应
            if envelope.get("isError"):
                content = envelope.get("content", [])
                error_text = ""
                if content and isinstance(content, list):
                    error_text = content[0].get("text", "")
                raise RuntimeError(
                    f"codebase-memory-mcp tool '{tool}' returned error: {error_text}\n"
                    f"  payload: {payload!r}"
                )

            # 优先使用 structuredContent（已解析的 JSON）
            structured = envelope.get("structuredContent")
            if structured is not None:
                return structured

            # 退回到 content[0].text（需要二次解析）
            content = envelope.get("content", [])
            if content and isinstance(content, list):
                text = content[0].get("text", "")
                if text:
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        return text

        return envelope

    # ── CodeIntelligenceBackend 实现 ─────────────────────────────

    def index_repo(self, repo_path: Path, mode: str = "full") -> None:
        """对目标仓库建立 CBM 索引。

        先检查 ``index_status``，若索引已存在且覆盖完整则跳过。
        """
        repo_str = str(repo_path)
        if self._indexed_repo == repo_str:
            return

        # 检查是否已有索引
        try:
            status = self._run_cli("index_status", {"project": repo_str})
            if isinstance(status, dict) and not status.get("error"):
                node_count = status.get("nodes", 0)
                if node_count > 0:
                    # index_status 响应里也带派生名，趁机缓存。
                    self._capture_project_name(repo_str, status)
                    logger.info(
                        f"CBM index already exists for {repo_str} "
                        f"({node_count} nodes, {status.get('edges', 0)} edges)."
                    )
                    self._indexed_repo = repo_str
                    return
        except RuntimeError:
            # index_status 失败说明尚未索引，继续建索引
            logger.debug("CBM index_status failed, proceeding to index.")

        logger.info(f"CBM: indexing repository {repo_str} (mode={mode})...")
        result = self._run_cli(
            "index_repository",
            {"repo_path": repo_str, "mode": mode},
        )

        if isinstance(result, dict) and result.get("error"):
            raise RuntimeError(f"CBM indexing failed: {result['error']}")

        node_count = 0
        edge_count = 0
        if isinstance(result, dict):
            node_count = result.get("nodes", 0)
            edge_count = result.get("edges", 0)
            # index_repository 响应里的 "project" 是 CBM 派生的项目名。
            self._capture_project_name(repo_str, result)
        logger.info(
            f"CBM: indexing complete ({node_count} nodes, {edge_count} edges)."
        )
        self._indexed_repo = repo_str

    def _capture_project_name(self, repo_str: str, response: Any) -> None:
        """从 index / index_status 响应里提取并缓存 CBM 派生的项目名。"""
        if not isinstance(response, dict):
            return
        name = response.get("project")
        if isinstance(name, str) and name:
            self._project_name_cache[repo_str] = name

    def _project(self, repo_path: Path) -> str:
        """返回 repo_path 对应的 CBM 派生项目名。

        优先用缓存（index 时已抓取）；未命中则调一次 index_status 获取并缓存。
        若都拿不到（如 CBM 未响应 project 字段），退回原始路径——CBM 0.9.0
        能解析路径，至少不会比现在更差。
        """
        repo_str = str(repo_path)
        cached = self._project_name_cache.get(repo_str)
        if cached:
            return cached
        try:
            status = self._run_cli("index_status", {"project": repo_str})
            self._capture_project_name(repo_str, status)
        except RuntimeError:
            pass
        return self._project_name_cache.get(repo_str, repo_str)

    def get_file_structure(
        self, repo_path: Path, file_path: str
    ) -> List[dict]:
        """通过 ``search_graph`` 查询单个文件中的所有函数/类。"""
        self.index_repo(repo_path)

        results = self._search_structure_nodes(repo_path, file_pattern=file_path)
        code_infos = []
        for node in results:
            code_info = self._node_to_code_info(repo_path, node)
            if code_info:
                code_infos.append(code_info)
        return code_infos

    def get_overall_structure(
        self,
        repo_path: Path,
        file_path_reflections: Dict[str, str],
        jump_files: List[str],
    ) -> Dict[str, List[dict]]:
        """查询全仓库所有已配置扩展名文件的函数/类结构。

        扩展名来自 ``SettingsManager.get_setting().project.file_extensions``
        （即 ``--file-extensions`` 传入的值，如 ``["java"]``）。
        当 Settings 未初始化时（如单元测试直接调用），不过滤扩展名，
        返回 CBM 已索引的全部节点。
        """
        self.index_repo(repo_path)

        extensions = _configured_file_extensions()
        all_nodes: List[dict] = []
        if extensions:
            # CBM search_graph 一次只接受一个 file_pattern，按扩展名分别查询后合并。
            for ext in extensions:
                ext = ext.lstrip(".")
                all_nodes.extend(
                    self._search_structure_nodes(
                        repo_path, file_pattern=f"*.{ext}"
                    )
                )
        else:
            # Settings 未初始化：不过滤扩展名，返回全部结构节点。
            all_nodes = self._search_structure_nodes(repo_path, file_pattern=None)
        # 按 file_path 分组
        structure: Dict[str, List[dict]] = {}
        for node in all_nodes:
            raw_file_path = node.get("file_path", "")
            if not raw_file_path:
                continue

            # 跳过 jump_files（未跟踪文件）
            if raw_file_path in jump_files:
                continue

            # 跳过 fake_file（latest_version 临时文件，任意扩展名）
            if _is_latest_version_file(raw_file_path):
                continue

            code_info = self._node_to_code_info(repo_path, node)
            if code_info:
                structure.setdefault(raw_file_path, []).append(code_info)

        return structure

    def find_references(
        self,
        repo_path: Path,
        file_path: str,
        obj_name: str,
        start_line: int,
        name_column: int,
        in_file_only: bool = False,
    ) -> List[Tuple[str, int, int]]:
        """通过 ``trace_path`` 查找对象的所有调用者。

        返回 ``[(relative_file_path, line, column), ...]`` 列表。
        """
        self.index_repo(repo_path)
        repo_str = str(repo_path)

        # 尝试从缓存获取 qualified_name
        qn = self._qn_cache.get((file_path, obj_name, start_line))

        if qn is None:
            # 回退:用短名搜索，取第一个匹配
            qn = self._resolve_qualified_name(repo_path, file_path, obj_name, start_line)
            if qn is None:
                logger.debug(
                    f"CBM: could not resolve qualified_name for "
                    f"{file_path}/{obj_name} (line {start_line}), skipping references."
                )
                return []

        result = self._run_cli(
            "trace_path",
            {
                "function_name": qn,
                "project": self._project(repo_path),
                "direction": "inbound",
                "mode": "calls",
                "format": "json",
                "depth": 10,
            },
        )

        if not isinstance(result, dict):
            return []

        # trace_path JSON 格式: {"callers": [{"name":..., "qualified_name":..., "hop":...}, ...]}
        # 或者可能返回 {"error": ...} / {"alternatives": [...]} 表示歧义
        if result.get("error") or result.get("alternatives"):
            logger.debug(
                f"CBM trace_path returned ambiguity/error for {qn}: "
                f"{result.get('error', 'ambiguous')}"
            )
            return []

        callers = result.get("callers", [])
        references: List[Tuple[str, int, int]] = []
        for caller in callers:
            caller_qn = caller.get("qualified_name", "")
            if not caller_qn:
                continue

            # 从缓存获取 caller 的 file_path 和 start_line
            caller_file, caller_line, _ = self._lookup_node_info(
                repo_path, caller_qn
            )
            if not caller_file:
                continue

            column = 0
            if in_file_only and caller_file != file_path:
                continue
            references.append((caller_file, caller_line, column))

        return references

    # ── 内部辅助方法 ─────────────────────────────────────────────

    def _search_structure_nodes(
        self,
        repo_path: Path,
        file_pattern: Optional[str] = None,
    ) -> List[dict]:
        """调用 ``search_graph`` 查询所有 Function/Method/Class 节点。

        使用 ``format=json`` 获取完整 JSON 对象，包含 properties 中的
        ``signature`` / ``return_type`` / ``docstring`` 等字段。
        过滤掉非项目文件（如 ``<python-builtins>``）。
        """
        repo_str = str(repo_path)
        args: dict = {
            "project": self._project(repo_path),
            "format": "json",
            "limit": 10000,
        }

        # search_graph 的 label 过滤一次只支持一个 label，
        # 所以分别查询 Function/Method 和 Class，然后合并。
        all_nodes: List[dict] = []
        for label in _STRUCTURE_LABELS:
            args_label = {**args, "label": label}
            try:
                result = self._run_cli("search_graph", args_label)
            except RuntimeError as e:
                logger.warning(f"CBM search_graph failed for label={label}: {e}")
                continue

            if not isinstance(result, dict):
                continue
            if result.get("error"):
                logger.warning(
                    f"CBM search_graph error for label={label}: {result['error']}"
                )
                continue

            nodes = result.get("results", [])
            if file_pattern:
                # 客户端按 file_pattern 过滤文件（如 "*.java" / "*.py"）。
                import fnmatch

                nodes = [
                    n for n in nodes if fnmatch.fnmatch(n.get("file_path", ""), file_pattern)
                ]

            # 过滤非项目文件
            nodes = [
                n for n in nodes if _is_project_file(n.get("file_path", ""))
            ]

            all_nodes.extend(nodes)

        return all_nodes

    def _node_to_code_info(
        self, repo_path: Path, node: dict
    ) -> Optional[dict]:
        """将 CBM search_graph 的节点转换为 ``code_info`` 字典。

        需要调用 ``get_code_snippet`` 获取源码（``source`` 字段）和
        精确的 ``start_line`` / ``end_line``。
        同时缓存 ``qualified_name`` 供 ``find_references`` 使用。
        """
        name = node.get("name", "")
        if not name:
            return None

        label = node.get("label", "")
        code_type = _LABEL_TO_TYPE.get(label, "FunctionDef")

        file_path = node.get("file_path", "")
        qualified_name = node.get("qualified_name", "")

        # search_graph 不返回 start_line/end_line，需要从 get_code_snippet 获取
        start_line = node.get("start_line", 0)
        end_line = node.get("end_line", start_line)

        # 从 signature 解析参数列表
        signature = node.get("signature", "")
        params = _parse_params_from_signature(signature)

        # 获取源码和精确行号
        code_content = ""
        have_return = False
        if qualified_name:
            try:
                snippet = self._run_cli(
                    "get_code_snippet",
                    {
                        "qualified_name": qualified_name,
                        "project": self._project(repo_path),
                    },
                )
                if isinstance(snippet, dict) and not snippet.get("error"):
                    code_content = snippet.get("source", "")
                    # get_code_snippet 返回精确的 start_line/end_line
                    if snippet.get("start_line"):
                        start_line = snippet["start_line"]
                    if snippet.get("end_line"):
                        end_line = snippet["end_line"]
                    # 如果 snippet 中有 signature，优先用它解析 params
                    # （比 search_graph 的更准确）
                    snippet_sig = snippet.get("signature", "")
                    if snippet_sig:
                        params = _parse_params_from_signature(snippet_sig)
            except RuntimeError as e:
                logger.debug(f"CBM get_code_snippet failed for {qualified_name}: {e}")

        # 缓存 qualified_name → node info
        if qualified_name and start_line > 0:
            self._qn_cache[(file_path, name, start_line)] = qualified_name
            self._node_info_cache[qualified_name] = (file_path, start_line, end_line)

        # have_return: 检查源码中是否含 return 语句（与 FileHandler 逻辑一致）
        if code_content:
            have_return = "return" in code_content

        # name_column: 从源码第一行查找名称位置（与 FileHandler 逻辑一致）
        name_column = 0
        if code_content:
            first_line = code_content.split("\n", 1)[0]
            pos = first_line.find(name)
            if pos >= 0:
                name_column = pos

        return {
            "type": code_type,
            "name": name,
            "md_content": [],
            "code_start_line": start_line,
            "code_end_line": end_line,
            "params": params,
            "have_return": have_return,
            "code_content": code_content,
            "name_column": name_column,
        }

    def _lookup_node_info(
        self, repo_path: Path, qualified_name: str
    ) -> Tuple[str, int, int]:
        """通过缓存或 search_graph 查找节点的 (file_path, start_line, end_line)。

        用于 ``find_references`` 中补全 trace_path 返回的 caller 信息。
        """
        # 先查缓存
        if qualified_name in self._node_info_cache:
            return self._node_info_cache[qualified_name]

        # 通过 get_code_snippet 获取信息
        try:
            snippet = self._run_cli(
                "get_code_snippet",
                {
                    "qualified_name": qualified_name,
                    "project": self._project(repo_path),
                },
            )
            if isinstance(snippet, dict) and not snippet.get("error"):
                # file_path 在 snippet 中是绝对路径，需要转成相对路径
                file_path = snippet.get("file_path", "")
                repo_str = str(repo_path)
                if file_path.startswith(repo_str):
                    file_path = file_path[len(repo_str):].lstrip("/")

                start_line = snippet.get("start_line", 0)
                end_line = snippet.get("end_line", start_line)

                if file_path and start_line > 0:
                    self._node_info_cache[qualified_name] = (
                        file_path,
                        start_line,
                        end_line,
                    )
                    return self._node_info_cache[qualified_name]
        except RuntimeError:
            pass

        return ("", 0, 0)

    def _resolve_qualified_name(
        self,
        repo_path: Path,
        file_path: str,
        obj_name: str,
        start_line: int,
    ) -> Optional[str]:
        """通过 ``search_graph`` 精确查找对象的 ``qualified_name``。

        当 ``_qn_cache`` 未命中时使用。通过 ``name_pattern`` + 文件路径过滤。
        """
        repo_str = str(repo_path)
        try:
            result = self._run_cli(
                "search_graph",
                {
                    "project": self._project(repo_path),
                    "name_pattern": obj_name,
                    "file_pattern": file_path,
                    "format": "json",
                    "limit": 50,
                },
            )
        except RuntimeError:
            return None

        if not isinstance(result, dict) or result.get("error"):
            return None

        for node in result.get("results", []):
            if (
                node.get("name") == obj_name
                and node.get("file_path") == file_path
            ):
                qn = node.get("qualified_name", "")
                if qn:
                    self._qn_cache[(file_path, obj_name, start_line)] = qn
                    return qn

        # 回退:取第一个 name 匹配的节点
        for node in result.get("results", []):
            if node.get("name") == obj_name:
                qn = node.get("qualified_name", "")
                if qn:
                    self._qn_cache[(file_path, obj_name, start_line)] = qn
                    return qn

        return None
