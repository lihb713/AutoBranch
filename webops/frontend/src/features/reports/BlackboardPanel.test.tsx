import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BlackboardPanel } from "./BlackboardPanel";

describe("BlackboardPanel", () => {
  it("空变量显示占位", () => {
    render(<BlackboardPanel variables={[]} />);
    expect(screen.getByText("（暂无变量）")).toBeVisible();
  });

  it("渲染变量路径/类型/值", () => {
    render(
      <BlackboardPanel
        variables={[
          { path: "this/订单号", type: "str", value: "ORD-001" },
          { path: "this/amount", type: "float", value: 98.0 },
        ]}
      />,
    );
    expect(screen.getByText("this/订单号")).toBeVisible();
    expect(screen.getByText("ORD-001")).toBeVisible();
    expect(screen.getByText("float")).toBeVisible();
    expect(screen.getByText("this/amount")).toBeVisible();
    expect(screen.getByText("98")).toBeVisible();
  });

  it("对象值以 JSON 展示", () => {
    render(
      <BlackboardPanel
        variables={[{ path: "this/页", type: "page_ref", value: { page_id: "1", url: "http://x" } }]}
      />,
    );
    expect(screen.getByText(/page_id/)).toBeVisible();
  });
});
