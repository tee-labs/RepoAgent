"""测试 MetaInfo.get_task_manager 的拓扑排序与循环引用处理。

这是性能敏感且语义关键的部分：原始实现是 O(N³)，在大仓库上会卡死；
优化版用 set 替代 list 成员判断，降到 ~O(N·avg_degree)。本测试用合成树
验证拓扑顺序（被引用者先于引用者）和循环引用兜底逻辑不变，作为回归保护。
"""

import unittest

from repo_agent.doc_meta_info import (
    DocItem,
    DocItemType,
    MetaInfo,
    need_to_generate,
)


def _func(name: str) -> DocItem:
    """构造一个文件级 function DocItem（能通过 need_to_generate）。"""
    return DocItem(item_type=DocItemType._function, obj_name=name)


def _class(name: str) -> DocItem:
    return DocItem(item_type=DocItemType._class, obj_name=name)


def _build_meta_info_with_funcs(funcs: dict) -> MetaInfo:
    """用给定的 {name: DocItem} 构造一个最小可用的 MetaInfo。

    funcs 里的 DocItem 应已设置好 reference_who / special_reference_type /
    children。本函数把它们挂到一个 _file 节点下，再挂到 _repo 根上，
    并设置 father / depth，使 get_travel_list 和 need_to_generate 正常工作。
    """
    root = DocItem(item_type=DocItemType._repo, obj_name="full_repo")
    file_node = DocItem(item_type=DocItemType._file, obj_name="sample.py")
    root.children["sample.py"] = file_node
    file_node.father = root

    for name, item in funcs.items():
        file_node.children[name] = item
        item.father = file_node

    # 设置 depth（get_task_manager 会按 depth 排序）
    root.check_depth()

    meta = MetaInfo(target_repo_hierarchical_tree=root)
    return meta


class TestGetTaskManager(unittest.TestCase):
    """验证拓扑排序结果与依赖关系。"""

    def test_referenced_item_scheduled_before_referencer(self):
        """如果 A 引用 B，B 必须先于 A 被排进任务队列（依赖正确）。"""
        a = _func("a")
        b = _func("b")
        # a 引用 b：a.reference_who = [b]，a 依赖 b 先完成
        a.reference_who = [b]
        a.special_reference_type = [False]

        meta = _build_meta_info_with_funcs({"a": a, "b": b})

        tm = meta.get_task_manager(
            meta.target_repo_hierarchical_tree,
            task_available_func=lambda item: need_to_generate(item, []),
        )

        # 任务按添加顺序排列：b 应该比 a 早（b 的 task_id 更小）。
        self.assertLess(b.multithread_task_id, a.multithread_task_id)
        # a 的任务依赖 b 的任务。
        a_task = tm.task_dict[a.multithread_task_id]
        a_dep_ids = {t.task_id for t in a_task.dependencies}
        self.assertIn(b.multithread_task_id, a_dep_ids)

    def test_chain_dependency_order(self):
        """链式依赖 c→b→a（c 引用 b，b 引用 a），顺序应为 a, b, c。"""
        a = _func("a")
        b = _func("b")
        c = _func("c")
        b.reference_who = [a]
        b.special_reference_type = [False]
        c.reference_who = [b]
        c.special_reference_type = [False]

        meta = _build_meta_info_with_funcs({"a": a, "b": b, "c": c})
        tm = meta.get_task_manager(
            meta.target_repo_hierarchical_tree,
            task_available_func=lambda item: need_to_generate(item, []),
        )

        # a 最先，b 其次，c 最后。
        self.assertLess(a.multithread_task_id, b.multithread_task_id)
        self.assertLess(b.multithread_task_id, c.multithread_task_id)

    def test_circular_reference_does_not_hang(self):
        """循环引用 a↔b 不应死循环，应能正常产出两个任务。"""
        a = _func("a")
        b = _func("b")
        a.reference_who = [b]
        a.special_reference_type = [False]
        b.reference_who = [a]
        b.special_reference_type = [False]

        meta = _build_meta_info_with_funcs({"a": a, "b": b})
        tm = meta.get_task_manager(
            meta.target_repo_hierarchical_tree,
            task_available_func=lambda item: need_to_generate(item, []),
        )

        # 两个函数都被排上任务（循环被打破，不死锁）。
        self.assertEqual(len(tm.task_dict), 2)
        self.assertIn(a.multithread_task_id, tm.task_dict)
        self.assertIn(b.multithread_task_id, tm.task_dict)
        # 至少有一个的依赖非空（循环打破后，先处理的那一个依赖为空，
        # 后处理的那一个依赖先处理的）。
        non_empty = [
            tid
            for tid, t in tm.task_dict.items()
            if t.dependencies
        ]
        self.assertGreater(len(non_empty), 0)

    def test_special_reference_excluded_from_second_best(self):
        """special=True 的引用不计入 second_best_break_level。"""
        a = _func("a")
        b = _func("b")
        # a 引用 b，但标记为 special
        a.reference_who = [b]
        a.special_reference_type = [True]

        meta = _build_meta_info_with_funcs({"a": a, "b": b})
        tm = meta.get_task_manager(
            meta.target_repo_hierarchical_tree,
            task_available_func=lambda item: need_to_generate(item, []),
        )

        # b 仍应先于 a（b 无依赖）。
        self.assertLess(b.multithread_task_id, a.multithread_task_id)

    def test_task_count_matches_available_items(self):
        """任务数应等于通过 task_available_func 的可生成 item 数。"""
        items = [_func(f"f{i}") for i in range(5)]
        meta = _build_meta_info_with_funcs({it.obj_name: it for it in items})
        tm = meta.get_task_manager(
            meta.target_repo_hierarchical_tree,
            task_available_func=lambda item: need_to_generate(item, []),
        )
        self.assertEqual(len(tm.task_dict), 5)


if __name__ == "__main__":
    unittest.main()
