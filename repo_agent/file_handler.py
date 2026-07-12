# FileHandler 类，实现对文件的读写操作，这里的文件包括markdown文件和源代码文件
# repo_agent/file_handler.py
import json
import os
from pathlib import Path

import git

from repo_agent.code_intelligence import get_backend
from repo_agent.settings import SettingsManager


class FileHandler:
    """
    历变更后的文件的循环中，为每个变更后文件（也就是当前文件）创建一个实例
    """

    def __init__(self, repo_path, file_path):
        self.file_path = file_path  # 这里的file_path是相对于仓库根目录的路径
        self.repo_path = repo_path

        setting = SettingsManager.get_setting()

        self.project_hierarchy = (
            setting.project.target_repo / setting.project.hierarchy_name
        )
        self.backend = get_backend()

    def read_file(self):
        """
        Read the file content

        Returns:
            str: The content of the current changed file
        """
        abs_file_path = os.path.join(self.repo_path, self.file_path)

        with open(abs_file_path, "r", encoding="utf-8") as file:
            content = file.read()
        return content

    def write_file(self, file_path, content):
        """
        Write content to a file.

        Args:
            file_path (str): The relative path of the file.
            content (str): The content to be written to the file.
        """
        # 确保file_path是相对路径
        if file_path.startswith("/"):
            # 移除开头的 '/'
            file_path = file_path[1:]

        abs_file_path = os.path.join(self.repo_path, file_path)
        os.makedirs(os.path.dirname(abs_file_path), exist_ok=True)
        with open(abs_file_path, "w", encoding="utf-8") as file:
            file.write(content)

    def get_modified_file_versions(self):
        """
        Get the current and previous versions of the modified file.

        Returns:
            tuple: A tuple containing the current version and the previous version of the file.
        """
        repo = git.Repo(self.repo_path)

        # Read the file in the current working directory (current version)
        current_version_path = os.path.join(self.repo_path, self.file_path)
        with open(current_version_path, "r", encoding="utf-8") as file:
            current_version = file.read()

        # Get the file version from the last commit (previous version)
        commits = list(repo.iter_commits(paths=self.file_path, max_count=1))
        previous_version = None
        if commits:
            commit = commits[0]
            try:
                previous_version = (
                    (commit.tree / self.file_path).data_stream.read().decode("utf-8")
                )
            except KeyError:
                previous_version = None  # The file may be newly added and not present in previous commits

        return current_version, previous_version

    def generate_file_structure(self, file_path):
        """
        Generates the file structure for the given file path.

        Delegates to the codebase-memory-mcp backend.

        Args:
            file_path (str): The relative path of the file.

        Returns:
            list: A list of code_info dictionaries for each function/class in the file.
        """
        return self.backend.get_file_structure(Path(self.repo_path), file_path)

    def generate_overall_structure(self, file_path_reflections, jump_files) -> dict:
        """获取目标仓库的文件情况，通过后端获取所有对象等情况。
        对于jump_files: 不会parse，当做不存在
        """
        return self.backend.get_overall_structure(
            Path(self.repo_path), file_path_reflections, jump_files
        )

    def convert_to_markdown_file(self, file_path=None):
        """
        Converts the content of a file to markdown format.

        Args:
            file_path (str, optional): The relative path of the file to be converted. If not provided, the default file path, which is None, will be used.

        Returns:
            str: The content of the file in markdown format.

        Raises:
            ValueError: If no file object is found for the specified file path in project_hierarchy.json.
        """
        with open(self.project_hierarchy, "r", encoding="utf-8") as f:
            json_data = json.load(f)

        if file_path is None:
            file_path = self.file_path

        # Find the file object in json_data that matches file_path

        file_dict = json_data.get(file_path)

        if file_dict is None:
            raise ValueError(
                f"No file object found for {self.file_path} in project_hierarchy.json"
            )

        markdown = ""
        parent_dict = {}
        objects = sorted(file_dict.values(), key=lambda obj: obj["code_start_line"])
        for obj in objects:
            if obj["parent"] is not None:
                parent_dict[obj["name"]] = obj["parent"]
        current_parent = None
        for obj in objects:
            level = 1
            parent = obj["parent"]
            while parent is not None:
                level += 1
                parent = parent_dict.get(parent)
            if level == 1 and current_parent is not None:
                markdown += "***\n"
            current_parent = obj["name"]
            params_str = ""
            if obj["type"] in ["FunctionDef", "AsyncFunctionDef"]:
                params_str = "()"
                if obj["params"]:
                    params_str = f"({', '.join(obj['params'])})"
            markdown += f"{'#' * level} {obj['type']} {obj['name']}{params_str}:\n"
            markdown += (
                f"{obj['md_content'][-1] if len(obj['md_content']) >0 else ''}\n"
            )
        markdown += "***\n"

        return markdown
