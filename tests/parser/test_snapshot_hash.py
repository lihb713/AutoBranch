"""compute_tree_content_hash 执行结构指纹测试（Change A 任务 2.1）。

覆盖：确定性；改名（树名/节点名）不影响；键序/注释不影响；改节点内容/
槽位顺序/执行配置改变；入参/出参声明不影响；节点 id 计入。
"""

from __future__ import annotations

from autobranch.parser.snapshot import compute_tree_content_hash

_BASE = """\
tree: 下单流程
inputs:
  user: str
outputs:
  - 结果
nodes:
  n1:
    type: Root
    name: 根
    body: n2
  n2:
    type: Sequence
    name: 流程
    actions: [n3, n4]
  n3:
    type: Action
    name: 登录
    description: 点击"登录"
  n4:
    type: Action
    name: 提交
    description: 点击"提交"
root: n1
"""


def _hash(*, nodes=None, tree=_BASE):
    return compute_tree_content_hash(tree)


def test_deterministic():
    assert _hash() == _hash()


def test_rename_tree_keeps_hash():
    renamed = _BASE.replace("tree: 下单流程", "tree: 别的名字")
    assert compute_tree_content_hash(renamed) == _hash()


def test_rename_node_name_keeps_hash():
    renamed = _BASE.replace("name: 登录", "name: 改名登录")
    assert compute_tree_content_hash(renamed) == _hash()


def test_key_order_and_comments_keeps_hash():
    # 键序打乱 + 注释/空行（normalize 后等价）
    reordered = """\
tree: 下单流程
# 注释行
nodes:
  n2:
    actions: [n3, n4]
    type: Sequence
    name: 流程
  n4:
    name: 提交
    type: Action
    description: 点击"提交"
  n3:
    type: Action
    description: 点击"登录"
    name: 登录
  n1:
    body: n2
    type: Root
    name: 根
root: n1
outputs:
  - 结果
inputs:
  user: str
"""
    assert compute_tree_content_hash(reordered) == _hash()


def test_inputs_outputs_decl_keeps_hash():
    changed = _BASE.replace("inputs:\n  user: str", "inputs:\n  user: int\n  extra: bool").replace(
        "outputs:\n  - 结果", "outputs:\n  - 结果\n  - 日志"
    )
    assert compute_tree_content_hash(changed) == _hash()


def test_change_node_description_changes_hash():
    changed = _BASE.replace('description: 点击"登录"', 'description: 点击"登录按钮"')
    assert compute_tree_content_hash(changed) != _hash()


def test_change_slot_order_changes_hash():
    changed = _BASE.replace("actions: [n3, n4]", "actions: [n4, n3]")
    assert compute_tree_content_hash(changed) != _hash()


def test_change_execution_config_changes_hash():
    changed = _BASE + "timeout: 120\n"
    assert compute_tree_content_hash(changed) != _hash()


def test_node_id_included():
    renamed = _BASE.replace("n3", "m3").replace("n4", "m4").replace("n2", "m2").replace("n1", "m1")
    assert compute_tree_content_hash(renamed) != _hash()
