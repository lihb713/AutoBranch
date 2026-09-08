"""M2 行为树文档解析器入口：两阶段流水线（§4/§5.7 契约）。

- ``BehaviorTreeParser.parse``：yaml/dict 文档 → 基础节点行为树 + 块声明表
  + 清晰度校验报告（``ParseResult``）。
- 非 yaml/dict 输入抛出 :class:`InvalidDocumentError`；结构/语义违规以
  ``CheckReport`` 错误清单返回。
"""

from __future__ import annotations

from webops.parser.checks import (
    build_report,
    leaf_locatable_predicate_checks,
    post_expansion_checks,
)
from webops.parser.document import parse_structure
from webops.parser.expand import ExpandContext, expand_document
from webops.parser.models import BehaviorTree, DocumentSource, ParseResult
from webops.parser.refs import RefResolver
from webops.parser.yamlio import normalize_document


class BehaviorTreeParser:
    """行为树文档解析器。

    两阶段流水线（设计决策 D1）：
    1. 结构解析（``parse_structure``）：块定义识别、接口/配置提取、中间表示；
    2. 展开与校验（``expand_document``）：复合节点展开、块引用解析、
       schema 命名空间、清晰度校验。

    :param max_expand_depth: 复合节点/引用展开的最大嵌套深度（递归上限）。
    """

    def __init__(self, max_expand_depth: int = 64) -> None:
        if max_expand_depth < 1:
            raise ValueError("max_expand_depth 必须 >= 1")
        self.max_expand_depth = max_expand_depth

    def parse(self, doc: DocumentSource, ref_resolver: RefResolver) -> ParseResult:
        """解析入口：yaml/dict 文档 → 基础节点行为树 + 块声明表 + 校验报告。

        :raises InvalidDocumentError: 输入既不是合法 yaml 也不是合法 dict。
        """
        raw = normalize_document(doc.data)
        structure = parse_structure(doc, raw)
        ctx = ExpandContext(
            ir=structure.ir, resolver=ref_resolver, max_depth=self.max_expand_depth
        )
        expansion = expand_document(ctx)
        post = post_expansion_checks(expansion.tree)
        leaves = leaf_locatable_predicate_checks(expansion.tree)
        report = build_report(
            [
                *structure.issues,
                *ctx.resolved_doc_issues,
                *expansion.issues,
                *post,
                *leaves,
            ]
        )
        tree = BehaviorTree(name=structure.ir.root_block, root=expansion.tree)
        return ParseResult(
            tree=tree,
            blocks=structure.ir.blocks,
            checks=report,
            bindings=expansion.bindings,
            frames=expansion.frames,
        )


def parse(
    doc: DocumentSource, ref_resolver: RefResolver, *, max_expand_depth: int = 64
) -> ParseResult:
    """模块级便捷解析入口。"""
    return BehaviorTreeParser(max_expand_depth=max_expand_depth).parse(doc, ref_resolver)
