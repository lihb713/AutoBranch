"""M2 解析器测试共享 fixtures 与多文档场景（对齐 §5.7.6 完整示例）。

多文档场景：
- 登录.md（doc_id=登录）：声明输入 username/password，输出 login_success；
  写入自身 schema（``=> $this/login_success``）。
- 导出.md（doc_id=导出）：引用 登录/登录（整树），绑定其输入；
  读直接子块输出（``{{$this/登录/login_success}}``）。
- 主流程.md（doc_id=主流程）：引用 导出/导出（整树），绑定其输入。
"""

from __future__ import annotations

from webops.parser.models import DocumentSource
from webops.parser.parser import BehaviorTreeParser
from webops.parser.refs import MappingResolver

#: 登录文档（yaml 文本形式，含配置覆盖 timeout: 30）
LOGIN_YAML = """
操作块 登录:
  输入: $username, $password
  输出: $login_success
  timeout: 30
  Sequence:
    - Step:
        action: 填 {{get:this/username}}
        expect: 输入成功
    - Step:
        action: 填 {{get:this/password}}
        expect: 输入成功
    - Step:
        action: 点"登录"
        expect: 出现"工作台"
    - Step:
        action: 提取登录状态 {{set:this/login_success}}
        expect: 非空
"""

#: 登录文档的等价 dict 形式（用于 yaml/dict 一致性断言）
LOGIN_DOC: dict = {
    "操作块 登录": {
        "输入": "$username, $password",
        "输出": "$login_success",
        "timeout": 30,
        "Sequence": [
            {"Step": {"action": "填 {{get:this/username}}", "expect": "输入成功"}},
            {"Step": {"action": "填 {{get:this/password}}", "expect": "输入成功"}},
            {"Step": {"action": '点"登录"', "expect": '出现"工作台"'}},
            {"Step": {"action": "提取登录状态 {{set:this/login_success}}", "expect": "非空"}},
        ],
    }
}

#: 导出文档（跨文档引用 登录/登录，绑定其输入，读直接子块输出）
EXPORT_DOC: dict = {
    "操作块 导出": {
        "输入": "$username, $password",
        "Sequence": [
            {
                "ref": "登录/登录",
                "写入": {
                    "$this/登录/username": "{{$this/username}}",
                    "$this/登录/password": "{{$this/password}}",
                },
            },
            {"Condition": "{{get:this/登录/login_success}}"},
            {"Step": {"action": '点"导出"', "expect": '出现"下载成功"'}},
        ],
    }
}

#: 主流程文档（跨文档引用 导出/导出，流式写入绑定）
MAIN_DOC: dict = {
    "操作块 主流程": {
        "Sequence": [
            {
                "ref": "导出/导出",
                "写入": {
                    "$this/导出/username": "{{$this/账号}}",
                    "$this/导出/password": "{{$this/密}}",
                },
            },
        ],
    }
}

#: 主流程文档的 yaml 文本形式（覆盖流式映射解析）
MAIN_YAML = """
操作块 主流程:
  Sequence:
    - ref: 导出/导出
      写入: { $this/导出/username: {{$this/账号}}, $this/导出/password: {{$this/密}} }
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
    from webops.parser import models

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
