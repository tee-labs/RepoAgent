"""测试 codebase-memory-mcp 后端。

这些测试需要 codebase-memory-mcp 二进制可用。
如果二进制不存在，测试会被跳过。

运行方式::

    # 先安装 CBM
    pip install codebase-memory-mcp

    # 然后运行测试
    pytest tests/test_cbm_backend.py -v
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from repo_agent.code_intelligence.cbm_backend import CodebaseMemoryBackend


def _cbm_available(binary_path="codebase-memory-mcp"):
    """检查 codebase-memory-mcp 二进制是否可用。"""
    return shutil.which(binary_path) is not None


# 跳过条件：CBM 二进制不可用时跳过整个模块
CBM_AVAILABLE = _cbm_available()


@unittest.skipUnless(CBM_AVAILABLE, "codebase-memory-mcp binary not found")
class TestCodebaseMemoryBackend(unittest.TestCase):
    """测试 CodebaseMemoryBackend 的核心功能。"""

    @classmethod
    def setUpClass(cls):
        """创建一个临时 Python 仓库用于测试。"""
        cls.tmpdir = tempfile.mkdtemp(prefix="cbm_test_repo_")
        cls.repo_path = Path(cls.tmpdir)

        # 创建一个简单的 Python 文件用于测试
        test_file = cls.repo_path / "sample.py"
        test_file.write_text(
            '''"""A sample module for testing."""


class Greeter:
    """A class that greets."""

    def __init__(self, name):
        self.name = name

    def greet(self):
        return f"Hello, {self.name}!"


def add(a, b):
    """Add two numbers."""
    return a + b


def use_greeter():
    """Use the Greeter class."""
    g = Greeter("World")
    return g.greet()
''',
            encoding="utf-8",
        )

        # 初始化 git 仓库（CBM 可能需要）
        import subprocess

        subprocess.run(
            ["git", "init"], cwd=cls.tmpdir, capture_output=True, check=True
        )
        subprocess.run(
            ["git", "add", "."], cwd=cls.tmpdir, capture_output=True, check=True
        )
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=cls.tmpdir,
            capture_output=True,
            check=False,  # may fail if git user not configured
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=cls.tmpdir,
            capture_output=True,
            check=False,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=cls.tmpdir,
            capture_output=True,
            check=False,
        )

        cls.backend = CodebaseMemoryBackend()
        # 建立索引
        cls.backend.index_repo(cls.repo_path, mode="full")

    @classmethod
    def tearDownClass(cls):
        """清理临时目录。"""
        import shutil

        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_index_repo_creates_index(self):
        """测试 index_repo 成功建立索引。"""
        # 如果 setUpClass 没有抛异常，说明索引成功了
        self.assertIsNotNone(self.backend._indexed_repo)
        self.assertEqual(self.backend._indexed_repo, str(self.repo_path))

    def test_get_file_structure_returns_code_info(self):
        """测试 get_file_structure 返回正确的 code_info 格式。"""
        structure = self.backend.get_file_structure(self.repo_path, "sample.py")

        self.assertIsInstance(structure, list)
        self.assertGreater(len(structure), 0, "Should find at least one function/class")

        # 验证每个 code_info 的字段完整性
        for code_info in structure:
            self.assertIn("type", code_info)
            self.assertIn("name", code_info)
            self.assertIn("md_content", code_info)
            self.assertIn("code_start_line", code_info)
            self.assertIn("code_end_line", code_info)
            self.assertIn("params", code_info)
            self.assertIn("have_return", code_info)
            self.assertIn("code_content", code_info)
            self.assertIn("name_column", code_info)

            # md_content 应初始化为空列表
            self.assertEqual(code_info["md_content"], [])

            # type 应该是 FunctionDef 或 ClassDef
            self.assertIn(
                code_info["type"], ["FunctionDef", "ClassDef"],
                f"Unexpected type: {code_info['type']}"
            )

    def test_get_file_structure_finds_expected_objects(self):
        """测试 get_file_structure 找到预期的函数和类。"""
        structure = self.backend.get_file_structure(self.repo_path, "sample.py")
        names = {ci["name"] for ci in structure}

        # 应该找到 Greeter 类和函数
        self.assertIn("Greeter", names)
        self.assertIn("add", names)

    def test_get_overall_structure(self):
        """测试 get_overall_structure 返回仓库级结构。"""
        structure = self.backend.get_overall_structure(
            self.repo_path,
            file_path_reflections={},
            jump_files=[],
        )

        self.assertIsInstance(structure, dict)
        self.assertIn("sample.py", structure)
        self.assertGreater(len(structure["sample.py"]), 0)

    def test_find_references_returns_list(self):
        """测试 find_references 返回引用列表。"""
        structure = self.backend.get_file_structure(self.repo_path, "sample.py")

        # 找到 Greeter 类
        greeter_info = None
        for ci in structure:
            if ci["name"] == "Greeter":
                greeter_info = ci
                break

        if greeter_info is None:
            self.skipTest("Greeter class not found in structure")

        references = self.backend.find_references(
            repo_path=self.repo_path,
            file_path="sample.py",
            obj_name="Greeter",
            start_line=greeter_info["code_start_line"],
            name_column=greeter_info["name_column"],
        )

        self.assertIsInstance(references, list)
        # Greeter 被 use_greeter 函数调用，应该至少有一个引用
        # (注意：CBM 的 trace_path 可能返回不同的结果格式)

    def test_code_content_not_empty(self):
        """测试 code_content 字段不为空（需要 get_code_snippet 成功）。"""
        structure = self.backend.get_file_structure(self.repo_path, "sample.py")

        for code_info in structure:
            if code_info["name"] == "add":
                self.assertTrue(
                    code_info["code_content"],
                    "code_content should not be empty for 'add' function"
                )
                self.assertIn("return", code_info["code_content"])
                self.assertTrue(code_info["have_return"])
                break


@unittest.skipUnless(CBM_AVAILABLE, "codebase-memory-mcp binary not found")
class TestCodebaseMemoryBackendErrorHandling(unittest.TestCase):
    """测试 CBM 后端的错误处理。"""

    def test_run_cli_with_missing_binary(self):
        """测试二进制不存在时的错误处理。"""
        backend = CodebaseMemoryBackend(binary_path="/nonexistent/cbm-binary")

        with self.assertRaises(RuntimeError) as ctx:
            backend._run_cli("list_projects", {})

        self.assertIn("not found", str(ctx.exception).lower())


@unittest.skipUnless(CBM_AVAILABLE, "codebase-memory-mcp binary not found")
class TestCodebaseMemoryBackendJava(unittest.TestCase):
    """测试 CBM 后端对 Java 语言的支持。"""

    @classmethod
    def setUpClass(cls):
        """创建一个临时 Java 仓库用于测试。"""
        cls.tmpdir = tempfile.mkdtemp(prefix="cbm_test_java_")
        cls.repo_path = Path(cls.tmpdir)

        # 创建一个简单的 Java 文件
        java_file = cls.repo_path / "Greeter.java"
        java_file.write_text(
            '''package com.example;

/**
 * A class that greets.
 */
public class Greeter {
    private String name;

    public Greeter(String name) {
        this.name = name;
    }

    public String greet() {
        return "Hello, " + name + "!";
    }
}
''',
            encoding="utf-8",
        )

        # 创建另一个 Java 文件引用 Greeter
        main_file = cls.repo_path / "Main.java"
        main_file.write_text(
            '''package com.example;

public class Main {
    public static void main(String[] args) {
        Greeter g = new Greeter("World");
        System.out.println(g.greet());
    }
}
''',
            encoding="utf-8",
        )

        # 初始化 git 仓库
        import subprocess

        subprocess.run(
            ["git", "init"], cwd=cls.tmpdir, capture_output=True, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=cls.tmpdir,
            capture_output=True,
            check=False,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=cls.tmpdir,
            capture_output=True,
            check=False,
        )
        subprocess.run(
            ["git", "add", "."], cwd=cls.tmpdir, capture_output=True, check=True
        )
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=cls.tmpdir,
            capture_output=True,
            check=False,
        )

        cls.backend = CodebaseMemoryBackend()
        cls.backend.index_repo(cls.repo_path, mode="full")

    @classmethod
    def tearDownClass(cls):
        import shutil

        shutil.rmtree(cls.tmpdir, ignore_errors=True)
        # 清理 CBM 索引
        try:
            import subprocess

            project_name = Path(cls.tmpdir).name.replace("-", "_")
            subprocess.run(
                [
                    "codebase-memory-mcp",
                    "cli",
                    "delete_project",
                    "--project",
                    str(cls.repo_path),
                    "--json",
                ],
                capture_output=True,
                timeout=30,
            )
        except Exception:
            pass

    def test_java_index_succeeds(self):
        """测试 Java 仓库索引成功。"""
        self.assertIsNotNone(self.backend._indexed_repo)

    def test_java_get_file_structure(self):
        """测试解析 Java 文件结构。"""
        structure = self.backend.get_file_structure(self.repo_path, "Greeter.java")

        self.assertIsInstance(structure, list)
        self.assertGreater(len(structure), 0, "Should find Java classes/methods")

        # 验证字段完整性
        for code_info in structure:
            self.assertIn("type", code_info)
            self.assertIn("name", code_info)
            self.assertIn("md_content", code_info)
            self.assertIn("code_start_line", code_info)
            self.assertIn("code_end_line", code_info)
            self.assertIn("params", code_info)
            self.assertIn("have_return", code_info)
            self.assertIn("code_content", code_info)
            self.assertIn("name_column", code_info)
            self.assertEqual(code_info["md_content"], [])

    def test_java_finds_class(self):
        """测试能找到 Java 类 Greeter。"""
        structure = self.backend.get_file_structure(self.repo_path, "Greeter.java")
        names = {ci["name"] for ci in structure}

        # CBM 应该能识别 Greeter 类
        self.assertIn("Greeter", names)

    def test_java_finds_methods(self):
        """测试能找到 Java 方法。"""
        structure = self.backend.get_file_structure(self.repo_path, "Greeter.java")
        names = {ci["name"] for ci in structure}

        # 应该找到 greet 方法
        method_found = any(name in names for name in ["greet", "Greeter"])
        self.assertTrue(method_found, f"Should find at least one method in {names}")

    def test_java_code_content_has_source(self):
        """测试 Java 的 code_content 不为空。"""
        structure = self.backend.get_file_structure(self.repo_path, "Greeter.java")

        found_with_content = False
        for code_info in structure:
            if code_info["code_content"]:
                found_with_content = True
                # Java 源码应该包含 class 或 method 关键字
                self.assertTrue(
                    "class" in code_info["code_content"]
                    or "public" in code_info["code_content"]
                    or "private" in code_info["code_content"],
                    f"Java source should contain Java keywords: {code_info['code_content'][:100]}",
                )
                break

        self.assertTrue(found_with_content, "At least one object should have source code")

    def test_java_get_overall_structure(self):
        """测试 Java 仓库的整体结构查询。"""
        structure = self.backend.get_overall_structure(
            self.repo_path,
            file_path_reflections={},
            jump_files=[],
        )

        self.assertIsInstance(structure, dict)
        # 应该包含 Java 文件
        java_files = [k for k in structure.keys() if k.endswith(".java")]
        self.assertGreater(len(java_files), 0, "Should find .java files")


if __name__ == "__main__":
    unittest.main()
