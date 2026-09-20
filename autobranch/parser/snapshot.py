"""行为树执行结构指纹（Change A 任务 2.1、Change C 经验匹配基础）。

``compute_tree_content_hash(content)`` 解析行为树文档并生成**执行结构指纹**：
只计入影响执行结果的内容（节点图 + 节点内容 + 执行配置），剔除树名 / 入参 /
出参声明 / 节点名称 / 注释空白键序。

- 规范化：经 ``normalize_document`` 转 dict（去除注释/空白）、``sort_keys``
  消除键序差异；**列表顺序保留**（Sequence.actions / Branch.branches /
  args / returns 的顺序是语义）。
- 同指纹 + 同入参 + 外部条件不变 ⇒ 执行结果理论相同；改名或改入参声明不改变
  指纹，增删改节点/节点内容/执行配置才改变。
"""

from __future__ import annotations

import hashlib
import json

from autobranch.parser.yamlio import normalize_document

#: 文档级剔除字段：树名、入参/出参声明（不参与执行结构）。
_TOP_EXCLUDED = frozenset({"tree", "inputs", "outputs"})
#: 节点级剔除字段：节点名称（显示用途，代码确认不参与报告/控制流）。
_NODE_EXCLUDED = frozenset({"name"})


def compute_tree_content_hash(content: str) -> str:
    """按行为树执行结构生成 SHA-256 指纹。

    :param content: 行为树文档文本（yaml/dict 统一槽位 DSL）。
    :returns: 64 位十六进制哈希。
    """
    data = normalize_document(content)
    out: dict[str, object] = {}
    for key, value in data.items():
        if key in _TOP_EXCLUDED:
            continue
        if key == "nodes" and isinstance(value, dict):
            out["nodes"] = {
                nid: (
                    {k: v for k, v in node.items() if k not in _NODE_EXCLUDED}
                    if isinstance(node, dict)
                    else node
                )
                for nid, node in value.items()
            }
        else:
            out[key] = value
    canonical = json.dumps(out, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = ["compute_tree_content_hash"]
