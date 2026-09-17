"""M3 schema 命名空间：数据模型（契约 §5.3/§5.7.4）。

``Value`` 是变量值的最小表示：标量（str/int/float/bool）或页面引用
（``PageRef``）。``SchemaFrame`` 是每次块引用创建的独立命名空间帧，
帧内以相对路径平铺存储业务变量（``storage``），并保存声明类型
（``declared``）用于读取时的强校验。纯内存结构，无任何 I/O。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeAlias


@dataclass(frozen=True)
class PageRef:
    """页面引用：指向某个浏览器页面（页句柄）。

    :param page_id: 页句柄标识（由浏览器驱动分配）。
    :param url: 页面地址（可选，便于日志与回溯）。
    """

    page_id: str
    url: str = ""


Value: TypeAlias = str | int | float | bool | PageRef | None


@dataclass(frozen=True)
class FrameDecl:
    """文档帧接口声明（来自 M2，本模块定义其所需最小结构，契约 §5.3.3）。

    :param name: 文档名（帧名）。
    :param inputs: 输入变量声明（变量名 -> 类型）。
    :param outputs: 输出变量声明（变量名 -> 类型）。
    :param config: 配置参数声明（参数名 -> 值，进入帧时注入）。
    :param config_types: 配置参数类型声明（参数名 -> 类型，缺省按值推断）。
    """

    name: str
    inputs: dict[str, str] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)
    config: dict[str, Value] = field(default_factory=dict)
    config_types: dict[str, str] = field(default_factory=dict)


@dataclass
class SchemaFrame:
    """一次文档引用的独立命名空间帧。

    帧保存 parent 指针与自身路径段（调用链），内部以平铺 dict 存储
    业务变量（``storage``）、声明类型（``declared``）与配置参数
    （``config``）。纯内存结构，无任何 I/O。

    :param id: 帧唯一标识（SchemaSpace 分配）。
    :param name: 文档名（帧名）。
    :param parent: 父帧指针（根帧为 None）。
    :param path_segments: 层级路径段（如 ``("T", "登录")``）。
    :param storage: 业务变量平铺存储（变量名 -> 值）。
    :param declared: 业务变量声明类型（变量名 -> 类型）。
    :param config: 配置参数存储（参数名 -> 值）。
    :param config_types: 配置参数类型（参数名 -> 类型）。
    :param children: 直接子帧（文档名 -> 帧，最近引用为准）。
    :param inputs: 文档输入声明（来自 FrameDecl）。
    :param outputs: 文档输出声明（来自 FrameDecl）。
    :param page_write_order: 页面变量写入顺序（解析当前页面变量用）。
    """

    id: int
    name: str
    parent: SchemaFrame | None
    path_segments: tuple[str, ...]
    storage: dict[str, Value] = field(default_factory=dict)
    declared: dict[str, str] = field(default_factory=dict)
    config: dict[str, Value] = field(default_factory=dict)
    config_types: dict[str, str] = field(default_factory=dict)
    children: dict[str, SchemaFrame] = field(default_factory=dict)
    inputs: dict[str, str] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)
    page_write_order: list[str] = field(default_factory=list)

    @property
    def path(self) -> str:
        """帧的完整层级路径（如 ``T/登录/``）。"""
        if not self.path_segments:
            return "/"
        return "/".join(self.path_segments) + "/"
