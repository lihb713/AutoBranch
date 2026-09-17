import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Screenshot } from "./Screenshot";

describe("Screenshot", () => {
  it("有 src 时渲染 img", () => {
    render(<Screenshot src="/api/reports/1/shot.png" />);
    const img = screen.getByRole("img", { name: "节点截图" });
    expect(img).toHaveAttribute("src", "/api/reports/1/shot.png");
  });

  it("加载失败显示占位", () => {
    render(<Screenshot src="/api/reports/1/missing.png" />);
    fireEvent.error(screen.getByRole("img"));
    expect(screen.getByText("截图加载失败")).toBeInTheDocument();
  });

  it("空路径显示无截图占位", () => {
    render(<Screenshot src="" />);
    expect(screen.getByText("无截图")).toBeInTheDocument();
  });
});