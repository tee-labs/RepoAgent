"""测试 MetaInfo.parse_reference 的双向引用解析（并行版本）。

parse_reference 现在分两阶段：阶段 A 并行调 find_references（CBM 查询），
阶段 B 串行写 reference_who / who_reference_me。本测试用 fake backend
注入脚本化的引用关系，验证：
- 双向关系正确（A 引用 B → A.reference_who 含 B 且 B.who_reference_me 含 A）
- name_duplicate（自引用）被跳过
- 跨文件引用正常
- 并发执行（max_thread_count > 1）结果与串行一致
"""

import unittest
from pathlib import Path
from unittest.mock import patch

from repo_agent.doc_meta_info import DocItem, DocItemType, MetaInfo


class _FakeBackend:
    """可脚本化的假后端：find_references 按 (file, obj) 返回预设引用列表。

    refs_map: {(rel_file_path, obj_name): [(referer_rel_path, line, col), ...]}
    """

    def __init__(self, refs_map):
        self.refs_map = refs_map
        self.call_count = 0

    def find_references(self, repo_path, file_path, obj_name, start_line,
                        name_column, in_file_only=False):
        self.call_count += 1
        return list(self.refs_map.get((file_path, obj_name), []))


def _build_two_file_tree():
    """构造一个含两个文件的树：
    - a.py: func caller (行 10)
    - b.py: func callee (行 20)
    返回 (meta, caller, callee)。
    """
    root = DocItem(item_type=DocItemType._repo, obj_name="full_repo")
    file_a = DocItem(item_type=DocItemType._file, obj_name="a.py")
    file_b = DocItem(item_type=DocItemType._file, obj_name="b.py")
    root.children["a.py"] = file_a
    file_a.father = root
    root.children["b.py"] = file_b
    file_b.father = root

    caller = DocItem(item_type=DocItemType._function, obj_name="caller")
    caller.code_start_line = 10
    caller.content = {"code_start_line": 10, "code_end_line": 15, "name_column": 0}
    file_a.children["caller"] = caller
    caller.father = file_a

    callee = DocItem(item_type=DocItemType._function, obj_name="callee")
    callee.code_start_line = 20
    callee.content = {"code_start_line": 20, "code_end_line": 25, "name_column": 0}
    file_b.children["callee"] = callee
    callee.father = file_b

    root.check_depth()
    meta = MetaInfo(target_repo_hierarchical_tree=root, repo_path=Path("/tmp/repo"))
    return meta, caller, callee


class TestParseReference(unittest.TestCase):

    def _run_parse_reference(self, meta, refs_map, max_thread_count,
                             reference_parse_concurrency=None):
        """用 fake backend 跑 parse_reference，patch 掉 get_backend 和设置。

        reference_parse_concurrency=None 模拟"未设置 -rpc，跟随 -mtc"。
        """
        fake = _FakeBackend(refs_map)
        with patch("repo_agent.doc_meta_info.get_backend", return_value=fake), \
             patch("repo_agent.doc_meta_info.SettingsManager") as sm:
            proj = sm.get_setting.return_value.project
            proj.max_thread_count = max_thread_count
            proj.reference_parse_concurrency = reference_parse_concurrency
            meta.parse_reference()
        return fake

    def test_bidirectional_relation_cross_file(self):
        """caller 引用 callee：caller.reference_who 含 callee，callee.who_reference_me 含 caller。"""
        meta, caller, callee = _build_two_file_tree()
        # callee 被谁引用？find_references 对 callee 返回 caller（在 a.py 第 10 行）
        refs_map = {
            ("b.py", "callee"): [("a.py", 10, 0)],
            ("a.py", "caller"): [],
        }
        self._run_parse_reference(meta, refs_map, max_thread_count=4)

        self.assertIn(callee, caller.reference_who)
        self.assertIn(caller, callee.who_reference_me)
        # special_reference_type 长度应与 reference_who 对齐
        self.assertEqual(
            len(caller.reference_who), len(caller.special_reference_type)
        )

    def test_self_reference_skipped(self):
        """name_duplicate（引用者与被查对象同名）应跳过，不建立自引用。"""
        meta, caller, callee = _build_two_file_tree()
        # callee 的引用者里有一个同名 callee（自引用）→ 应跳过
        refs_map = {
            ("b.py", "callee"): [("b.py", 20, 0)],  # 同名同文件 → 跳过
        }
        self._run_parse_reference(meta, refs_map, max_thread_count=1)
        # callee 不应引用自己
        self.assertNotIn(callee, callee.reference_who)

    def test_referencer_not_in_repo_is_skipped(self):
        """引用者文件不在树里（find 返回 None）应跳过，不报错。"""
        meta, caller, callee = _build_two_file_tree()
        refs_map = {
            ("b.py", "callee"): [("nonexistent.py", 5, 0)],
        }
        # 不应抛异常
        self._run_parse_reference(meta, refs_map, max_thread_count=2)
        self.assertEqual(callee.who_reference_me, [])

    def test_parallel_matches_serial(self):
        """并发（max_thread_count=8）与串行（=1）结果一致。"""
        # 构造稍复杂的多引用场景
        refs_map = {
            ("b.py", "callee"): [("a.py", 10, 0), ("a.py", 11, 0)],
            ("a.py", "caller"): [],
        }

        meta1, caller1, callee1 = _build_two_file_tree()
        self._run_parse_reference(meta1, refs_map, max_thread_count=1)

        meta2, caller2, callee2 = _build_two_file_tree()
        self._run_parse_reference(meta2, refs_map, max_thread_count=8)

        # 两边引用集合应相同（按 obj_name 比较，因为是两棵独立的树）
        self.assertEqual(
            {x.obj_name for x in caller1.reference_who},
            {x.obj_name for x in caller2.reference_who},
        )
        self.assertEqual(
            {x.obj_name for x in callee1.who_reference_me},
            {x.obj_name for x in callee2.who_reference_me},
        )

    def test_find_references_called_for_each_object(self):
        """每个文件级 function 都应被查一次 find_references。"""
        meta, caller, callee = _build_two_file_tree()
        refs_map = {(k, v): [] for k, v in [("a.py", "caller"), ("b.py", "callee")]}
        fake = self._run_parse_reference(meta, refs_map, max_thread_count=4)
        # caller 和 callee 各查一次
        self.assertEqual(fake.call_count, 2)

    def test_rpc_overrides_mtc_for_parse_concurrency(self):
        """-rpc 设置时，引用解析并发用 -rpc 而非 -mtc（结果仍正确）。"""
        meta, caller, callee = _build_two_file_tree()
        refs_map = {
            ("b.py", "callee"): [("a.py", 10, 0)],
            ("a.py", "caller"): [],
        }
        # mtc=1（LLM 低并发），rpc=8（CBM 高并发）→ parse_reference 应用 8
        self._run_parse_reference(
            meta, refs_map, max_thread_count=1, reference_parse_concurrency=8
        )
        # 关系仍正确建立
        self.assertIn(callee, caller.reference_who)
        self.assertIn(caller, callee.who_reference_me)

    def test_rpc_none_falls_back_to_mtc(self):
        """-rpc 未设置（None）时，引用解析并发跟随 -mtc。"""
        meta, caller, callee = _build_two_file_tree()
        refs_map = {("a.py", "caller"): [], ("b.py", "callee"): []}
        # rpc=None → 跟随 mtc=2，不应报错
        fake = self._run_parse_reference(
            meta, refs_map, max_thread_count=2, reference_parse_concurrency=None
        )
        self.assertEqual(fake.call_count, 2)


if __name__ == "__main__":
    unittest.main()
