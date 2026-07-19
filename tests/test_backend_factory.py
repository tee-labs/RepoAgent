"""测试代码智能后端工厂和多语言配置。"""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from repo_agent.code_intelligence import get_backend, reset_backend
from repo_agent.code_intelligence.base import CodeIntelligenceBackend


class TestBackendFactory(unittest.TestCase):
    """测试 get_backend() 工厂函数。"""

    def setUp(self):
        """每个测试前重置后端缓存和 settings 单例。"""
        reset_backend()
        from repo_agent.settings import SettingsManager

        SettingsManager._setting_instance = None

    def tearDown(self):
        reset_backend()
        from repo_agent.settings import SettingsManager

        SettingsManager._setting_instance = None

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False)
    def test_get_backend_returns_codebase_memory(self):
        """测试获取 codebase_memory 后端。"""
        from repo_agent.settings import SettingsManager

        SettingsManager.initialize_with_params(
            target_repo=Path("."),
            markdown_docs_name="markdown_docs",
            hierarchy_name=".project_doc_record",
            ignore_list=[],
            language="English",
            max_thread_count=4,
            log_level="INFO",
            model="gpt-4o-mini",
            temperature=0.2,
            request_timeout=60,
            openai_base_url="https://api.openai.com/v1",
            cbm_binary_path="/usr/local/bin/codebase-memory-mcp",
        )

        backend = get_backend()
        from repo_agent.code_intelligence.cbm_backend import CodebaseMemoryBackend

        self.assertIsInstance(backend, CodebaseMemoryBackend)
        self.assertIsInstance(backend, CodeIntelligenceBackend)
        self.assertEqual(backend.binary, "/usr/local/bin/codebase-memory-mcp")

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False)
    def test_backend_singleton(self):
        """测试后端实例是单例（多次 get_backend 返回同一实例）。"""
        from repo_agent.settings import SettingsManager

        SettingsManager.initialize_with_params(
            target_repo=Path("."),
            markdown_docs_name="markdown_docs",
            hierarchy_name=".project_doc_record",
            ignore_list=[],
            language="English",
            max_thread_count=4,
            log_level="INFO",
            model="gpt-4o-mini",
            temperature=0.2,
            request_timeout=60,
            openai_base_url="https://api.openai.com/v1",
        )

        backend1 = get_backend()
        backend2 = get_backend()
        self.assertIs(backend1, backend2)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False)
    def test_reset_backend(self):
        """测试 reset_backend 后重新获取会创建新实例。"""
        from repo_agent.settings import SettingsManager

        SettingsManager.initialize_with_params(
            target_repo=Path("."),
            markdown_docs_name="markdown_docs",
            hierarchy_name=".project_doc_record",
            ignore_list=[],
            language="English",
            max_thread_count=4,
            log_level="INFO",
            model="gpt-4o-mini",
            temperature=0.2,
            request_timeout=60,
            openai_base_url="https://api.openai.com/v1",
        )

        backend1 = get_backend()
        reset_backend()
        backend2 = get_backend()
        self.assertIsNot(backend1, backend2)


class TestFileExtensionsConfig(unittest.TestCase):
    """测试多语言文件扩展名配置。"""

    def setUp(self):
        reset_backend()
        from repo_agent.settings import SettingsManager

        SettingsManager._setting_instance = None

    def tearDown(self):
        reset_backend()
        from repo_agent.settings import SettingsManager

        SettingsManager._setting_instance = None

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False)
    def test_default_file_extensions_is_py(self):
        """测试默认文件扩展名为 ['py']。"""
        from repo_agent.settings import SettingsManager

        SettingsManager.initialize_with_params(
            target_repo=Path("."),
            markdown_docs_name="markdown_docs",
            hierarchy_name=".project_doc_record",
            ignore_list=[],
            language="English",
            max_thread_count=4,
            log_level="INFO",
            model="gpt-4o-mini",
            temperature=0.2,
            request_timeout=60,
            openai_base_url="https://api.openai.com/v1",
        )

        setting = SettingsManager.get_setting()
        self.assertEqual(setting.project.file_extensions, ["py"])

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False)
    def test_custom_file_extensions_java(self):
        """测试配置 Java 文件扩展名。"""
        from repo_agent.settings import SettingsManager

        SettingsManager.initialize_with_params(
            target_repo=Path("."),
            markdown_docs_name="markdown_docs",
            hierarchy_name=".project_doc_record",
            ignore_list=[],
            language="English",
            max_thread_count=4,
            log_level="INFO",
            model="gpt-4o-mini",
            temperature=0.2,
            request_timeout=60,
            openai_base_url="https://api.openai.com/v1",
            file_extensions=["java"],
        )

        setting = SettingsManager.get_setting()
        self.assertEqual(setting.project.file_extensions, ["java"])

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False)
    def test_multi_language_extensions(self):
        """测试多语言混合扩展名配置。"""
        from repo_agent.settings import SettingsManager

        SettingsManager.initialize_with_params(
            target_repo=Path("."),
            markdown_docs_name="markdown_docs",
            hierarchy_name=".project_doc_record",
            ignore_list=[],
            language="English",
            max_thread_count=4,
            log_level="INFO",
            model="gpt-4o-mini",
            temperature=0.2,
            request_timeout=60,
            openai_base_url="https://api.openai.com/v1",
            file_extensions=["py", "java", "go"],
        )

        setting = SettingsManager.get_setting()
        self.assertEqual(setting.project.file_extensions, ["py", "java", "go"])


class TestSourceToMdConversion(unittest.TestCase):
    """测试 _source_to_md 函数的扩展名替换逻辑。"""

    def test_py_to_md(self):
        from repo_agent.runner import _source_to_md

        self.assertEqual(_source_to_md("src/main.py", ["py"]), "src/main.md")

    def test_java_to_md(self):
        from repo_agent.runner import _source_to_md

        self.assertEqual(
            _source_to_md("com/example/Foo.java", ["java"]),
            "com/example/Foo.md",
        )

    def test_multi_ext(self):
        from repo_agent.runner import _source_to_md

        self.assertEqual(_source_to_md("a.py", ["py", "java"]), "a.md")
        self.assertEqual(_source_to_md("b.java", ["py", "java"]), "b.md")


class TestGitignoreCheckerExtensions(unittest.TestCase):
    """测试 GitignoreChecker 的多扩展名支持。"""

    def test_py_only(self):
        import os
        import tempfile

        from repo_agent.utils.gitignore_checker import GitignoreChecker

        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建 .py 和 .java 文件
            with open(os.path.join(tmpdir, "foo.py"), "w") as f:
                f.write("")
            with open(os.path.join(tmpdir, "bar.java"), "w") as f:
                f.write("")

            gitignore_path = os.path.join(tmpdir, ".gitignore")
            with open(gitignore_path, "w") as f:
                f.write("")

            checker = GitignoreChecker(tmpdir, gitignore_path, file_extensions=["py"])
            files = checker.check_files_and_folders()
            self.assertIn("foo.py", files)
            self.assertNotIn("bar.java", files)

    def test_java_only(self):
        import os
        import tempfile

        from repo_agent.utils.gitignore_checker import GitignoreChecker

        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "foo.py"), "w") as f:
                f.write("")
            with open(os.path.join(tmpdir, "bar.java"), "w") as f:
                f.write("")

            gitignore_path = os.path.join(tmpdir, ".gitignore")
            with open(gitignore_path, "w") as f:
                f.write("")

            checker = GitignoreChecker(
                tmpdir, gitignore_path, file_extensions=["java"]
            )
            files = checker.check_files_and_folders()
            self.assertNotIn("foo.py", files)
            self.assertIn("bar.java", files)

    def test_multi_extensions(self):
        import os
        import tempfile

        from repo_agent.utils.gitignore_checker import GitignoreChecker

        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "foo.py"), "w") as f:
                f.write("")
            with open(os.path.join(tmpdir, "bar.java"), "w") as f:
                f.write("")
            with open(os.path.join(tmpdir, "baz.go"), "w") as f:
                f.write("")

            gitignore_path = os.path.join(tmpdir, ".gitignore")
            with open(gitignore_path, "w") as f:
                f.write("")

            checker = GitignoreChecker(
                tmpdir, gitignore_path, file_extensions=["py", "java"]
            )
            files = checker.check_files_and_folders()
            self.assertIn("foo.py", files)
            self.assertIn("bar.java", files)
            self.assertNotIn("baz.go", files)


class TestCliRawJsonArgs(unittest.TestCase):
    """测试 ``_run_cli`` 通过单个位置参数 raw-JSON 传递参数。

    CBM 在 0.8.1 与 0.9.0 上的参数形式支持不一致（由
    ``scripts/diagnose_cbm.py`` 在 Windows 0.8.1 + Linux 0.9.0 上对四种形式
    逐一实测确认）：

    - ``--flag value``：0.9.0 接受连字符 flag，0.8.1 不认 → 不可靠。
    - ``--args-file``：**0.8.1 完全不支持** → 不可靠。
    - **raw-JSON 位置参数**：两个版本都接受，JSON key 用下划线（``repo_path``）
      → 唯一跨版本兼容的形式，本类锁定它。

    本测试不依赖 CBM 二进制，通过 mock ``subprocess.run`` 捕获实际命令，
    验证命令形状（raw-JSON 作为位置参数）、payload 内容、错误信息。
    """

    def _make_capture_mock(self):
        """返回 (fake_run, records)。

        records 收集每次调用收到的 (cmd, payload)——payload 是从命令中第 3 个
        位置参数（raw-JSON 字符串）反序列化出来的。
        """
        import json as _json
        from subprocess import CompletedProcess

        records: list[tuple[list[str], dict]] = []

        def fake_run(cmd, *args, **kwargs):
            # cmd 形如 [binary, "cli", tool, "<json>", "--json"]
            payload = {}
            try:
                payload = _json.loads(cmd[3])
            except (IndexError, ValueError, TypeError):
                pass
            records.append((list(cmd), payload))
            return CompletedProcess(
                args=cmd,
                returncode=0,
                stdout='{"structuredContent": {}, "isError": false}',
                stderr="",
            )

        return fake_run, records

    def test_command_passes_payload_as_positional_json(self):
        """命令应是 ``[binary, cli, <tool>, <json-string>, --json]``。"""
        import json as _json

        from repo_agent.code_intelligence.cbm_backend import CodebaseMemoryBackend

        backend = CodebaseMemoryBackend(binary_path="codebase-memory-mcp")
        fake_run, records = self._make_capture_mock()

        with patch(
            "repo_agent.code_intelligence.cbm_backend.subprocess.run",
            side_effect=fake_run,
        ):
            backend._run_cli(
                "index_repository",
                {"repo_path": "/tmp/repo", "mode": "full"},
            )

        self.assertEqual(len(records), 1)
        cmd, payload = records[0]
        # 骨架：binary cli <tool> <json-string> --json
        self.assertEqual(cmd[0:3], ["codebase-memory-mcp", "cli", "index_repository"])
        self.assertEqual(cmd[4], "--json")
        # 第 4 个元素是合法 JSON，解析后等于 payload。
        self.assertEqual(_json.loads(cmd[3]), payload)
        # 关键：不应出现任何逐个 flag 或 --args-file。
        for token in cmd:
            self.assertFalse(token.startswith("--repo"), f"unexpected flag: {token}")
        self.assertNotIn("--args-file", cmd)
        self.assertNotIn("--mode", cmd)

    def test_payload_keeps_underscore_keys(self):
        """raw-JSON 的 key 保持下划线（CBM JSON 形式要求）。"""
        from repo_agent.code_intelligence.cbm_backend import CodebaseMemoryBackend

        backend = CodebaseMemoryBackend(binary_path="codebase-memory-mcp")
        fake_run, records = self._make_capture_mock()

        with patch(
            "repo_agent.code_intelligence.cbm_backend.subprocess.run",
            side_effect=fake_run,
        ):
            backend._run_cli(
                "search_graph",
                {
                    "project": "/tmp/repo",
                    "name_pattern": "foo",
                    "file_pattern": "*.java",
                    "label": "Class",
                    "limit": 50,
                },
            )

        _, payload = records[0]
        # key 保持原样（下划线），不转连字符。
        self.assertIn("name_pattern", payload)
        self.assertIn("file_pattern", payload)
        self.assertNotIn("name-pattern", payload)
        self.assertNotIn("file-pattern", payload)
        self.assertEqual(payload["file_pattern"], "*.java")
        self.assertEqual(payload["limit"], 50)

    def test_none_values_filtered_from_payload(self):
        """None 的参数不应进入 payload（避免 CBM 收到 null）。"""
        from repo_agent.code_intelligence.cbm_backend import CodebaseMemoryBackend

        backend = CodebaseMemoryBackend(binary_path="codebase-memory-mcp")
        fake_run, records = self._make_capture_mock()

        with patch(
            "repo_agent.code_intelligence.cbm_backend.subprocess.run",
            side_effect=fake_run,
        ):
            backend._run_cli(
                "search_graph",
                {"project": "/tmp/repo", "name_pattern": None, "label": "Class"},
            )

        _, payload = records[0]
        self.assertNotIn("name_pattern", payload)
        self.assertEqual(payload, {"project": "/tmp/repo", "label": "Class"})

    def test_paths_with_backslashes_survive(self):
        """Windows 风格的反斜杠路径应原样出现在 JSON 字符串里。"""
        import json as _json

        from repo_agent.code_intelligence.cbm_backend import CodebaseMemoryBackend

        backend = CodebaseMemoryBackend(binary_path="codebase-memory-mcp")
        fake_run, records = self._make_capture_mock()

        with patch(
            "repo_agent.code_intelligence.cbm_backend.subprocess.run",
            side_effect=fake_run,
        ):
            backend._run_cli(
                "index_repository",
                {"repo_path": r"D:\source\NGCRM\crm\jbusiness", "mode": "full"},
            )

        _, payload = records[0]
        # 反斜杠路径应完整保留（JSON 里会被转义为 \\，反序列化后还原）。
        self.assertEqual(payload["repo_path"], r"D:\source\NGCRM\crm\jbusiness")

    def test_error_message_includes_payload(self):
        """CBM 返回错误时，异常信息应携带 payload 便于排查。"""
        from subprocess import CompletedProcess

        from repo_agent.code_intelligence.cbm_backend import CodebaseMemoryBackend

        backend = CodebaseMemoryBackend(binary_path="codebase-memory-mcp")

        def fake_run(cmd, *args, **kwargs):
            return CompletedProcess(
                args=cmd,
                returncode=0,
                stdout='{"isError": true, "content": [{"type":"text","text":"boom"}]}',
                stderr="",
            )

        with patch(
            "repo_agent.code_intelligence.cbm_backend.subprocess.run",
            side_effect=fake_run,
        ):
            with self.assertRaises(RuntimeError) as ctx:
                backend._run_cli("index_repository", {"repo_path": "/tmp/repo"})

        msg = str(ctx.exception)
        self.assertIn("index_repository", msg)
        self.assertIn("boom", msg)
        self.assertIn("repo_path", msg)  # payload 里有 repo_path


class TestProjectNameResolution(unittest.TestCase):
    """测试 CBM 派生项目名的解析与使用。

    CBM 的 index_repository 接受 repo_path（原始路径），但 search_graph /
    get_code_snippet / trace_path 的 project 字段在某些版本（如 0.8.1）只认
    CBM 派生名（``D:\\a\\b`` → ``D-a-b``），不做路径→名解析。派生名必须从
    index 响应里读出，不能本地复刻。

    本测试 mock ``_run_cli``，验证：index 时抓取并缓存派生名；后续查询用缓存
    名而非原始路径；未命中时回退到 index_status 查询。
    """

    def test_index_repo_captures_derived_project_name(self):
        """index_repo 应从 index_repository 响应里抓取派生名并缓存。"""
        from repo_agent.code_intelligence.cbm_backend import CodebaseMemoryBackend

        backend = CodebaseMemoryBackend(binary_path="codebase-memory-mcp")

        def fake_run_cli(tool, args):
            if tool == "index_status":
                return {"error": "not found"}  # 触发实际索引
            if tool == "index_repository":
                # CBM 返回派生名 D-a-b（对应路径 D:\a\b）
                return {"project": "D-a-b", "nodes": 5, "edges": 6, "status": "indexed"}
            return {}

        with patch.object(backend, "_run_cli", side_effect=fake_run_cli):
            backend.index_repo(Path(r"D:\a\b"), mode="full")

        self.assertEqual(
            backend._project_name_cache[r"D:\a\b"], "D-a-b"
        )

    def test_project_returns_cached_name(self):
        """_project() 优先返回缓存，不再调用 CBM。"""
        from repo_agent.code_intelligence.cbm_backend import CodebaseMemoryBackend

        backend = CodebaseMemoryBackend(binary_path="codebase-memory-mcp")
        backend._project_name_cache["/tmp/repo"] = "tmp-repo"

        with patch.object(backend, "_run_cli") as mock_cli:
            name = backend._project(Path("/tmp/repo"))
            mock_cli.assert_not_called()  # 命中缓存，不该调 CBM

        self.assertEqual(name, "tmp-repo")

    def test_project_falls_back_to_index_status_lookup(self):
        """缓存未命中时，_project() 调 index_status 获取派生名。"""
        from repo_agent.code_intelligence.cbm_backend import CodebaseMemoryBackend

        backend = CodebaseMemoryBackend(binary_path="codebase-memory-mcp")

        def fake_run_cli(tool, args):
            if tool == "index_status":
                return {"project": "derived-name", "nodes": 3}
            return {}

        with patch.object(backend, "_run_cli", side_effect=fake_run_cli):
            name = backend._project(Path("/tmp/repo"))

        self.assertEqual(name, "derived-name")
        self.assertEqual(backend._project_name_cache["/tmp/repo"], "derived-name")

    def test_query_methods_use_derived_name_not_raw_path(self):
        """get_overall_structure 等查询应用派生名作为 project，而非原始路径。"""
        from repo_agent.code_intelligence.cbm_backend import CodebaseMemoryBackend

        backend = CodebaseMemoryBackend(binary_path="codebase-memory-mcp")
        # 模拟已索引：缓存里已有派生名
        backend._project_name_cache[r"D:\source\repo"] = "D-source-repo"
        backend._indexed_repo = r"D:\source\repo"

        captured_projects = []

        def fake_run_cli(tool, args):
            captured_projects.append((tool, args.get("project")))
            if tool == "search_graph":
                return {"results": []}
            return {"results": []}

        with patch.object(backend, "_run_cli", side_effect=fake_run_cli):
            backend.get_overall_structure(Path(r"D:\source\repo"), {}, [])

        # 所有 search_graph 调用都应用派生名，而不是原始路径
        for tool, project in captured_projects:
            if tool == "search_graph":
                self.assertEqual(
                    project,
                    "D-source-repo",
                    f"search_graph 应使用派生名，实际用了 {project!r}",
                )

    def test_project_fallback_to_raw_path_on_failure(self):
        """index_status 失败时，_project() 退回原始路径（CBM 0.9.0 能解析）。"""
        from repo_agent.code_intelligence.cbm_backend import CodebaseMemoryBackend

        backend = CodebaseMemoryBackend(binary_path="codebase-memory-mcp")

        def fake_run_cli(tool, args):
            raise RuntimeError("boom")

        with patch.object(backend, "_run_cli", side_effect=fake_run_cli):
            name = backend._project(Path("/tmp/repo"))

        self.assertEqual(name, "/tmp/repo")  # 退回原始路径


class TestFilePathNormalization(unittest.TestCase):
    """测试 CBM 返回路径的归一化（修复 Windows 上引用解析 "not in target repo"）。

    CBM 在不同平台/工具返回的 file_path 格式不一致：search_graph 在 Linux
    返回相对路径，在 Windows 返回绝对正斜杠路径；get_code_snippet 始终返回
    绝对路径。下游 doc_meta_info 的契约是「相对路径 + 正斜杠」。本测试验证
    _normalize_file_path 及其在 get_overall_structure / _lookup_node_info 的应用，
    用 Windows 风格输入（反斜杠 repo 路径 + 正斜杠绝对文件路径）模拟现场。
    """

    def test_normalize_unit_forward_slash_absolute(self):
        """正斜杠绝对路径 → 相对路径（Windows CBM 的典型输出）。"""
        from repo_agent.code_intelligence.cbm_backend import _normalize_file_path

        repo = Path(r"D:\source\NGCRM\crm\jbusiness")
        # CBM 返回正斜杠绝对路径
        result = _normalize_file_path(
            repo, r"D:/source/NGCRM/crm/jbusiness/opcode/src/main/java/X.java"
        )
        self.assertEqual(result, "opcode/src/main/java/X.java")

    def test_normalize_unit_backslash_absolute(self):
        """反斜杠绝对路径 → 相对正斜杠路径。"""
        from repo_agent.code_intelligence.cbm_backend import _normalize_file_path

        repo = Path(r"D:\source\repo")
        result = _normalize_file_path(repo, r"D:\source\repo\src\G.java")
        self.assertEqual(result, "src/G.java")

    def test_normalize_unit_case_insensitive_drive_letter(self):
        """盘符大小写不一致（D: vs d:）也应能去掉前缀。"""
        from repo_agent.code_intelligence.cbm_backend import _normalize_file_path

        repo = Path(r"D:\source\repo")
        result = _normalize_file_path(repo, r"d:/source/repo/X.java")
        self.assertEqual(result, "X.java")

    def test_normalize_unit_already_relative_is_noop(self):
        """已经是相对路径的输入应原样返回（保证 Linux 行为不变）。"""
        from repo_agent.code_intelligence.cbm_backend import _normalize_file_path

        repo = Path("/tmp/repo")
        self.assertEqual(_normalize_file_path(repo, "src/G.java"), "src/G.java")
        self.assertEqual(_normalize_file_path(repo, "G.java"), "G.java")

    def test_normalize_unit_empty(self):
        """空输入原样返回。"""
        from repo_agent.code_intelligence.cbm_backend import _normalize_file_path

        self.assertEqual(_normalize_file_path(Path("/tmp/repo"), ""), "")

    def test_get_overall_structure_normalizes_windows_paths(self):
        """get_overall_structure 的键应是相对路径，即使 CBM 返回绝对路径。"""
        from repo_agent.code_intelligence.cbm_backend import CodebaseMemoryBackend

        backend = CodebaseMemoryBackend(binary_path="codebase-memory-mcp")
        backend._indexed_repo = r"D:\source\repo"
        backend._project_name_cache[r"D:\source\repo"] = "D-source-repo"

        # 模拟 Windows：CBM search_graph 返回绝对正斜杠路径。
        def fake_run_cli(tool, args):
            if tool == "search_graph":
                return {
                    "results": [
                        {
                            "name": "greet",
                            "label": "Method",
                            "file_path": "D:/source/repo/src/G.java",
                            "qualified_name": "D-source-repo.G.greet",
                        }
                    ]
                }
            if tool == "get_code_snippet":
                return {
                    "source": "public void greet(){}",
                    "start_line": 1,
                    "end_line": 1,
                    "signature": "()",
                    "file_path": "D:/source/repo/src/G.java",
                }
            return {}

        with patch.object(backend, "_run_cli", side_effect=fake_run_cli):
            with patch(
                "repo_agent.code_intelligence.cbm_backend._configured_file_extensions",
                return_value=["java"],
            ):
                structure = backend.get_overall_structure(
                    Path(r"D:\source\repo"), {}, []
                )

        # 键必须是相对路径，不能含盘符/仓库根。
        self.assertEqual(list(structure.keys()), ["src/G.java"])

    def test_lookup_node_info_normalizes_absolute_snippet_path(self):
        """_lookup_node_info 应把 get_code_snippet 的绝对路径归一化（这是 bug 所在）。"""
        from repo_agent.code_intelligence.cbm_backend import CodebaseMemoryBackend

        backend = CodebaseMemoryBackend(binary_path="codebase-memory-mcp")
        backend._project_name_cache[r"D:\source\repo"] = "D-source-repo"

        def fake_run_cli(tool, args):
            # get_code_snippet 返回 Windows 风格绝对正斜杠路径。
            if tool == "get_code_snippet":
                return {
                    "file_path": "D:/source/repo/opcode/X.java",
                    "start_line": 5,
                    "end_line": 10,
                }
            return {}

        with patch.object(backend, "_run_cli", side_effect=fake_run_cli):
            file_path, start, end = backend._lookup_node_info(
                Path(r"D:\source\repo"), "X.foo"
            )

        # 必须是相对路径；修复前会返回绝对路径 D:/source/repo/opcode/X.java。
        self.assertEqual(file_path, "opcode/X.java")
        self.assertEqual(start, 5)
        self.assertEqual(end, 10)


if __name__ == "__main__":
    unittest.main()
