"""M2 行为树文档解析器入口：一文档一树（§4/§12/§14 契约）。

- ``BehaviorTreeParser.parse``：yaml/dict 文档 → 基础节点行为树 + 文档级
  接口声明 + 清晰度校验报告（``ParseResult``）。
- 非 yaml/dict 输入抛出 :class:`InvalidDocumentError`；结构/语义违规以
  ``CheckReport`` 错误清单返回。
- 一文档一树：``tree``/``nodes``/``root`` 平铺节点 + 槽位引用；ref 按
  文档名引用另一文档整棵树（经 RefResolver，运行时加载）。
"""

from __future__ import annotations

from webops.parser.checks import (
    build_report,
    leaf_locatable_predicate_checks,
    post_expansion_checks,
)
from webops.parser.expand import ExpandContext, expand_document
from webops.parser.models import BehaviorTree, DocumentSource, ParseResult
from webops.parser.onedoc import parse_document as parse_onedoc
from webops.parser.refs import RefResolver


class BehaviorTreeParser:
    """行为树文档解析器（一文档一树）。

    :param max_expand_depth: 复合节点/引用展开的最大嵌套深度（递归上限）。
    """

    def __init__(self, max_expand_depth: int = 64) -> None:
        if max_expand_depth < 1:
            raise ValueError("max_expand_depth 必须 >= 1")
        self.max_expand_depth = max_expand_depth

    def parse(self, doc: DocumentSource, ref_resolver: RefResolver) -> ParseResult:
        """解析入口：yaml/dict 文档 → 基础节点行为树 + 文档声明 + 校验报告。

        :raises InvalidDocumentError: 输入既不是合法 yaml 也不是合法 dict。
        """
        ores = parse_onedoc(doc, ref_resolver)
        ctx = ExpandContext(max_depth=self.max_expand_depth)
        expansion = expand_document(ores.main_tree, ctx, decl_inputs=ores.decl_inputs)
        post = post_expansion_checks(expansion.tree)
        leaves = leaf_locatable_predicate_checks(expansion.tree)
        report = build_report([*ores.issues, *ctx.issues, *post, *leaves])
        tree = BehaviorTree(name=doc.id, root=expansion.tree)
        return ParseResult(
            tree=tree,
            blocks_tree={doc.id: expansion.tree},
            decl_inputs=ores.decl_inputs,
            decl_outputs=ores.decl_outputs,
            config=ores.config,
            checks=report,
        )


def parse(
    doc: DocumentSource, ref_resolver: RefResolver, *, max_expand_depth: int = 64
) -> ParseResult:
    """模块级便捷解析入口。"""
    return BehaviorTreeParser(max_expand_depth=max_expand_depth).parse(doc, ref_resolver)
