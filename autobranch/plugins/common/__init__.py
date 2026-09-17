"""共享库（`common`，非插件）——被预置插件 `import`，不注册函数、不对 LLM 暴露。

提供预置插件共享的通用对象类型与工具。用户自定义插件仅标准库，不能引用本包。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PageObject:
    """页面对象（浏览器插件的泛型对象）。

    作为 ``object`` 类型值在变量中存储与传递；黑板 / 报告以 ``str`` 呈现。
    """

    id: str
    url: str = ""

    def __str__(self) -> str:
        return f"PageObject(id={self.id}, url={self.url})"


def display(value: object, max_len: int = 200) -> str:
    """对象呈现（黑板 / 报告）：按 ``repr`` 截断防超长。"""
    text = repr(value)
    if len(text) > max_len:
        return text[:max_len] + "…"
    return text


__all__ = ["PageObject", "display"]
