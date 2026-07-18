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


class TestCliFlagHyphenation(unittest.TestCase):
    """测试 ``_run_cli`` 把 arg key 的下划线转成连字符 flag。

    CBM CLI flags 规范形式是连字符（``--repo-path``、``--file-pattern`` 等），
    Windows 构建会拒绝下划线形式（``--repo_path``）。此测试不依赖 CBM 二进制，
    通过 mock ``subprocess.run`` 捕获实际命令并断言 flag 形式，覆盖 Linux
    上"两种形式都接受"导致测不出的盲区。
    """

    def _make_run_cli_mock(self):
        """返回 (mock, captured_cmds)。

        mock 模拟一次成功的 CBM 调用：空 structuredContent。
        captured_cmds 收集每次调用收到的 argv 列表。
        """
        from subprocess import CompletedProcess

        captured: list[list[str]] = []

        def fake_run(cmd, *args, **kwargs):
            captured.append(list(cmd))
            return CompletedProcess(
                args=cmd,
                returncode=0,
                stdout='{"structuredContent": {}, "isError": false}',
                stderr="",
            )

        return fake_run, captured

    def test_index_repository_uses_hyphenated_repo_path(self):
        """index_repository 的 repo_path → --repo-path。"""
        from pathlib import Path

        from repo_agent.code_intelligence.cbm_backend import CodebaseMemoryBackend

        backend = CodebaseMemoryBackend(binary_path="codebase-memory-mcp")
        backend._indexed_repo = None  # 强制走建索引分支，不命中缓存

        fake_run, captured = self._make_run_cli_mock()

        def fake_status(*a, **k):
            # 让 index_status 检查返回"无索引"，从而进入 index_repository。
            from subprocess import CompletedProcess

            return CompletedProcess(
                args=a,
                returncode=0,
                stdout='{"structuredContent": {"error": "no index"}, "isError": false}',
                stderr="",
            )

        call_count = {"n": 0}

        def run_dispatch(cmd, *args, **kwargs):
            call_count["n"] += 1
            # 第一次调用是 index_status，后续是 index_repository。
            if call_count["n"] == 1:
                return fake_status(cmd, *args, **kwargs)
            return fake_run(cmd, *args, **kwargs)

        with patch(
            "repo_agent.code_intelligence.cbm_backend.subprocess.run",
            side_effect=run_dispatch,
        ):
            backend.index_repo(Path("/tmp/sample-repo"), mode="full")

        # 至少有一次 index_repository 调用
        index_calls = [c for c in captured if "index_repository" in c]
        self.assertGreater(len(index_calls), 0, "should call index_repository")
        cmd = index_calls[-1]
        self.assertIn("--repo-path", cmd)
        self.assertIn("/tmp/sample-repo", cmd)
        self.assertIn("--mode", cmd)
        # 关键：下划线形式不应出现。
        self.assertNotIn("--repo_path", cmd)

    def test_search_graph_uses_hyphenated_flags(self):
        """search_graph 的 name_pattern/file_pattern → 连字符。"""
        from pathlib import Path

        from repo_agent.code_intelligence.cbm_backend import CodebaseMemoryBackend

        backend = CodebaseMemoryBackend(binary_path="codebase-memory-mcp")
        fake_run, captured = self._make_run_cli_mock()

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

        self.assertGreater(len(captured), 0)
        cmd = captured[-1]
        self.assertIn("--name-pattern", cmd)
        self.assertIn("--file-pattern", cmd)
        self.assertNotIn("--name_pattern", cmd)
        self.assertNotIn("--file_pattern", cmd)

    def test_trace_path_uses_hyphenated_function_name(self):
        """trace_path 的 function_name → --function-name。"""
        from repo_agent.code_intelligence.cbm_backend import CodebaseMemoryBackend

        backend = CodebaseMemoryBackend(binary_path="codebase-memory-mcp")
        fake_run, captured = self._make_run_cli_mock()

        with patch(
            "repo_agent.code_intelligence.cbm_backend.subprocess.run",
            side_effect=fake_run,
        ):
            backend._run_cli(
                "trace_path",
                {
                    "function_name": "mod.foo",
                    "project": "/tmp/repo",
                    "direction": "inbound",
                },
            )

        cmd = captured[-1]
        self.assertIn("--function-name", cmd)
        self.assertNotIn("--function_name", cmd)

    def test_single_word_keys_unchanged(self):
        """单 word key（project/label/mode）不受影响。"""
        from repo_agent.code_intelligence.cbm_backend import CodebaseMemoryBackend

        backend = CodebaseMemoryBackend(binary_path="codebase-memory-mcp")
        fake_run, captured = self._make_run_cli_mock()

        with patch(
            "repo_agent.code_intelligence.cbm_backend.subprocess.run",
            side_effect=fake_run,
        ):
            backend._run_cli("index_status", {"project": "/tmp/repo"})

        cmd = captured[-1]
        self.assertIn("--project", cmd)


if __name__ == "__main__":
    unittest.main()
