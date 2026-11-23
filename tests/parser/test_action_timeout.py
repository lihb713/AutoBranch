"""Action 节点级 timeout 解析。"""

from __future__ import annotations

from autobranch.parser import parse
from autobranch.parser.models import ActionNode, DocumentSource


def _doc(action: str) -> DocumentSource:
    return DocumentSource(
        id="t",
        data=f"""tree: t
nodes:
  n1: {{type: Root, body: n2}}
  n2:
    type: Action
    description: 慢动作
{action}
root: n1
""",
    )


def test_action_timeout_parsed():
    result = parse(_doc("    timeout: 12.5"), None)
    assert result.checks.ok, result.checks.issues
    node = result.tree.root.children[0]
    assert isinstance(node, ActionNode)
    assert node.timeout == 12.5


def test_action_timeout_must_be_positive_number():
    result = parse(_doc("    timeout: 0"), None)
    assert not result.checks.ok
    assert any("timeout 必须是正数" in i.message for i in result.checks.issues)
