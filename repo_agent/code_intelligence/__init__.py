"""代码智能后端包。

通过 codebase-memory-mcp (tree-sitter + 知识图谱) 提供 AST 解析和
引用关系分析，支持 Python、Java 等 158 种编程语言。

提供 ``get_backend()`` 工厂函数，返回 ``CodebaseMemoryBackend`` 单例。
"""

from __future__ import annotations

from typing import Optional

from repo_agent.code_intelligence.base import CodeIntelligenceBackend

_backend_instance: Optional[CodeIntelligenceBackend] = None


def get_backend() -> CodeIntelligenceBackend:
    """获取 codebase-memory-mcp 后端实例（单例）。

    根据 ``SettingsManager`` 中的 ``cbm_binary_path`` 配置二进制路径。
    首次调用时创建实例并缓存。
    """
    global _backend_instance
    if _backend_instance is not None:
        return _backend_instance

    from repo_agent.settings import SettingsManager
    from repo_agent.code_intelligence.cbm_backend import CodebaseMemoryBackend

    setting = SettingsManager.get_setting()
    binary_path = setting.project.cbm_binary_path
    _backend_instance = CodebaseMemoryBackend(binary_path=binary_path)

    return _backend_instance


def reset_backend() -> None:
    """重置后端实例缓存。

    主要用于测试场景，在切换 settings 后需要重新获取后端时调用。
    """
    global _backend_instance
    _backend_instance = None


__all__ = [
    "CodeIntelligenceBackend",
    "get_backend",
    "reset_backend",
]
