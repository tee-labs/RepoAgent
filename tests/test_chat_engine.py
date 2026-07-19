"""测试 ChatEngine 的 stream / 非 stream 双路径。

用户的 OpenAI 兼容 API 可能只支持 stream（非 stream 调用失败）。ChatEngine
新增 use_stream 配置：True 时用 stream_chat 聚合 chunks 取最终全文。

本测试不连真实 LLM，通过 mock OpenAILike 验证：
- 非 stream：走 .chat()，返回 response.message.content
- stream：走 stream_chat，聚合到最后一个 chunk 的 message.content
- stream 下 usage 不可用时不报错（容错）
- stream 下 usage 可用时（additional_kwargs）记录日志
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _make_doc_item():
    """构造一个最小可用、能让 build_prompt 不报错的 DocItem。"""
    from repo_agent.doc_meta_info import DocItem, DocItemType

    item = DocItem(item_type=DocItemType._function, obj_name="foo")
    item.content = {
        "type": "FunctionDef",
        "name": "foo",
        "code_content": "def foo():\n    return 1\n",
        "have_return": True,
        "code_start_line": 1,
        "name_column": 0,
    }
    item.md_content = []
    return item


def _resp(content, usage=None, additional_kwargs=None):
    """构造一个假的 ChatResponse：有 message.content，raw.usage，additional_kwargs。"""
    raw = SimpleNamespace(usage=usage)  # usage 可以是 None 或有 prompt_tokens 等
    msg = SimpleNamespace(content=content)
    return SimpleNamespace(
        message=msg, raw=raw, delta="", additional_kwargs=additional_kwargs or {}
    )


def _build_engine(use_stream):
    """构造一个 ChatEngine，llm 被 mock，settings 被 patch 成全局单例。

    patch 持续生效（不限于 with 块内），因为 generate_doc→build_prompt 也会
    读 SettingsManager。返回 (engine, cleanup)。
    """
    from repo_agent.chat_engine import ChatEngine

    setting = MagicMock()
    setting.chat_completion.use_stream = use_stream
    setting.project.language = "English"

    patcher_sm = patch("repo_agent.chat_engine.SettingsManager")
    patcher_oal = patch("repo_agent.chat_engine.OpenAILike")
    sm = patcher_sm.start()
    patcher_oal.start()
    sm.get_setting.return_value = setting

    try:
        engine = ChatEngine(project_manager=None)
    finally:
        # OpenAILike 已经不需要了（下面手动替换 llm），但 SettingsManager 的
        # patch 要保留到测试结束（build_prompt 会用）。提供一个 cleanup。
        patcher_oal.stop()

    engine.llm = MagicMock()
    cleanup = lambda: patcher_sm.stop()  # noqa: E731
    return engine, cleanup


class TestGenerateDocNonStream(unittest.TestCase):
    def setUp(self):
        self.engine, self.cleanup = _build_engine(use_stream=False)

    def tearDown(self):
        self.cleanup()

    def test_non_stream_uses_chat_and_returns_content(self):
        """use_stream=False：走 .chat()，返回 message.content。"""
        self.engine.llm.chat.return_value = _resp("doc text", usage=None)

        result = self.engine.generate_doc(_make_doc_item())

        self.engine.llm.chat.assert_called_once()
        self.engine.llm.stream_chat.assert_not_called()
        self.assertEqual(result, "doc text")


class TestGenerateDocStream(unittest.TestCase):
    def setUp(self):
        self.engine, self.cleanup = _build_engine(use_stream=True)

    def tearDown(self):
        self.cleanup()

    def test_stream_aggregates_to_last_chunk_content(self):
        """use_stream=True：聚合 stream_chat，返回最后一个 chunk 的累积全文。"""
        self.engine.llm.stream_chat.return_value = iter([
            _resp("Hel", additional_kwargs={}),
            _resp("Hello", additional_kwargs={}),
            _resp("Hello world", additional_kwargs={}),
        ])

        result = self.engine.generate_doc(_make_doc_item())

        self.engine.llm.stream_chat.assert_called_once()
        self.engine.llm.chat.assert_not_called()
        self.assertEqual(result, "Hello world")

    def test_stream_passes_include_usage_option(self):
        """stream 调用应带 stream_options={'include_usage': True}。"""
        self.engine.llm.stream_chat.return_value = iter([_resp("x")])

        self.engine.generate_doc(_make_doc_item())

        _, kwargs = self.engine.llm.stream_chat.call_args
        self.assertEqual(kwargs.get("stream_options"), {"include_usage": True})

    def test_stream_tolerates_missing_usage(self):
        """stream 下拿不到 usage（无 raw.usage 且 additional_kwargs 为空）不应报错。"""
        self.engine.llm.stream_chat.return_value = iter([_resp("final text")])

        result = self.engine.generate_doc(_make_doc_item())

        self.assertEqual(result, "final text")

    def test_stream_logs_usage_from_additional_kwargs(self):
        """stream 下 usage 在最后一个 chunk 的 additional_kwargs 时应能记录（不报错）。"""
        self.engine.llm.stream_chat.return_value = iter([
            _resp("partial", additional_kwargs={}),
            _resp(
                "partial done",
                additional_kwargs={
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            ),
        ])

        result = self.engine.generate_doc(_make_doc_item())
        self.assertEqual(result, "partial done")

    def test_stream_empty_chunks_returns_empty_string(self):
        """stream 没有任何 chunk 时返回空串，不报错。"""
        self.engine.llm.stream_chat.return_value = iter([])

        result = self.engine.generate_doc(_make_doc_item())
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
