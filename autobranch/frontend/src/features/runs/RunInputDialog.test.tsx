import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RunInputDialog } from "./RunInputDialog";

describe("RunInputDialog", () => {
  it("array/object 入参按 JSON 构造，generics 原样保留", () => {
    const onConfirm = vi.fn();
    render(
      <RunInputDialog
        treeName="带参流程"
        inputs={{ payload: "object", items: "array", raw: "generics", count: "int" }}
        onConfirm={onConfirm}
        onCancel={() => {}}
      />,
    );
    fireEvent.change(screen.getByTestId("input-value-payload"), {
      target: { value: '{"host":"x"}' },
    });
    fireEvent.change(screen.getByTestId("input-value-items"), {
      target: { value: "[1,2]" },
    });
    fireEvent.change(screen.getByTestId("input-value-raw"), {
      target: { value: '{"keep":"as-text"}' },
    });
    fireEvent.change(screen.getByTestId("input-value-count"), {
      target: { value: "3" },
    });
    fireEvent.click(screen.getByTestId("run-dialog-confirm"));
    expect(onConfirm).toHaveBeenCalledWith({
      payload: { host: "x" },
      items: [1, 2],
      raw: '{"keep":"as-text"}',
      count: 3,
    });
  });
});
