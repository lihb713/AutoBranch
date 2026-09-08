"""M3 schema 命名空间：SchemaSpace 门面（契约 §5.1）。

``SchemaSpace`` 管理每次块引用的帧生命周期（``enter_block``/
``exit_block``）、变量读写（``write``/``read``，严格作用域）、配置参数
继承（``resolve_config``：自身 → 最近祖先 → 根级全局默认）、类型契约
校验与页面变量解析（``current_page``）。纯内存结构，无外部依赖。
"""

from __future__ import annotations

from webops.schema.errors import SchemaError, SchemaPathError
from webops.schema.models import BlockDecl, PageRef, SchemaFrame, Value
from webops.schema.path import THIS_TOKEN, resolve_target
from webops.schema.types import check_type, infer_type, validate_type_name


class SchemaSpace:
    """行为树变量命名空间门面。

    :param global_config: 全局默认配置参数（工具配置文件注入根级帧，
        契约 §5.3.4/§5.7.5）。
    :param global_config_types: 全局默认配置参数类型声明（缺省按值推断）。
    """

    def __init__(
        self,
        global_config: dict[str, Value] | None = None,
        global_config_types: dict[str, str] | None = None,
    ) -> None:
        self._next_id = 1
        self.root = self._new_frame("<root>", parent=None)
        self._current: SchemaFrame | None = None
        self._inject_config(self.root, global_config or {}, global_config_types or {})

    def _new_frame(
        self, block_name: str, parent: SchemaFrame | None
    ) -> SchemaFrame:
        frame = SchemaFrame(
            id=self._next_id,
            block_name=block_name,
            parent=parent,
            path_segments=parent.path_segments + (block_name,) if parent else (),
        )
        self._next_id += 1
        return frame

    @staticmethod
    def _inject_config(
        frame: SchemaFrame,
        config: dict[str, Value],
        config_types: dict[str, str],
    ) -> None:
        for name, value in config.items():
            type_name = config_types.get(name, infer_type(value))
            check_type(type_name, value)
            frame.config[name] = value
            frame.config_types[name] = type_name

    # ---- 帧生命周期 -------------------------------------------------

    def enter_block(
        self, block_name: str, decl: BlockDecl | None = None
    ) -> SchemaFrame:
        """进入一次块引用，创建独立帧并挂接为当前帧的直接子帧。

        帧按调用链形成层级路径（如 ``T/登录/``）；同名变量在不同帧互不
        冲突。块的配置参数声明（``decl.config``）进入帧时注入，构成
        「块自身配置优先」的覆盖源。
        """
        parent = self._current if self._current is not None else self.root
        if not block_name or "/" in block_name or block_name == THIS_TOKEN:
            raise SchemaPathError(f"非法块名: {block_name!r}")
        if block_name == parent.block_name:
            raise SchemaPathError(f"子块名不能与父块名相同: {block_name!r}")
        frame = self._new_frame(block_name, parent)
        parent.children[block_name] = frame
        if decl is not None:
            frame.inputs = dict(decl.inputs)
            frame.outputs = dict(decl.outputs)
            self._inject_config(frame, decl.config, decl.config_types)
        self._current = frame
        return frame

    def exit_block(self, frame: SchemaFrame | None = None) -> None:
        """退出当前帧并恢复父帧为当前帧。

        帧数据**保留至整个行为树执行结束**（供黑板上报各调用帧变量）；
        「释放」指退出激活栈，非物理删除。帧对象的物理删除仅随每次运行的
        全新 ``SchemaSpace`` 发生（``Engine.run`` 每轮新建）。运行期访问
        由激活帧（``self._current``）控制：已退出的帧虽数据仍在，但不经
        ``resolve_target`` 寻址（单段，仅当前帧）。
        """
        current = frame if frame is not None else self._current
        if current is None or (frame is not None and current is not frame):
            raise SchemaError("exit_block 与当前激活帧不匹配")
        self._current = current.parent

    # ---- 业务变量读写（严格作用域） -----------------------------------

    def write(
        self, frame: SchemaFrame, path: str, value: Value, value_type: str
    ) -> None:
        """写入变量：声明类型并即时校验（契约 §5.3.5）。

        只允许写入自身帧与直接子帧（契约 §5.3.2），越权抛
        ``SchemaScopeError``；类型不匹配抛 ``SchemaTypeError``。
        """
        validate_type_name(value_type)
        target, var = resolve_target(frame, path)
        check_type(value_type, value)
        target.storage[var] = value
        target.declared[var] = value_type
        if isinstance(value, PageRef):
            target.page_write_order.append(var)

    def read(self, frame: SchemaFrame, path: str) -> Value:
        """读取变量：提取时强校验（契约 §5.3.5）。

        读取自身未定义的业务变量返回 None，不向上查找（契约 §5.3.4）。
        越权读取抛 ``SchemaScopeError``。
        """
        target, var = resolve_target(frame, path)
        if var not in target.storage:
            return None
        value = target.storage[var]
        check_type(target.declared[var], value)
        return value

    # ---- 配置参数继承 -------------------------------------------------

    def set_config(
        self,
        frame: SchemaFrame,
        name: str,
        value: Value,
        value_type: str | None = None,
    ) -> None:
        """在指定帧声明配置参数（块覆盖全局默认用，契约 §5.3.4）。"""
        type_name = value_type if value_type is not None else infer_type(value)
        check_type(type_name, value)
        frame.config[name] = value
        frame.config_types[name] = type_name

    def resolve_config(self, frame: SchemaFrame, name: str) -> Value:
        """配置参数三级查找：自身 → 最近祖先 → 根级全局默认。

        业务变量不参与此链（严格作用域，见 §5.3.4）。全部未定义时返回
        None（表示工具配置未提供该参数）。
        """
        node: SchemaFrame | None = frame
        while node is not None:
            if name in node.config:
                return node.config[name]
            node = node.parent
        return None

    # ---- 页面变量机制（契约 §5.10） -----------------------------------

    def current_page(self, frame: SchemaFrame) -> PageRef | None:
        """解析当前页面变量：帧中最近写入的页面引用，无则 None。

        绑定目标页由上层（M5/M7）取用，本层保持纯逻辑。
        """
        for var in reversed(frame.page_write_order):
            value = frame.storage.get(var)
            if isinstance(value, PageRef):
                return value
        return None

    def page_refs(self, frame: SchemaFrame) -> list[tuple[str, PageRef]]:
        """列出帧中全部页面变量（变量名 -> 页面引用），互不覆盖。"""
        return [
            (var, value)
            for var, value in frame.storage.items()
            if isinstance(value, PageRef)
        ]

    def activate_page(self, frame: SchemaFrame, var_name: str) -> None:
        """把指定页面变量设为当前活动页（§5.10 多页切换）。

        将 ``var_name`` 提升为帧中最近写入的页面引用——后续 ``current_page``
        返回它。变量不存在或非页面引用时抛 ``SchemaPathError`` / ``SchemaTypeError``。
        """
        from webops.schema.errors import SchemaPathError, SchemaTypeError

        if var_name not in frame.storage:
            raise SchemaPathError(f"页面变量未定义: {var_name}")
        value = frame.storage.get(var_name)
        if not isinstance(value, PageRef):
            raise SchemaTypeError(f"变量不是页面引用: {var_name} = {value!r}")
        if var_name in frame.page_write_order:
            frame.page_write_order.remove(var_name)
        frame.page_write_order.append(var_name)

    # ---- blackboard 快照（契约 §5.3 扩展：供报告/前端展示） -------------

    def snapshot_variables(self, frame: SchemaFrame | None = None) -> list[dict]:
        """导出当前帧（含子帧）的全量变量快照。

        :param frame: 起始帧；None 用当前激活帧（无则根帧）。
        :return: ``[{path, type, value}]``，path 形如 ``this/param`` 或
          ``this/子块/param``（相对起始帧的完整层级），供执行报告与前端
          变量黑板展示。注意：此处递归子帧路径属**展示输出**（黑板上报各
          调用帧变量），并非 ``resolve_target`` 运行期寻址——运行期寻址
          已单段化，仅当前帧。
        """
        start = frame if frame is not None else self._current
        if start is None:
            start = self.root
        result: list[dict] = []

        def walk(fr: SchemaFrame, prefix: str) -> None:
            for var in sorted(fr.storage):
                result.append(
                    {
                        "path": f"{prefix}{var}",
                        "type": fr.declared.get(var, ""),
                        "value": fr.storage[var],
                    }
                )
            for child_name in sorted(fr.children):
                child = fr.children[child_name]
                walk(child, f"{prefix}{child_name}/")

        walk(start, "this/")
        return result
