"""代码智能后端的抽象基类。

定义 AST 解析和引用关系分析的统一接口，使 RepoAgent 可以在
``builtin``（ast + jedi）和 ``codebase_memory``（codebase-memory-mcp）
后端之间切换。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Tuple


class CodeIntelligenceBackend(ABC):
    """代码智能后端的统一接口。

    所有方法返回的数据结构必须与 ``FileHandler`` 原有的输出格式保持一致，
    以确保 ``DocItem``、``MetaInfo``、``ChatEngine`` 等下游消费者无需修改。
    """

    @abstractmethod
    def index_repo(self, repo_path: Path, mode: str = "full") -> None:
        """对目标仓库建立索引（如有需要）。

        Args:
            repo_path: 目标仓库的绝对路径。
            mode: 索引模式（后端自定义，如 ``"full"`` / ``"moderate"`` / ``"fast"``）。
        """

    @abstractmethod
    def get_file_structure(
        self, repo_path: Path, file_path: str
    ) -> List[dict]:
        """获取单个文件中所有函数/类的 ``code_info`` 字典列表。

        Args:
            repo_path: 目标仓库的绝对路径。
            file_path: 相对于仓库根目录的文件路径。

        Returns:
            ``code_info`` 字典列表，每个字典包含以下 key::

                type, name, md_content, code_start_line, code_end_line,
                params, have_return, code_content, name_column
        """

    @abstractmethod
    def get_overall_structure(
        self,
        repo_path: Path,
        file_path_reflections: Dict[str, str],
        jump_files: List[str],
    ) -> Dict[str, List[dict]]:
        """获取整个仓库的文件结构。

        Args:
            repo_path: 目标仓库的绝对路径。
            file_path_reflections: 未暂存修改文件的 {原始路径: fake_file路径} 映射。
            jump_files: 需要跳过（不解析）的文件列表。

        Returns:
            ``{file_path: [code_info, ...]}`` 字典。
        """

    @abstractmethod
    def find_references(
        self,
        repo_path: Path,
        file_path: str,
        obj_name: str,
        start_line: int,
        name_column: int,
        in_file_only: bool = False,
    ) -> List[Tuple[str, int, int]]:
        """查找对象的所有引用者。

        Args:
            repo_path: 目标仓库的绝对路径。
            file_path: 对象所在文件（相对路径）。
            obj_name: 对象名称。
            start_line: 对象起始行号。
            name_column: 对象名称在起始行的列偏移。
            in_file_only: 是否只搜索同一文件内的引用。

        Returns:
            ``[(relative_file_path, line, column), ...]`` 列表，
            不包含对象自身的定义位置。
        """
