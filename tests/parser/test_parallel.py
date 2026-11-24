"""Parallel 节点解析与作用域校验。"""

from __future__ import annotations

from autobranch.parser import parse
from autobranch.parser.models import DocumentSource, ParallelNode


def _doc(extra: str = "    max_concurrency: 2\n") -> DocumentSource:
    return DocumentSource(
        id="t",
        data=f"""tree: t
inputs: {{items: array}}
nodes:
  n1: {{type: Root, body: n2}}
  n2:
    type: Parallel
    variables: {{item: Param.items}}
    on_failure: continue
    collect:
      target: rows
      fields: [result]
{extra}    body: n3
  n3: {{type: Action, description: "处理 Param.item"}}
root: n1
""",
    )


def test_parallel_parses():
    result = parse(_doc(), None)
    assert result.checks.ok, result.checks.issues
    node = result.tree.root.children[0]
    assert isinstance(node, ParallelNode)
    assert node.variables == (("item", "Param.items"),)
    assert node.max_concurrency == 2
    assert node.collect_target == "rows"
    assert node.collect_fields == ("result",)


def test_parallel_invalid_options():
    result = parse(
        _doc("    max_concurrency: 0\n    collect: {target: '', fields: [bad-name]}\n"),
        None,
    )
    assert not result.checks.ok
    messages = " ".join(issue.message for issue in result.checks.issues)
    assert "max_concurrency" in messages
    assert "collect" in messages
