import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ReportPanel } from "./ReportPanel";

describe("ReportPanel", () => {
  it("默认展示完整执行报告，可切换到回溯报告", () => {
    render(<ReportPanel execText="执行报告内容" traceText="回溯报告内容" />);
    expect(screen.getByText("执行报告内容")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "回溯报告" }));
    expect(screen.getByText("回溯报告内容")).toBeInTheDocument();
  });

  it("报告为空时给出占位提示", () => {
    render(<ReportPanel execText="" traceText={null} />);
    expect(screen.getByText("（报告为空）")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "回溯报告" }));
    expect(screen.getByText("报告加载中…")).toBeInTheDocument();
  });

  it("报告加载错误提示", () => {
    render(<ReportPanel execText={null} traceText={null} error="加载报告失败" />);
    expect(screen.getByText("加载报告失败")).toBeInTheDocument();
  });
});