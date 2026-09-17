"""M2 解析器测试共享 fixtures 与多文档场景（对齐函数式传参 DSL）。

多文档场景：
- 登录.md（doc_id=登录）：声明输入 username/password，输出 login_success；
  块内叶子 set 本帧输出（``[[set:...:this/login_success]]``）。
- 导出.md（doc_id=导出）：引用 登录/登录，args 传实参、returns 接收输出；
  读本帧 returns 注入的局部变量（``[[get:this/登录成功]]``）。
- 主流程.md（doc_id=主流程）：引用 导出/导出，args 传实参、returns 接收输出。
"""

from __future__ import annotations

from autobranch.parser.models import DocumentSource
from autobranch.parser.parser import BehaviorTreeParser
from autobranch.parser.refs import MappingResolver

#: 登录文档（yaml 文本形式，含配置覆盖 timeout: 30）
LOGIN_YAML = """
block 登录:
  inputs: {username: str, password: str}
  outputs: login_success
  timeout: 30
  Sequence:
    - Step:
        action: 填 [[get:this/username]]
        expect: 输入成功
    - Step:
        action: 填 [[get:this/password]]
        expect: 输入成功
    - Step:
        action: 点"登录"
        expect: 出现"工作台"
    - Step:
        action: 提取登录状态 [[set:this/login_success]]
        expect: 非空
"""

#: 登录文档的等价 dict 形式（用于 yaml/dict 一致性断言）
LOGIN_DOC: dict = {
    "block 登录": {
        "inputs": {"username": "str", "password": "str"},
        "outputs": "login_success",
        "timeout": 30,
        "Sequence": [
            {"Step": {"action": "填 [[get:this/username]]", "expect": "输入成功"}},
            {"Step": {"action": "填 [[get:this/password]]", "expect": "输入成功"}},
            {"Step": {"action": '点"登录"', "expect": '出现"工作台"'}},
            {
                "Step": {
                    "action": "提取登录状态 [[set:this/login_success]]",
                    "expect": "非空",
                }
            },
        ],
    }
}

#: 导出文档（跨文档引用 登录/登录，args 传参、returns 回收输出）
EXPORT_DOC: dict = {
    "block 导出": {
        "inputs": {"username": "str", "password": "str"},
        "outputs": "report",
        "Sequence": [
            {
                "ref": "登录/登录",
                "args": {
                    "username": "this/username",
                    "password": "this/password",
                },
                "returns": {
                    "login_success": "this/登录成功",
                },
            },
            {"Condition": "登录成功 [[get:this/登录成功]]"},
            {
                "Step": {
                    "action": '点"导出" 提取下载状态 [[set:this/report]]',
                    "expect": '出现"下载成功"',
                }
            },
        ],
    }
}

#: 主流程文档（跨文档引用 导出/导出，args 传参、returns 回收输出）
MAIN_DOC: dict = {
    "block 主流程": {
        "Sequence": [
            {
                "ref": "导出/导出",
                "args": {
                    "username": "this/账号",
                    "password": "this/密",
                },
                "returns": {
                    "report": "this/导出报告",
                },
            },
        ],
    }
}

#: 主流程文档的 yaml 文本形式（覆盖流式映射解析）
MAIN_YAML = """
block 主流程:
  Sequence:
    - ref: 导出/导出
      args: { username: this/账号, password: this/密 }
      returns: { report: this/导出报告 }
"""


def make_sources() -> list[DocumentSource]:
    """多文档 fixture：登录 / 导出 / 主流程。"""
    return [
        DocumentSource(id="主流程", data=MAIN_DOC),
        DocumentSource(id="导出", data=EXPORT_DOC),
        DocumentSource(id="登录", data=LOGIN_DOC),
    ]


def build_resolver(*sources: DocumentSource) -> MappingResolver:
    resolver = MappingResolver()
    for src in sources:
        resolver.add(src)
    return resolver


def parse_doc(
    doc_id: str,
    data: str | dict,
    resolver: MappingResolver | None = None,
    max_expand_depth: int = 64,
):
    """便捷解析：构造 DocumentSource 并解析。"""
    if resolver is None:
        resolver = MappingResolver()
    return BehaviorTreeParser(max_expand_depth=max_expand_depth).parse(
        DocumentSource(id=doc_id, data=data), resolver
    )


def walk_nodes(node):
    """先序遍历基础节点（集成测试断言仅含基础节点用）。"""
    from autobranch.parser import models

    yield node
    if isinstance(node, models.SequenceNode):
        for c in node.children:
            yield from walk_nodes(c)
    elif isinstance(node, models.SelectorNode):
        for b in node.branches:
            if b.condition is not None:
                yield from walk_nodes(b.condition)
            yield from walk_nodes(b.child)
    elif isinstance(node, models.RepeatNode):
        if node.until is not None:
            yield from walk_nodes(node.until)
        yield from walk_nodes(node.body)
