import itertools
import os

import git
from colorama import Fore, Style

from repo_agent.log import logger
from repo_agent.settings import SettingsManager

# fake-file 后缀的基础名，实际使用时会拼接当前处理的扩展名，
# 例如处理 .py 文件时为 "_latest_version.py"，处理 .java 时为 "_latest_version.java"
latest_verison_base = "_latest_version"


def _get_source_extensions():
    """从 settings 获取当前配置的源文件扩展名列表。"""
    try:
        return SettingsManager.get_setting().project.file_extensions
    except Exception:
        return ["py"]


def _is_source_file(file_name: str) -> bool:
    """检查文件是否匹配已配置的源代码扩展名。"""
    for ext in _get_source_extensions():
        if file_name.endswith("." + ext):
            return True
    return False


def _is_latest_version_file(file_name: str) -> bool:
    """检查文件是否是 fake-file（任意扩展名的 _latest_version 文件）。"""
    return latest_verison_base + "." in file_name and any(
        file_name.endswith(latest_verison_base + "." + ext)
        for ext in _get_source_extensions()
    )


# 兼容性保留：CBM 后端的 cbm_backend.py 引用了此变量用于过滤 fake-file。
# 由于现在 fake-file 后缀是动态的，cbm_backend 改用 _is_latest_version_file 逻辑。
latest_verison_substring = latest_verison_base + ".py"


def make_fake_files():
    """根据git status检测暂存区信息。如果有文件：
    1. 新增文件，没有add。无视
    2. 修改文件内容，没有add，原始文件重命名为fake_file，新建原本的文件名内容为git status中的文件内容
    3. 删除文件，没有add，原始文件重命名为fake_file，新建原本的文件名内容为git status中的文件内容
    注意: 目标仓库的文件不能以latest_verison_substring结尾
    """
    delete_fake_files()
    setting = SettingsManager.get_setting()

    repo = git.Repo(setting.project.target_repo)
    unstaged_changes = repo.index.diff(None)  # 在git status里，但是有修改没提交
    untracked_files = repo.untracked_files  # 在文件系统里，但没在git里的文件

    jump_files = []  # 这里面的内容不parse、不生成文档，并且引用关系也不计算他们
    for file_name in untracked_files:
        if _is_source_file(file_name):
            print(
                f"{Fore.LIGHTMAGENTA_EX}[SKIP untracked files]: {Style.RESET_ALL}{file_name}"
            )
            jump_files.append(file_name)
    for diff_file in unstaged_changes.iter_change_type(
        "A"
    ):  # 新增的、没有add的文件，都不处理
        if _is_latest_version_file(diff_file.a_path):
            logger.error(
                "FAKE_FILE_IN_GIT_STATUS detected! suggest to use `delete_fake_files` and re-generate document"
            )
            exit()
        jump_files.append(diff_file.a_path)

    file_path_reflections = {}
    for diff_file in itertools.chain(
        unstaged_changes.iter_change_type("M"), unstaged_changes.iter_change_type("D")
    ):  # 获取修改过的文件
        if _is_latest_version_file(diff_file.a_path):
            logger.error(
                "FAKE_FILE_IN_GIT_STATUS detected! suggest to use `delete_fake_files` and re-generate document"
            )
            exit()
        now_file_path = diff_file.a_path  # 针对repo_path的相对路径
        if _is_source_file(now_file_path):
            raw_file_content = diff_file.a_blob.data_stream.read().decode("utf-8")
            # 根据原始扩展名动态生成 fake-file 路径
            original_ext = "." + now_file_path.rsplit(".", 1)[-1]
            latest_file_path = (
                now_file_path[: -len(original_ext)]
                + latest_verison_base
                + original_ext
            )
            if os.path.exists(os.path.join(setting.project.target_repo, now_file_path)):
                os.rename(
                    os.path.join(setting.project.target_repo, now_file_path),
                    os.path.join(setting.project.target_repo, latest_file_path),
                )

                print(
                    f"{Fore.LIGHTMAGENTA_EX}[Save Latest Version of Code]: {Style.RESET_ALL}{now_file_path} -> {latest_file_path}"
                )
            else:
                print(
                    f"{Fore.LIGHTMAGENTA_EX}[Create Temp-File for Deleted(But not Staged) Files]: {Style.RESET_ALL}{now_file_path} -> {latest_file_path}"
                )
                with open(
                    os.path.join(setting.project.target_repo, latest_file_path), "w"
                ) as writer:
                    pass
            with open(
                os.path.join(setting.project.target_repo, now_file_path), "w"
            ) as writer:
                writer.write(raw_file_content)
            file_path_reflections[now_file_path] = latest_file_path  # real指向fake
    return file_path_reflections, jump_files


def delete_fake_files():
    """在任务执行完成以后，删除所有的fake_file"""
    setting = SettingsManager.get_setting()

    def gci(filepath):
        # 遍历filepath下所有文件，包括子目录
        files = os.listdir(filepath)
        for fi in files:
            fi_d = os.path.join(filepath, fi)
            if os.path.isdir(fi_d):
                gci(fi_d)
            elif _is_latest_version_file(fi_d):
                # 将 fake-file 名恢复为原始文件名（任意扩展名）
                # 例如 foo_latest_version.py → foo.py
                #     Bar_latest_version.java → Bar.java
                original_ext = "." + fi_d.rsplit(".", 1)[-1]
                origin_name = fi_d.replace(
                    latest_verison_base + original_ext, original_ext
                )
                os.remove(origin_name)
                if os.path.getsize(fi_d) == 0:
                    print(
                        f"{Fore.LIGHTRED_EX}[Deleting Temp File]: {Style.RESET_ALL}{fi_d[len(str(setting.project.target_repo)):]}, {origin_name[len(str(setting.project.target_repo)):]}"
                    )  # type: ignore
                    os.remove(fi_d)
                else:
                    print(
                        f"{Fore.LIGHTRED_EX}[Recovering Latest Version]: {Style.RESET_ALL}{origin_name[len(str(setting.project.target_repo)):]} <- {fi_d[len(str(setting.project.target_repo)):]}"
                    )  # type: ignore
                    os.rename(fi_d, origin_name)

    gci(setting.project.target_repo)
