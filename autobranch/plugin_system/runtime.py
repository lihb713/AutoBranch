"""插件框架：插件运行上下文（引擎注入，懒装配时传给插件 ``init``）。

插件（如浏览器）在 ``init(runtime)`` 时读取运行期资源：浏览器工厂、
下载目录、截图目录、等待超时、LLM 语义图填充器等。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PluginRuntime:
    """插件运行上下文。

    :param browser_factory: 提供浏览器驱动的工厂（懒装配时调用）。
    :param browser_config: 浏览器配置（懒启动驱动时传入；None 用默认）。
    :param download_dir: 下载保存目录。
    :param screenshot_dir: 截图保存目录（``semantic_graph`` 用）。
    :param wait_timeout_ms: 等待默认超时（毫秒）。
    :param budget_limit: 语义图 token 预算上限。
    :param llm_filler: 语义图 LLM 填充器。
    :param extras: 其他插件自定义资源（按名取值）。
    """

    browser_factory: Any = None
    browser_config: Any = None
    download_dir: str = "."
    screenshot_dir: str | None = None
    wait_timeout_ms: int = 30000
    budget_limit: int | None = None
    llm_filler: Any = None
    extras: dict[str, Any] = field(default_factory=dict)


__all__ = ["PluginRuntime"]
