"""行为树解析的数据模型（M2 spec §5.1/§5.2 与契约 §5.7 对齐）。

- 基础节点模型：``ActionNode`` / ``ConditionNode`` / ``SequenceNode`` /
  ``SelectorNode`` / ``RepeatNode`` / ``FinishNode`` —— 展开后的最终形态，
  复合节点对引擎不可见（§4.3）。
- 输出契约：``ParseResult``（tree / blocks / checks，另附 bindings/frames
  扩展字段）、``BlockDecl``（块声明）、``CheckReport``（校验报告）。
- 输入契约：``DocumentSource``。

所有模型均为 ``frozen`` dataclass，保证确定性输出（同输入两次解析结构一致）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

#: 清晰度校验规则名称（§4.4 八类，按错误码前缀映射）
RULE_BY_PREFIX = {
    "structure": "结构合法性",
    "expand": "展开后合法性",
    "ref": "块引用存在",
    "repeat": "循环上界",
    "scope": "变量契约",
    "locatable": "可定位性",
    "verify": "验证条件",
    "predicate": "谓词可校验",
}


def rule_name(code: str) -> str:
    """由错误码前缀得到校验规则名（可读）。"""
    return RULE_BY_PREFIX.get(code.split(".")[0], "清晰度")


@dataclass(frozen=True)
class Loc:
    """文档位置（路径式定位，yaml/dict 输入均适用）。

    :param doc_id: 所属文档标识。
    :param path: 文档内路径，如 ``操作块 登录/Sequence/0/Step``。
    :param line: yaml 行号（可选项，当前子集解析器不填充）。
    """

    doc_id: str
    path: str
    line: int | None = None

    def __str__(self) -> str:
        return f"{self.doc_id}/{self.path}"


@dataclass(frozen=True)
class DocumentSource:
    """行为树文档源（解析入口输入）。

    :param id: 文档标识（文档名，即根块名）。
    :param data: yaml 文本或 dict。
    :param path: 来源路径（可选，便于错误定位）。
    """

    id: str
    data: str | dict
    path: str | None = None


@dataclass(frozen=True)
class Node:
    """基础节点基类。

    :param loc: 文档位置（供校验错误定位）。
    :param frame: 所属 schema 命名空间帧路径（§5.7.4，供 M7 执行定位）。
    """

    loc: Loc | None = None
    frame: str = ""


@dataclass(frozen=True)
class ActionNode(Node):
    """动作叶子：自然语言描述 + 可选 CSS 提示（§5.2）。

    LLM 介入（agent 式执行）。可定位性 = 有 CSS 或有可映射的自然语言。
    ``set_targets`` 记录描述中声明的可写变量路径（``{{set:this/param}}``，
    供 M6 注入提示词与 M5 校验写入目标）。``set_decls`` 携带类型标注
    ``(path, type)``，type ∈ page/string/""（``{{set:page:页面A}}`` 存页签
    引用、``{{set:string:url}}`` 存文本）。
    """

    description: str = ""
    css_hint: str | None = None
    set_targets: tuple[str, ...] = ()
    set_decls: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ConditionNode(Node):
    """条件叶子：自然语言描述（断言/分支/循环条件，§5.5/§5.6）。

    :param description: 自然语言条件描述。
    :param target: 谓词指向的页面对象/目标（可选项，结构可校验用）。
    :param predicate: 比较谓词（可选项，如 等于/包含/存在）。
    """

    description: str = ""
    target: str | None = None
    predicate: str | None = None


@dataclass(frozen=True)
class SequenceNode(Node):
    """顺序执行，任一失败即整体失败（短路）。"""

    children: tuple[Node, ...] = ()


@dataclass(frozen=True)
class BranchSpec:
    """Selector 的一个分支：条件 → 子节点。

    :param condition: 分支条件；``None`` 表示 otherwise（兜底分支）。
    :param child: 该分支对应的子节点。
    """

    condition: ConditionNode | None = None
    child: Node = field(default_factory=SequenceNode)


@dataclass(frozen=True)
class SelectorNode(Node):
    """分支选择：按条件顺序检查，第一个命中即走该路径（§5.7.7）。"""

    branches: tuple[BranchSpec, ...] = ()


@dataclass(frozen=True)
class RepeatNode(Node):
    """循环（带上限安全闸）。

    :param mode: ``loop_until`` 每轮先判 until；``retry`` 每轮后判 body 结果。
    :param until: loop_until 的终止条件。
    :param max: 循环上界（防死循环），达到上限整体失败。
    """

    body: Node = field(default_factory=SequenceNode)
    mode: Literal["loop_until", "retry"] = "retry"
    until: ConditionNode | None = None
    max: int = 0


@dataclass(frozen=True)
class FinishNode(Node):
    """完成/终止节点（报告，叶子·纯程序）。"""


@dataclass(frozen=True)
class BehaviorTree:
    """内部行为树对象：根块名 + 仅含基础节点的根节点。"""

    name: str
    root: Node


@dataclass(frozen=True)
class ConfigOverride:
    """块内配置参数覆盖（§4.2/§5.7.5）。

    :param name: 配置参数名（timeout/retry/browser，工具定义固定）。
    :param value: 覆盖值。
    :param loc: 声明位置。
    """

    name: str
    value: int | str | bool
    loc: Loc | None = None


@dataclass(frozen=True)
class BlockDecl:
    """命名块声明（块接口 + 配置参数覆盖，供 M3 建立 schema 命名空间）。

    :param name: 块名。
    :param doc_id: 所属文档标识。
    :param inputs: 输入参数名（调用方需注入）。
    :param outputs: 输出参数名（调用方可读取）。
    :param config_overrides: 配置参数覆盖（仅当前块及其子树生效）。
    """

    name: str
    doc_id: str
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    config_overrides: tuple[ConfigOverride, ...] = ()
    loc: Loc | None = None


@dataclass(frozen=True)
class ParamBinding:
    """块引用处的参数绑定记录（§5.7.3/§5.7.4 的 ``写入`` 注入）。

    :param frame_path: 引用处所在 schema 帧路径（如 ``主流程/``）。
    :param block_name: 被引用块名。
    :param target_path: 写入目标（``$this/导出/username``）。
    :param value_expr: 值表达式（如 ``{{$this/账号}}``）。
    :param loc: 引用位置。
    """

    frame_path: str
    block_name: str
    target_path: str
    value_expr: str
    loc: Loc | None = None


@dataclass(frozen=True)
class FrameInfo:
    """schema 命名空间帧（类似调用栈帧，§5.7.4）。

    :param path: 帧路径，如 ``主流程/导出/``。
    :param block: 该帧对应的块名。
    :param parent: 父帧路径（根帧为 None）。
    :param children: 直接子帧路径。
    """

    path: str
    block: str
    parent: str | None
    children: tuple[str, ...]


@dataclass(frozen=True)
class CheckIssue:
    """清晰度校验错误项（可读、可定位、指明违反规则）。

    :param code: 错误码（如 ``scope.out_of_scope``）。
    :param message: 可读消息（含位置与原因）。
    :param loc: 文档位置。
    :param rule: 违反的校验规则名（§4.4 八类之一）。
    """

    code: str
    message: str
    loc: Loc | None = None
    rule: str = ""

    def __post_init__(self) -> None:
        if not self.rule:
            object.__setattr__(self, "rule", rule_name(self.code))


def make_issue(prefix: str, code: str, message: str, loc: Loc | None = None) -> CheckIssue:
    """构造校验错误项（自动拼装完整错误码与规则名）。"""
    full = f"{prefix}.{code}" if "." not in code else code
    return CheckIssue(code=full, message=message, loc=loc, rule=rule_name(full))


@dataclass(frozen=True)
class CheckReport:
    """清晰度校验报告（§4.4/§5.6）。

    :param ok: 是否全部校验项通过。
    :param issues: 错误清单（通过时为空）。
    """

    ok: bool
    issues: tuple[CheckIssue, ...] = ()


@dataclass(frozen=True)
class ParseResult:
    """解析输出契约（M2 spec §5.1）。

    :param tree: 内部行为树（仅基础节点）。
    :param blocks: 命名块声明表（输入/输出/配置参数覆盖）。
    :param checks: 清晰度校验报告。
    :param bindings: 块引用处的参数绑定记录（扩展字段，供命名空间/校验）。
    :param frames: schema 命名空间帧层级（扩展字段，§5.7.4）。
    """

    tree: BehaviorTree
    blocks: dict[str, BlockDecl]
    checks: CheckReport
    bindings: tuple[ParamBinding, ...] = ()
    frames: tuple[FrameInfo, ...] = ()
