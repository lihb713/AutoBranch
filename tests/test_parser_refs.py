"""任务 4.1/4.2/4.3：块引用解析、schema 命名空间与绑定、循环检测。"""

from __future__ import annotations

from parser_fixtures import (
    EXPORT_DOC,
    LOGIN_DOC,
    MAIN_DOC,
    build_resolver,
    make_sources,
    parse_doc,
)

from webops.parser import (
    ActionNode,
    ConditionNode,
    DocumentSource,
    FinishNode,
    SequenceNode,
)


def _full_resolver():
    return build_resolver(*make_sources())


def test_ref_this_named_block():
    """4.1 ``this/块名``：解析当前文档内的命名块。"""
    doc = {
        "block 主流程": {"Sequence": [{"ref": "this/登录"}, {"Finish": "结束"}]},
        "block 登录": {"Sequence": [{"Action": "填账号"}, {"Action": "填密码"}]},
    }
    result = parse_doc("主流程", doc, _full_resolver())
    assert result.checks.ok, result.checks.issues
    root = result.tree.root
    assert isinstance(root, SequenceNode)
    inline, finish = root.children
    assert isinstance(inline, SequenceNode)  # 命名块子树内联
    assert [type(c).__name__ for c in inline.children] == ["ActionNode", "ActionNode"]
    assert inline.children[0].description == "填账号"
    assert isinstance(finish, FinishNode)


def test_ref_cross_doc_block():
    """4.1 ``文档名/块名``：跨文档引用某块（此处为登录文档根块）。"""
    doc = {
        "block 出口": {
            "Sequence": [
                {
                    "ref": "登录/登录",
                    "args": {
                        "username": "this/账号",
                        "password": "this/密",
                    },
                }
            ]
        }
    }
    result = parse_doc("出口", doc, _full_resolver())
    assert result.checks.ok, result.checks.issues
    inline = result.tree.root.children[0]
    assert isinstance(inline, SequenceNode)
    step = inline.children[0]
    assert isinstance(step, SequenceNode)
    assert isinstance(step.children[0], ActionNode)


def test_ref_cross_doc_whole_tree():
    """4.1 ``文档名/文档名``：跨文档引用整个行为树（根块名 = 文档名）。"""
    doc = {
        "block 用户": {
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
                }
            ]
        }
    }
    result = parse_doc("用户", doc, _full_resolver())
    assert result.checks.ok, result.checks.issues
    inline = result.tree.root.children[0]
    # 导出块内：登录整树（Sequence）+ Condition + Step
    assert isinstance(inline, SequenceNode)
    inner = inline.children[0]
    assert isinstance(inner, SequenceNode)  # 登录整树内联
    assert isinstance(inline.children[1], ConditionNode)


def test_ref_missing_doc():
    """4.1 引用不存在的文档 → ref.missing_doc。"""
    doc = {"block 用户": {"Sequence": [{"ref": "不存在的文档/某块"}]}}
    result = parse_doc("用户", doc, _full_resolver())
    assert result.checks.ok is False
    assert any(i.code == "ref.missing_doc" for i in result.checks.issues)


def test_ref_missing_block():
    """4.1 引用存在文档但不存在的块 → ref.missing_block。"""
    doc = {"block 用户": {"Sequence": [{"ref": "登录/不存在的块"}]}}
    result = parse_doc("用户", doc, _full_resolver())
    assert result.checks.ok is False
    assert any(i.code == "ref.missing_block" for i in result.checks.issues)


def test_namespace_frames_hierarchy():
    """4.2 引用处建立独立 schema 命名空间帧（对齐 §5.7.6 流转路径）。"""
    result = parse_doc("主流程", MAIN_DOC, _full_resolver())
    assert result.checks.ok, result.checks.issues
    frames = {f.path: f for f in result.frames}
    assert set(frames) == {"主流程/", "主流程/导出/", "主流程/导出/登录/"}
    root = frames["主流程/"]
    assert root.block == "主流程"
    assert root.parent is None
    assert root.children == ("导出",)
    export = frames["主流程/导出/"]
    assert export.block == "导出"
    assert export.parent == "主流程/"
    assert export.children == ("登录",)
    login = frames["主流程/导出/登录/"]
    assert login.block == "登录"
    assert login.parent == "主流程/导出/"
    assert login.children == ()


def test_args_and_returns_recorded_on_ir():
    """4.2 引用处记录 args（实参）与 returns（回收输出）而非 bindings。"""
    from webops.parser.document import parse_structure

    st = parse_structure(DocumentSource(id="主流程", data=MAIN_DOC), MAIN_DOC)
    ref = st.ir.root.children[0]
    assert ref.kind == "ref"
    assert ref.ref_target == "导出/导出"
    assert ref.args == (("username", "this/账号"), ("password", "this/密"))
    assert ref.returns == (("report", "this/导出报告"),)
    assert ref.bindings == ()


def test_bindings_always_empty_in_result():
    """4.2 args/returns 取代写入 后 bindings 恒空（Plan ③ 移除）。"""
    result = parse_doc("主流程", MAIN_DOC, _full_resolver())
    assert result.checks.ok, result.checks.issues
    assert result.bindings == ()


def test_export_doc_inputs_typed():
    """4.2 导出文档引用登录并传参其全部输入（§5.7.6 逐层转发）。"""
    result = parse_doc("导出", EXPORT_DOC, _full_resolver())
    assert result.checks.ok, result.checks.issues
    # 块声明表 = 当前文档命名块（被引用块的声明经 RefResolver 在展开期校验）
    assert set(result.blocks) == {"导出"}
    assert result.blocks["导出"].inputs == (("username", "str"), ("password", "str"))
    # 登录块的输入声明在登录文档自身声明表中
    login = parse_doc("登录", LOGIN_DOC, _full_resolver())
    assert login.blocks["登录"].inputs == (("username", "str"), ("password", "str"))


def test_cycle_detection_two_docs():
    """4.3 A↔B 相互引用 → ref.cycle 且报告指明环路。"""
    resolver = build_resolver()
    resolver.add(
        DocumentSource(
            id="a", data={"block a": {"Sequence": [{"ref": "b/b"}]}}
        )
    )
    resolver.add(
        DocumentSource(
            id="b", data={"block b": {"Sequence": [{"ref": "a/a"}]}}
        )
    )
    result = parse_doc("a", {"block a": {"Sequence": [{"ref": "b/b"}]}}, resolver)
    assert result.checks.ok is False
    cycle = [i for i in result.checks.issues if i.code == "ref.cycle"]
    assert cycle
    assert "a/a" in cycle[0].message and "b/b" in cycle[0].message


def test_cycle_detection_self_ref():
    """4.3 自身循环引用（this/自身）→ ref.cycle。"""
    doc = {"block s": {"Sequence": [{"ref": "this/s"}]}}
    result = parse_doc("s", doc, _full_resolver())
    assert result.checks.ok is False
    assert any(i.code == "ref.cycle" for i in result.checks.issues)


def test_ref_input_not_bound():
    """4.2 引用带输入声明的块而未传实参 → ref.input_not_bound。"""
    doc = {"block 用户": {"Sequence": [{"ref": "登录/登录"}]}}
    result = parse_doc("用户", doc, _full_resolver())
    assert result.checks.ok is False
    issue = [i for i in result.checks.issues if i.code == "ref.input_not_bound"]
    assert issue
    assert "username" in issue[0].message and "password" in issue[0].message


def test_ref_args_not_input():
    """4.2 实参名不是被引用块声明输入 → ref.args_not_input。"""
    doc = {
        "block 用户": {
            "Sequence": [
                {
                    "ref": "登录/登录",
                    "args": {"not_a_declared_input": "this/账号"},
                }
            ]
        }
    }
    result = parse_doc("用户", doc, _full_resolver())
    assert any(i.code == "ref.args_not_input" for i in result.checks.issues)


def test_ref_returns_not_output():
    """4.2 返回值名不是被引用块声明输出 → ref.returns_not_output。"""
    doc = {
        "block 用户": {
            "Sequence": [
                {
                    "ref": "登录/登录",
                    "args": {"username": "this/账号", "password": "this/密"},
                    "returns": {"不存在的输出": "this/x"},
                }
            ]
        }
    }
    result = parse_doc("用户", doc, _full_resolver())
    assert any(i.code == "ref.returns_not_output" for i in result.checks.issues)


def test_ref_args_multisegment_value_out_of_scope():
    """4.2 实参值跨帧路径（this/子块/变量）→ scope.out_of_scope。"""
    doc = {
        "block 用户": {
            "Sequence": [
                {
                    "ref": "登录/登录",
                    "args": {"username": "this/其他块/账号", "password": "this/密"},
                }
            ]
        }
    }
    result = parse_doc("用户", doc, _full_resolver())
    assert any(i.code == "scope.out_of_scope" for i in result.checks.issues)
