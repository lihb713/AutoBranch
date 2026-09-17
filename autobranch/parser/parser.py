"""M2 行为树文档解析器入口：一文档一树（§4/§12/§14 契约）。

- ``BehaviorTreeParser.parse``：yaml/dict 文档 → 基础节点行为树 + 文档级
  接口声明 + 清晰度校验报告（``ParseResult``）。
- 非 yaml/dict 输入抛出 :class:`InvalidDocumentError`；结构/语义违规以
  ``CheckReport`` 错误清单返回。
- 一文档一树：``tree``/``nodes``/``root`` 平铺节点 + 槽位引用；ref 按
  文档名引用另一文档整棵树（经 RefResolver，运行时加载）。
"""

from __future__ import annotations

from autobranch.parser.checks import (
    build_report,
    function_call_checks,
    leaf_locatable_predicate_checks,
    post_expansion_checks,
)
from autobranch.parser.expand import ExpandContext, expand_document
from autobranch.parser.models import BehaviorTree, DocumentSource, ParseResult
from autobranch.parser.onedoc import parse_document as parse_onedoc
from autobranch.parser.refs import RefResolver


class BehaviorTreeParser:
    """行为树文档解析器（一文档一树）。

    :param max_expand_depth: 复合节点/引用展开的最大嵌套深度（递归上限）。
    """

    def __init__(self, max_expand_depth: int = 64) -> None:
        if max_expand_depth < 1:
            raise ValueError("max_expand_depth 必须 >= 1")
        self.max_expand_depth = max_expand_depth

    def parse(
        self,
        doc: DocumentSource,
        ref_resolver: RefResolver,
        function_registry: object | None = None,
    ) -> ParseResult:
        """解析入口：yaml/dict 文档 → 基础节点行为树 + 文档声明 + 校验报告。

        :param function_registry: 可选，插件函数注册表（提供 ``function(name)``），
          用于 FunctionCall 函数存在与参数对齐校验；None 时跳过（运行时兜底）。

        :raises InvalidDocumentError: 输入既不是合法 yaml 也不是合法 dict。
        """
        ores = parse_onedoc(doc, ref_resolver)
        ctx = ExpandContext(max_depth=self.max_expand_depth)
        expansion = expand_document(ores.main_tree, ctx, decl_inputs=ores.decl_inputs)
        post = post_expansion_checks(expansion.tree)
        leaves = leaf_locatable_predicate_checks(expansion.tree)
        funcs = function_call_checks(expansion.tree, function_registry) if function_registry else ()
        report = build_report([*ores.issues, *ctx.issues, *post, *leaves, *funcs])
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
    doc: DocumentSource,
    ref_resolver: RefResolver,
    *,
    max_expand_depth: int = 64,
    function_registry: object | None = None,
) -> ParseResult:
    """模块级便捷解析入口。"""
    return BehaviorTreeParser(max_expand_depth=max_expand_depth).parse(
        doc, ref_resolver, function_registry
    )
