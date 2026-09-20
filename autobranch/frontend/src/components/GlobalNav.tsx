import { NavLink } from "react-router-dom";

/** 全局页签导航：行为树管理 / 行为树执行列表 / 插件管理（Change A 任务 5.1）。 */
export function GlobalNav() {
  const items = [
    { to: "/", label: "行为树管理", end: true },
    { to: "/runs", label: "行为树执行列表" },
    { to: "/plugins", label: "插件管理" },
  ];
  return (
    <nav className="global-nav" aria-label="主导航" data-testid="global-nav">
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) => `global-nav__tab${isActive ? " global-nav__tab--active" : ""}`}
          data-testid={`nav-${item.to === "/" ? "trees" : item.to.slice(1)}`}
        >
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}