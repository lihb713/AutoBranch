import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { FunctionInfo } from "../../types/plugin";
import { ConditionField, conditionSummary, predicateSummary } from "./ConditionEditor";

const FUNCTIONS: FunctionInfo[] = [
  {
    full_name: "predicate.gt",
    plugin: "predicate",
    name: "gt",
    description: "大于",
    returns: { result: "bool" },
    parameters: {
      type: "object",
      properties: { a: {}, b: {} },
      required: ["a", "b"],
    },
  },
  {
    full_name: "compute.add",
    plugin: "compute",
    name: "add",
    description: "加法",
    returns: { result: "float" },
    parameters: { type: "object", properties: { a: {}, b: {} }, required: ["a", "b"] },
  },
];

describe("ConditionEditor", () => {
  it("自然语言条件写入显式 mode", () => {
    const onChange = vi.fn();
    render(
      <ConditionField
        label="条件"
        value={undefined}
        functions={FUNCTIONS}
        dataTestid="cond"
        onChange={onChange}
      />,
    );
    fireEvent.change(screen.getByTestId("cond-text"), { target: { value: "出现成功" } });
    expect(onChange).toHaveBeenCalledWith({ mode: "natural", text: "出现成功" });
  });

  it("切换谓词模式", () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const onChange = vi.fn();
    render(
      <ConditionField
        label="条件"
        value={{ mode: "natural", text: "出现成功" }}
        functions={FUNCTIONS}
        dataTestid="cond"
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByTestId("cond-predicate"));
    expect(onChange).toHaveBeenCalledWith({
      mode: "predicate",
      expression: { all: [] },
    });
  });

  it("谓词编辑器只显示单 bool 函数并可编辑保存", () => {
    const onChange = vi.fn();
    render(
      <ConditionField
        label="条件"
        value={{
          mode: "predicate",
          expression: {
            all: [{ function: "predicate.gt", args: ["1", "2"], kwargs: {} }],
          },
        }}
        functions={FUNCTIONS}
        dataTestid="cond"
        onChange={onChange}
      />,
    );
    expect(screen.getByTestId("cond-summary")).toHaveTextContent("ALL(predicate.gt)");
    fireEvent.click(screen.getByTestId("cond-edit"));
    expect(screen.getByTestId("condition-editor")).toBeInTheDocument();
    expect(screen.queryByText("compute.add")).not.toBeInTheDocument();
    fireEvent.change(screen.getByTestId("predicate-arg-b"), { target: { value: "3" } });
    fireEvent.click(screen.getByTestId("condition-save"));
    expect(onChange).toHaveBeenCalledWith({
      mode: "predicate",
      expression: {
        all: [{ function: "predicate.gt", args: ["1", "3"], kwargs: {} }],
      },
    });
  });

  it("条件摘要支持嵌套组", () => {
    const expr = {
      all: [
        { function: "predicate.gt", args: ["1", "0"] },
        { not: { function: "predicate.is_empty", args: ["x"] } },
      ],
    };
    expect(predicateSummary(expr)).toContain("ALL");
    expect(conditionSummary({ mode: "predicate", expression: expr })).toContain("NOT");
  });
});
