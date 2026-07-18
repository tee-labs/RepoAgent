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


class TestCliArgsFile(unittest.TestCase):
    """测试 ``_run_cli`` 通过 ``--args-file`` 传递参数。

    CBM 经 Python shim 转发到 Go 二进制，在 Windows 上逐个 ``--flag value``
    会经历多次命令行 tokenize（RepoAgent → shim 的 sys.argv → Go），含反斜杠
    的路径可能丢失，导致 CBM 报 ``repo_path is required``。改用单个
    ``--args-file <json>`` token 规避该问题。CBM 的 JSON 参数 key 用下划线
    （``repo_path``），与 flag 形式（``--repo-path``）相反。

    本测试不依赖 CBM 二进制，通过 mock ``subprocess.run`` 捕获命令并在调用
    期间读取临时文件内容，验证：命令形式、payload 内容、临时文件清理。
    """

    def _make_capture_mock(self):
        """返回 (fake_run, records)。

        records 收集每次调用收到的 (cmd, payload) —— payload 是从命令里的
        ``--args-file`` 指向的临时文件中实时读出的（必须在 finally 删除前读取）。
        """
        import json as _json
        from subprocess import CompletedProcess

        records: list[tuple[list[str], dict]] = []

        def fake_run(cmd, *args, **kwargs):
            # 从 cmd 里找到 --args-file 的值并读出 payload。
            payload = {}
            try:
                idx = cmd.index("--args-file")
                with open(cmd[idx + 1]) as f:
                    payload = _json.load(f)
            except (ValueError, IndexError, OSError):
                pass
            records.append((list(cmd), payload))
            return CompletedProcess(
                args=cmd,
                returncode=0,
                stdout='{"structuredContent": {}, "isError": false}',
                stderr="",
            )

        return fake_run, records

    def test_command_uses_args_file_not_inline_flags(self):
        """命令应是 ``... <tool> --args-file <path> --json``，没有逐个 ``--repo-path`` 等。"""
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
        cmd, _ = records[0]
        # 命令骨架：binary cli <tool> --args-file <path> --json
        self.assertEqual(cmd[0:2], ["codebase-memory-mcp", "cli"])
        self.assertIn("index_repository", cmd)
        self.assertIn("--args-file", cmd)
        self.assertIn("--json", cmd)
        # 关键：不应再出现逐个的内联 flag（旧的 --repo-path / --repo_path）。
        self.assertNotIn("--repo-path", cmd)
        self.assertNotIn("--repo_path", cmd)
        self.assertNotIn("--mode", cmd)

    def test_payload_keeps_underscore_keys(self):
        """临时文件里的 JSON key 保持下划线（CBM JSON 形式要求）。"""
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

    def test_temp_file_cleaned_up_after_call(self):
        """调用结束后 --args-file 指向的临时文件应被删除。"""
        from repo_agent.code_intelligence.cbm_backend import CodebaseMemoryBackend

        backend = CodebaseMemoryBackend(binary_path="codebase-memory-mcp")
        fake_run, records = self._make_capture_mock()

        with patch(
            "repo_agent.code_intelligence.cbm_backend.subprocess.run",
            side_effect=fake_run,
        ):
            backend._run_cli("index_status", {"project": "/tmp/repo"})

        cmd, _ = records[0]
        args_path = cmd[cmd.index("--args-file") + 1]
        import os

        self.assertFalse(
            os.path.exists(args_path), f"temp args file should be deleted: {args_path}"
        )

    def test_temp_file_cleaned_up_even_on_error(self):
        """即使 CBM 返回错误，临时文件也应被清理（finally 兜底）。"""
        import os
        from subprocess import CompletedProcess

        from repo_agent.code_intelligence.cbm_backend import CodebaseMemoryBackend

        backend = CodebaseMemoryBackend(binary_path="codebase-memory-mcp")

        captured_path = []

        def fake_run(cmd, *args, **kwargs):
            captured_path.append(cmd[cmd.index("--args-file") + 1])
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

        self.assertEqual(len(captured_path), 1)
        self.assertFalse(
            os.path.exists(captured_path[0]),
            f"temp args file should be deleted even on error: {captured_path[0]}",
        )
        # 错误信息应携带命令和 payload，便于 Windows 等环境排查 CBM 入参。
        msg = str(ctx.exception)
        self.assertIn("index_repository", msg)
        self.assertIn("boom", msg)
        self.assertIn("repo_path", msg)  # payload 里有 repo_path
        self.assertIn("--args-file", msg)  # 命令里有 --args-file


if __name__ == "__main__":
    unittest.main()
