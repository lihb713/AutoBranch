"""浏览器驱动数据契约（M1 spec §5.5/§5.3、契约 §8.3/§9.5）。

- ``OpResult``：所有操作的统一返回（设计决策 D9），失败时 ``detail["code"]``
  携带可分类错误码（契约 §9.4）。
- ``ElementRef`` / ``PageRef``：元素与页面引用，会话内即用即弃（§7.8 策略B）。
- ``HttpResponse``：HTTP 响应记录（§5.8.2 形态A/形态B 共用）。
- ``ElementNode`` / ``DomSnapshot``：DOM 爬取快照，供 M4 语义图程序化阶段使用
  （§8.3 节点树/role/可见性/包围盒/程序化值）。
- ``LODSpec``：语义图分级参数（§9.5 四维：深度/广度/属性/关联）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ErrorCode:
    """程序侧失败分类错误码（契约 §9.4，存入 ``OpResult.detail["code"]``）。"""

    SESSION_NOT_RUNNING = "SESSION_NOT_RUNNING"  # 会话未启动或已停止
    INVALID_REF = "INVALID_REF"  # 页面/元素引用无效或已释放
    NOT_FOUND = "NOT_FOUND"  # 元素在 DOM 中不存在
    NOT_VISIBLE = "NOT_VISIBLE"  # 元素存在但不可见
    NOT_ENABLED = "NOT_ENABLED"  # 元素存在但被禁用
    NOT_EDITABLE = "NOT_EDITABLE"  # 元素存在但不可编辑
    NOT_INTERACTABLE = "NOT_INTERACTABLE"  # 元素被遮挡/不稳定，无法交互
    AMBIGUOUS = "AMBIGUOUS"  # 选择器匹配多个元素（strict 模式冲突）
    TIMEOUT = "TIMEOUT"  # 操作/等待超时（未细分）
    LOAD_TIMEOUT = "LOAD_TIMEOUT"  # 页面加载超时
    NETWORK = "NETWORK"  # 网络层失败（独立请求/页面加载）
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"  # 下载失败
    UPLOAD_FAILED = "UPLOAD_FAILED"  # 上传失败
    INVALID_ARGUMENT = "INVALID_ARGUMENT"  # 参数非法
    UNKNOWN = "UNKNOWN"  # 其他程序侧错误


@dataclass
class OpResult:
    """所有浏览器操作的统一返回（设计决策 D9）。

    :param ok: 是否成功。
    :param error: 失败原因（供 LLM 作为工具结果回读）。
    :param detail: 附加信息；失败时 ``detail["code"]`` 为分类错误码
      （契约 §9.4），成功时携带操作产物（如 ``page_ref`` / ``path``）。
    """

    ok: bool
    error: str | None = None
    detail: dict[str, Any] | None = None


@dataclass(frozen=True)
class ElementRef:
    """元素引用（来自 ref 映射表，§7.8）。

    M1 层将 ``id`` 解释为定位该元素的 CSS 选择器（确定性解析）；M4/M5
    语义图节点 id → CSS 选择器的映射由上层负责。
    """

    id: str


@dataclass(frozen=True)
class PageRef:
    """页面引用：会话内自增 id，仅在本会话内有效，stop 后全部失效（§5.10）。"""

    id: str


@dataclass(frozen=True)
class HttpResponse:
    """一次 HTTP 响应的记录（形态A 页面请求 / 形态B 独立请求共用）。"""

    method: str
    url: str
    status: int
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""

    @property
    def ok(self) -> bool:
        """HTTP 状态是否成功（2xx/3xx）。"""
        return 200 <= self.status < 400


@dataclass(frozen=True)
class LODSpec:
    """语义图分级参数（契约 §9.5 四维）。

    :param depth: 语义容器嵌套层数；``-1`` 表示不限深度（LOD-3）。
    :param breadth: 广度（``direct``/``region``/``full``）。
    :param attributes: 每节点携带字段（``minimal``/``standard``/``rich``/``full``）。
    :param relations: 关联边详尽程度（``none``/``high``/``all``）；
      M1 不产出关联边，此维度仅作记录，供 M4 使用。
    """

    depth: int = -1
    breadth: str = "full"
    attributes: str = "full"
    relations: str = "all"

    @classmethod
    def from_level(cls, level: int) -> LODSpec:
        """按契约 §9.5 的 LOD-0~3 分级构造参数。"""
        table = {
            0: cls(depth=0, breadth="direct", attributes="minimal", relations="none"),
            1: cls(depth=1, breadth="region", attributes="standard", relations="high"),
            2: cls(depth=2, breadth="region", attributes="rich", relations="all"),
            3: cls(depth=-1, breadth="full", attributes="full", relations="all"),
        }
        if level not in table:
            raise ValueError(f"非法 LOD 级别: {level}（应为 0~3）")
        return table[level]

    @property
    def unlimited_depth(self) -> bool:
        return self.depth < 0


@dataclass(frozen=True)
class Bounds:
    """元素包围盒（视口坐标，供 M4 视觉关联使用，§7.5.3）。"""

    x: float
    y: float
    w: float
    h: float


@dataclass
class ElementNode:
    """DOM 快照中的单个元素节点（契约 §7.5.3 程序化字段）。

    :param id: 快照内唯一自增标识。
    :param tag: HTML 标签名。
    :param role: 可访问性 role（程序化读取，§8.3 ②）。
    :param dom_id: 元素 DOM ``id`` 属性（无则为空串，供定位/映射使用）。
    :param text: 元素自身文本（§7.3 文本是元素属性）。
    :param value: 输入值/选中值（程序化实时读取，§9.5）。
    :param checked: checkbox/radio 勾选状态；非勾选控件为 None。
    :param disabled: 是否禁用。
    :param selected: select 当前选中项的文本。
    :param options: select 选项文本列表。
    :param visible: 可见性（M1 已剔除隐藏元素，恒为 True，§8.4 ⑤）。
    :param bounds: 包围盒（视口坐标）。
    :param depth: 在快照树中的深度。
    :param children: 子节点（语义容器层级，§8.4）。
    """

    id: str
    tag: str
    role: str
    dom_id: str = ""
    text: str = ""
    value: str = ""
    checked: bool | None = None
    disabled: bool = False
    selected: str = ""
    options: list[str] = field(default_factory=list)
    visible: bool = True
    bounds: Bounds | None = None
    depth: int = 0
    children: list[ElementNode] = field(default_factory=list)


@dataclass
class DomSnapshot:
    """DOM 爬取快照（M1 spec §5.4，供 M4 程序化阶段，§8.3）。

    :param url: 快照时的页面 URL。
    :param title: 页面标题。
    :param lod: 本次爬取使用的 LOD 参数。
    :param root: 合成根节点（``role=document``），children 为顶层节点。
    :param elements: 全部节点的扁平列表（含嵌套节点）。
    :param viewport: 视口尺寸（``{width, height}``，供 M4 计算空间方位，§8.3 ③）。
    """

    url: str
    title: str
    lod: LODSpec
    root: ElementNode | None = None
    elements: list[ElementNode] = field(default_factory=list)
    viewport: dict[str, int] = field(default_factory=dict)
