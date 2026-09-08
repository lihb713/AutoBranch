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
    ConditionNode,
    DocumentSource,
    FinishNode,
    RefNode,
    SequenceNode,
)


def _full_resolver():
    return build_resolver(*make_sources())


def test_ref_becomes_refnode_not_inlined():
    """4.2 ref 保留为 RefNode：携带 ref_target/args/returns，不内联子块树。"""
    doc = {
        "block 主": {
            "Sequence": [
                {"ref": "this/登录", "args": {"u": "this/a"}, "returns": {"r": "this/b"}}
            ]
        },
        "block 登录": {
            "inputs": {"u": "str"},
            "outputs": "r",
            "Sequence": [{"Step": {"action": "x"}}],
        },
    }
    result = parse_doc("主", doc, _full_resolver())
    ref_node = result.tree.root.children[0]
    assert isinstance(ref_node, RefNode)
    assert ref_node.ref_target == "this/登录"
    assert ref_node.args == (("u", "this/a"),)
    assert ref_node.returns == (("r", "this/b"),)


def test_blocks_tree_contains_each_block():
    """4.2 blocks_tree 含每个命名块的基础树；根块树与 tree.root 同一。"""
    doc = {
        "block 主": {"Sequence": [{"ref": "this/登录"}]},
        "block 登录": {"Sequence": [{"Step": {"action": "x"}}]},
    }
    result = parse_doc("主", doc, _full_resolver())
    assert set(result.blocks_tree) == {"主", "登录"}
    assert result.blocks_tree["主"] is result.tree.root


def test_ref_this_named_block():
    """4.1 ``this/块名``：解析当前文档内的命名块（保留为 RefNode，不内联）。"""
    doc = {
        "block 主流程": {"Sequence": [{"ref": "this/登录"}, {"Finish": "结束"}]},
        "block 登录": {"Sequence": [{"Action": "填账号"}, {"Action": "填密码"}]},
    }
    result = parse_doc("主流程", doc, _full_resolver())
    assert result.checks.ok, result.checks.issues
    root = result.tree.root
    assert isinstance(root, SequenceNode)
    ref_node, finish = root.children
    assert isinstance(ref_node, RefNode)
    assert ref_node.ref_target == "this/登录"
    assert isinstance(finish, FinishNode)
    # 登录块以独立预展开树存于 blocks_tree（不在主树内内联）
    login_tree = result.blocks_tree["登录"]
    assert [type(c).__name__ for c in login_tree.children] == ["ActionNode", "ActionNode"]
    assert login_tree.children[0].description == "填账号"


def test_ref_cross_doc_block():
    """4.1 ``文档名/块名``：跨文档引用某块（此处为登录文档根块，保留为 RefNode）。"""
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
    ref_node = result.tree.root.children[0]
    assert isinstance(ref_node, RefNode)
    assert ref_node.ref_target == "登录/登录"
    assert ref_node.args == (("username", "this/账号"), ("password", "this/密"))
    assert set(result.blocks_tree) == {"出口", "登录"}


def test_ref_cross_doc_whole_tree():
    """4.1 ``文档名/文档名``：跨文档引用整个行为树（RefNode + 独立预展开树）。"""
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
    ref_node = result.tree.root.children[0]
    assert isinstance(ref_node, RefNode)
    assert ref_node.ref_target == "导出/导出"
    assert ref_node.args == (("username", "this/账号"), ("password", "this/密"))
    assert ref_node.returns == (("report", "this/导出报告"),)
    # 导出块树独立预展开于 blocks_tree；其内部引用 登录/登录 亦为 RefNode
    export_tree = result.blocks_tree["导出"]
    assert isinstance(export_tree, SequenceNode)
    inner = export_tree.children[0]
    assert isinstance(inner, RefNode)
    assert inner.ref_target == "登录/登录"
    assert isinstance(export_tree.children[1], ConditionNode)


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


def test_blocks_tree_contains_all_docs_blocks():
    """4.2 每块独立预展开：blocks_tree 含根文档与全部跨文档加载块的基础树。"""
    result = parse_doc("主流程", MAIN_DOC, _full_resolver())
    assert result.checks.ok, result.checks.issues
    assert set(result.blocks_tree) == {"主流程", "导出", "登录"}
    assert isinstance(result.blocks_tree["主流程"], SequenceNode)
    export = result.blocks_tree["导出"]
    assert isinstance(export, SequenceNode)
    assert isinstance(export.children[0], RefNode)  # 导出内引用 登录/登录
    login = result.blocks_tree["登录"]
    assert isinstance(login, SequenceNode)


def test_cross_doc_block_internal_this_resolves_to_owner_doc():
    """handoff 2：跨文档块内部的 ``this/块`` 解析到**所属文档**（非根文档）。

    主流程（根文档）引用 导出/导出；导出块内部引用 this/登录——`this` 应为
    所属文档（导出），而非根文档（主流程）。旧实现恒解析到根文档会误报
    ref.missing_block。
    """
    resolver = build_resolver(
        DocumentSource(
            id="主流程",
            data={"block 主流程": {"Sequence": [{"ref": "导出/导出"}]}},
        ),
        DocumentSource(
            id="导出",
            data={
                "block 导出": {"Sequence": [{"ref": "this/登录"}]},
                "block 登录": {
                    "Sequence": [{"Step": {"action": "x", "expect": "出现"}}]
                },
            },
        ),
    )
    result = parse_doc("主流程", {"block 主流程": {"Sequence": [{"ref": "导出/导出"}]}}, resolver)
    assert result.checks.ok, result.checks.issues
    # 导出块树内的 this/登录 保留为 RefNode，目标解析到所属文档（导出）
    export_tree = result.blocks_tree["导出"]
    inner = export_tree.children[0]
    assert isinstance(inner, RefNode)
    assert inner.ref_target == "this/登录"
    # 登录块来自导出文档，被预展开进 blocks_tree
    assert "登录" in result.blocks_tree
    assert [type(c).__name__ for c in result.blocks_tree["登录"].children] == [
        "SequenceNode"
    ]


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
