"""Debug 节点解析。"""

from __future__ import annotations

from autobranch.parser import parse
from autobranch.parser.models import DebugNode, DocumentSource


def test_debug_parses_variables():
    result = parse(
        DocumentSource(
            id="t",
            data="""tree: t
nodes:
  n1: {type: Root, body: n2}
  n2:
    type: Debug
    variables: [result, rows]
root: n1
""",
        ),
        None,
    )
    assert result.checks.ok, result.checks.issues
    node = result.tree.root.children[0]
    assert isinstance(node, DebugNode)
    assert node.vars == ("result", "rows")
