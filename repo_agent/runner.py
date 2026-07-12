import shutil
import subprocess
import threading
import time
from functools import partial
from pathlib import Path

from colorama import Fore, Style
from tqdm import tqdm

from repo_agent.change_detector import ChangeDetector
from repo_agent.chat_engine import ChatEngine
from repo_agent.doc_meta_info import DocItem, DocItemStatus, MetaInfo, need_to_generate
from repo_agent.log import logger
from repo_agent.multi_task_dispatch import worker
from repo_agent.project_manager import ProjectManager
from repo_agent.settings import SettingsManager
from repo_agent.utils.meta_info_utils import delete_fake_files, make_fake_files


def _source_to_md(file_path: str, file_extensions: list) -> str:
    """将源文件路径的扩展名替换为 ``.md``。

    支持任意已配置的源扩展名（如 ``.py`` / ``.java`` / ``.go``）。
    """
    for ext in file_extensions:
        ext_with_dot = "." + ext
        if file_path.endswith(ext_with_dot):
            return file_path[: -len(ext_with_dot)] + ".md"
    return file_path + ".md"


class Runner:
    def __init__(self):
        self.setting = SettingsManager.get_setting()
        self.absolute_project_hierarchy_path = (
            self.setting.project.target_repo / self.setting.project.hierarchy_name
        )

        self.project_manager = ProjectManager(
            repo_path=self.setting.project.target_repo,
            project_hierarchy=self.setting.project.hierarchy_name,
        )
        self.change_detector = ChangeDetector(
            repo_path=self.setting.project.target_repo
        )
        self.chat_engine = ChatEngine(project_manager=self.project_manager)

        # 触发代码智能后端索引（codebase_memory 后端会建 CBM 索引；
        # builtin 后端为 no-op）
        from repo_agent.code_intelligence import get_backend

        self.backend = get_backend()
        self.backend.index_repo(
            repo_path=self.setting.project.target_repo,
            mode=self.setting.project.cbm_index_mode,
        )

        if not self.absolute_project_hierarchy_path.exists():
            file_path_reflections, jump_files = make_fake_files()
            self.meta_info = MetaInfo.init_meta_info(file_path_reflections, jump_files)
            self.meta_info.checkpoint(
                target_dir_path=self.absolute_project_hierarchy_path
            )
        else:  # 如果存在全局结构信息文件夹.project_hierarchy，就从中加载
            self.meta_info = MetaInfo.from_checkpoint_path(
                self.absolute_project_hierarchy_path
            )

        self.meta_info.checkpoint(  # 更新白名单后也要重新将全局信息写入到.project_doc_record文件夹中
            target_dir_path=self.absolute_project_hierarchy_path
        )
        self.runner_lock = threading.Lock()

    def generate_doc_for_a_single_item(self, doc_item: DocItem):
        """为一个对象生成文档"""
        try:
            if not need_to_generate(doc_item, self.setting.project.ignore_list):
                print(
                    f"Content ignored/Document generated, skipping: {doc_item.get_full_name()}"
                )
            else:
                print(
                    f" -- Generating document  {Fore.LIGHTYELLOW_EX}{doc_item.item_type.name}: {doc_item.get_full_name()}{Style.RESET_ALL}"
                )
                response_message = self.chat_engine.generate_doc(
                    doc_item=doc_item,
                )
                doc_item.md_content.append(response_message)  # type: ignore
                doc_item.item_status = DocItemStatus.doc_up_to_date
                self.meta_info.checkpoint(
                    target_dir_path=self.absolute_project_hierarchy_path
                )
        except Exception:
            logger.exception(
                f"Document generation failed after multiple attempts, skipping: {doc_item.get_full_name()}"
            )
            doc_item.item_status = DocItemStatus.doc_has_not_been_generated

    def first_generate(self):
        """
        生成所有文档，完成后刷新并保存文件系统中的文档信息。
        """
        logger.info("Starting to generate documentation")
        check_task_available_func = partial(
            need_to_generate, ignore_list=self.setting.project.ignore_list
        )
        task_manager = self.meta_info.get_topology(check_task_available_func)
        before_task_len = len(task_manager.task_dict)

        if not self.meta_info.in_generation_process:
            self.meta_info.in_generation_process = True
            logger.info("Init a new task-list")
        else:
            logger.info("Load from an existing task-list")
        self.meta_info.print_task_list(task_manager.task_dict)

        try:
            # 创建并启动线程
            threads = [
                threading.Thread(
                    target=worker,
                    args=(
                        task_manager,
                        process_id,
                        self.generate_doc_for_a_single_item,
                    ),
                )
                for process_id in range(self.setting.project.max_thread_count)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            # 所有任务完成后刷新文档
            self.markdown_refresh()

            # 更新文档版本
            self.meta_info.document_version = (
                self.change_detector.repo.head.commit.hexsha
            )
            self.meta_info.in_generation_process = False
            self.meta_info.checkpoint(
                target_dir_path=self.absolute_project_hierarchy_path
            )
            logger.info(
                f"Successfully generated {before_task_len - len(task_manager.task_dict)} documents."
            )

        except BaseException as e:
            logger.error(
                f"An error occurred: {e}. {before_task_len - len(task_manager.task_dict)} docs are generated at this time"
            )

    def markdown_refresh(self):
        """刷新最新的文档信息到markdown格式文件夹中"""
        with self.runner_lock:
            # 定义 markdown 文件夹路径
            markdown_folder = (
                Path(self.setting.project.target_repo)
                / self.setting.project.markdown_docs_name
            )

            # 删除并重新创建目录
            if markdown_folder.exists():
                logger.debug(f"Deleting existing contents of {markdown_folder}")
                shutil.rmtree(markdown_folder)
            markdown_folder.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Created markdown folder at {markdown_folder}")

        # 遍历文件列表生成 markdown
        file_item_list = self.meta_info.get_all_files()
        logger.debug(f"Found {len(file_item_list)} files to process.")

        for file_item in tqdm(file_item_list):
            # 检查文档内容
            def recursive_check(doc_item) -> bool:
                if doc_item.md_content:
                    return True
                for child in doc_item.children.values():
                    if recursive_check(child):
                        return True
                return False

            if not recursive_check(file_item):
                logger.debug(
                    f"No documentation content for: {file_item.get_full_name()}, skipping."
                )
                continue

            # 生成 markdown 内容
            markdown = ""
            for child in file_item.children.values():
                markdown += self.to_markdown(child, 2)

            if not markdown:
                logger.warning(
                    f"No markdown content generated for: {file_item.get_full_name()}"
                )
                continue

            # 确定并创建文件路径（将源文件扩展名替换为 .md）
            file_name = file_item.get_file_name()
            # 将任意源扩展名替换为 .md（如 Foo.py→Foo.md, Bar.java→Bar.md）
            for ext in self.setting.project.file_extensions:
                ext_with_dot = "." + ext
                if file_name.endswith(ext_with_dot):
                    file_name = file_name[: -len(ext_with_dot)] + ".md"
                    break
            else:
                # 如果没有匹配到已知扩展名，直接追加 .md
                file_name = file_name + ".md"
            file_path = Path(self.setting.project.markdown_docs_name) / file_name
            abs_file_path = self.setting.project.target_repo / file_path
            logger.debug(f"Writing markdown to: {abs_file_path}")

            # 确保目录存在
            abs_file_path.parent.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Ensured directory exists: {abs_file_path.parent}")

            # 使用锁保护文件写入操作
            with self.runner_lock:
                for attempt in range(3):  # 最多重试3次
                    try:
                        with open(abs_file_path, "w", encoding="utf-8") as file:
                            file.write(markdown)
                        logger.debug(f"Successfully wrote to {abs_file_path}")
                        break
                    except IOError as e:
                        logger.error(
                            f"Failed to write {abs_file_path} on attempt {attempt + 1}: {e}"
                        )
                        time.sleep(1)  # 延迟再试

        logger.info(
            f"Markdown documents have been refreshed at {self.setting.project.markdown_docs_name}"
        )

    def to_markdown(self, item, now_level: int) -> str:
        """将文件内容转化为 markdown 格式的文本"""
        markdown_content = (
            "#" * now_level + f" {item.item_type.to_str()} {item.obj_name}"
        )
        if "params" in item.content.keys() and item.content["params"]:
            markdown_content += f"({', '.join(item.content['params'])})"
        markdown_content += "\n"
        if item.md_content:
            markdown_content += f"{item.md_content[-1]}\n"
        else:
            markdown_content += "Doc is waiting to be generated...\n"
        for child in item.children.values():
            markdown_content += self.to_markdown(child, now_level + 1)
            markdown_content += "***\n"
        return markdown_content

    def git_commit(self, commit_message):
        try:
            subprocess.check_call(
                ["git", "commit", "--no-verify", "-m", commit_message],
                shell=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"An error occurred while trying to commit {str(e)}")

    def run(self):
        """
        Runs the document update process.

        This method detects the changed Python files, processes each file, and updates the documents accordingly.

        Returns:
            None
        """

        if self.meta_info.document_version == "":
            # 根据document version自动检测是否仍在最初生成的process里(是否为第一次生成)
            self.first_generate()  # 如果是第一次做文档生成任务，就通过first_generate生成所有文档
            self.meta_info.checkpoint(
                target_dir_path=self.absolute_project_hierarchy_path,
                flash_reference_relation=True,
            )  # 这一步将生成后的meta信息（包含引用关系）写入到.project_doc_record文件夹中
            return

        if (
            not self.meta_info.in_generation_process
        ):  # 如果不是在生成过程中，就开始检测变更
            logger.info("Starting to detect changes.")

            """采用新的办法
            1.新建一个project-hierachy
            2.和老的hierarchy做merge,处理以下情况：
            - 创建一个新文件：需要生成对应的doc
            - 文件、对象被删除：对应的doc也删除(按照目前的实现，文件重命名算是删除再添加)
            - 引用关系变了：对应的obj-doc需要重新生成
            
            merge后的new_meta_info中：
            1.新建的文件没有文档，因此metainfo merge后还是没有文档
            2.被删除的文件和obj，本来就不在新的meta里面，相当于文档被自动删除了
            3.只需要观察被修改的文件，以及引用关系需要被通知的文件去重新生成文档"""
            file_path_reflections, jump_files = make_fake_files()
            new_meta_info = MetaInfo.init_meta_info(file_path_reflections, jump_files)
            new_meta_info.load_doc_from_older_meta(self.meta_info)

            self.meta_info = new_meta_info  # 更新自身的meta_info信息为new的信息
            self.meta_info.in_generation_process = True  # 将in_generation_process设置为True，表示检测到变更后Generating document 的过程中

        # 处理任务队列
        check_task_available_func = partial(
            need_to_generate, ignore_list=self.setting.project.ignore_list
        )

        task_manager = self.meta_info.get_task_manager(
            self.meta_info.target_repo_hierarchical_tree,
            task_available_func=check_task_available_func,
        )

        for item_name, item_type in self.meta_info.deleted_items_from_older_meta:
            print(
                f"{Fore.LIGHTMAGENTA_EX}[Dir/File/Obj Delete Dected]: {Style.RESET_ALL} {item_type} {item_name}"
            )
        self.meta_info.print_task_list(task_manager.task_dict)
        if task_manager.all_success:
            logger.info(
                "No tasks in the queue, all documents are completed and up to date."
            )

        threads = [
            threading.Thread(
                target=worker,
                args=(task_manager, process_id, self.generate_doc_for_a_single_item),
            )
            for process_id in range(self.setting.project.max_thread_count)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.meta_info.in_generation_process = False
        self.meta_info.document_version = self.change_detector.repo.head.commit.hexsha

        self.meta_info.checkpoint(
            target_dir_path=self.absolute_project_hierarchy_path,
            flash_reference_relation=True,
        )
        logger.info(f"Doc has been forwarded to the latest version")

        self.markdown_refresh()
        delete_fake_files()

        logger.info(f"Starting to git-add DocMetaInfo and newly generated Docs")
        time.sleep(1)

        # 将run过程中更新的Markdown文件（未暂存）添加到暂存区
        git_add_result = self.change_detector.add_unstaged_files()

        if len(git_add_result) > 0:
            logger.info(
                f"Added {[file for file in git_add_result]} to the staging area."
            )

        # self.git_commit(f"Update documentation for {file_handler.file_path}") # 提交变更


if __name__ == "__main__":
    runner = Runner()

    runner.run()

    logger.info("文档任务完成。")


if __name__ == "__main__":
    runner = Runner()

    runner.run()

    logger.info("文档任务完成。")
