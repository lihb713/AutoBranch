"""WebOps 行为树文档解析器（M2）。

将行为树文档（yaml/dict）确定性解析为**仅含基础节点**的内部行为树对象，
展开复合节点（§4.3）、解析块引用（§5.7.3）、提取 schema 绑定声明并执行
清晰度校验（§4.4）。纯逻辑、无外部运行时依赖（不依赖 LLM / 浏览器）。

公开入口：
- ``BehaviorTreeParser.parse`` / ``parse``：解析入口
- 数据模型：``Node`` 各子类、``BranchSpec``、``BlockDecl``、``ParseResult``、
  ``CheckReport``、``DocumentSource`` 等
- 引用解析：``RefResolver``（协议）、``MappingResolver``（内存实现）
- 异常：``ParserError`` / ``InvalidDocumentError`` / ``RefNotFoundError``
"""

from webops.parser.errors import InvalidDocumentError, ParserError, RefNotFoundError
from webops.parser.models import (
    ActionNode,
    BehaviorTree,
    BlockDecl,
    BranchSpec,
    CheckIssue,
    CheckReport,
    ConditionNode,
    ConfigOverride,
    DocumentSource,
    FinishNode,
    Loc,
    Node,
    ParseResult,
    RefNode,
    RepeatNode,
    SelectorNode,
    SequenceNode,
    make_issue,
)
from webops.parser.parser import BehaviorTreeParser, parse
from webops.parser.refs import MappingResolver, RefResolver

__all__ = [
    "BehaviorTreeParser",
    "parse",
    "ActionNode",
    "ConditionNode",
    "SequenceNode",
    "SelectorNode",
    "RepeatNode",
    "FinishNode",
    "Node",
    "RefNode",
    "BranchSpec",
    "BehaviorTree",
    "BlockDecl",
    "ConfigOverride",
    "CheckIssue",
    "CheckReport",
    "ParseResult",
    "DocumentSource",
    "Loc",
    "make_issue",
    "RefResolver",
    "MappingResolver",
    "ParserError",
    "InvalidDocumentError",
    "RefNotFoundError",
]
