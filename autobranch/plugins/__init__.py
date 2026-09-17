"""预置插件包（M7 插件集）：浏览器 / 计算 / SSH / 文件 + common 共享库。

预置插件是工具的一部分（随工具分发），引擎启动时经插件框架（M3）
扫描 ``autobranch.plugins`` 下的子包注册。各插件包以 ``plugin`` 变量暴露
``PluginBase`` 实例。
"""

__all__: list[str] = []
