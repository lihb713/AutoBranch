import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HoverTooltip } from "./HoverTooltip";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("HoverTooltip", () => {
  it("底部空间不足时显示在锚点上方", async () => {
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(
      function (this: HTMLElement) {
        if ((this as HTMLElement).classList.contains("hover-tooltip")) {
          return {
            left: 0, top: 0, right: 200, bottom: 100, width: 200, height: 100,
            x: 0, y: 0, toJSON: () => ({}),
          } as DOMRect;
        }
        return {
          left: 20, top: 170, right: 120, bottom: 190, width: 100, height: 20,
          x: 20, y: 170, toJSON: () => ({}),
        } as DOMRect;
      },
    );
    Object.defineProperty(window, "innerHeight", { value: 240, configurable: true });

    render(<HoverTooltip content="完整描述">描述</HoverTooltip>);
    fireEvent.mouseEnter(screen.getByText("描述"));
    await waitFor(() => {
      expect(screen.getByRole("tooltip")).toHaveStyle({ top: "62px" });
    });
  });
});
