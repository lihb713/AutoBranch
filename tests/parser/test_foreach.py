"""ForEach 节点解析与作用域校验。"""

from __future__ import annotations

from autobranch.parser import parse
from autobranch.parser.models import ActionNode, DocumentSource, ForEachNode


def _doc(variables: str = "{env_id: Param.env_ids, label: 'x'}", on_failure: str = "continue"):
    return DocumentSource(
        id="t",
        data=f"""tree: t
inputs: {{env_ids: object}}
nodes:
  n1: {{type: Root, body: n2}}
  n2:
    type: ForEach
    name: 遍历环境
    variables: {variables}
    body: n3
    on_failure: {on_failure}
  n3: {{type: Action, name: 处理, description: "处理 Param.env_id"}}
root: n1
""",
    )


def test_foreach_parses_variables_body_and_policy():
    result = parse(_doc(), None)
    assert result.checks.ok, result.checks.issues
    node = result.tree.root.children[0]
    assert isinstance(node, ForEachNode)
    assert node.variables == (("env_id", "Param.env_ids"), ("label", "x"))
    assert node.on_failure == "continue"
    assert isinstance(node.body, ActionNode)


def test_foreach_unknown_item_read_rejected():
    result = parse(
        DocumentSource(
            id="t",
            data="""tree: t
inputs: {env_ids: object}
nodes:
  n1: {type: Root, body: n2}
  n2:
    type: ForEach
    variables: {env_id: Param.env_ids}
    body: n3
  n3: {type: Action, description: "处理 Param.missing"}
root: n1
""",
        ),
        None,
    )
    assert not result.checks.ok
    assert any(i.code == "scope.get_undeclared" for i in result.checks.issues)


def test_foreach_invalid_policy_rejected():
    result = parse(_doc(on_failure="stop"), None)
    assert not result.checks.ok
    assert any("on_failure" in i.message for i in result.checks.issues)
