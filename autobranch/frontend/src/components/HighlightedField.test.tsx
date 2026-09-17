import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HighlightedField } from "./HighlightedField";

describe("HighlightedField", () => {
  it("高亮 Param 与 NewParam 记号", () => {
    const { container } = render(
      <HighlightedField
        label="描述"
        value="访问 Param.base_url 并保存为 NewParam.siteUrl:str"
        onChange={() => {}}
      />,
    );
    expect(container.querySelectorAll(".hl-param")).toHaveLength(1);
    expect(container.querySelectorAll(".hl-newparam")).toHaveLength(1);
    expect(container.querySelector(".hl-param")).toHaveTextContent("Param.base_url");
    expect(container.querySelector(".hl-newparam")).toHaveTextContent("NewParam.siteUrl:str");
  });

  it("NewParam 内嵌的 Param 不误高亮", () => {
    const { container } = render(
      <HighlightedField label="描述" value="存 NewParam.amount:int" onChange={() => {}} />,
    );
    expect(container.querySelectorAll(".hl-param")).toHaveLength(0);
    expect(container.querySelectorAll(".hl-newparam")).toHaveLength(1);
    expect(container.querySelector(".hl-newparam")).toHaveTextContent("NewParam.amount:int");
  });

  it("反引号转义段不高亮", () => {
    const { container } = render(
      <HighlightedField label="描述" value="写 `Param` 词，读 Param.x" onChange={() => {}} />,
    );
    expect(container.querySelectorAll(".hl-param")).toHaveLength(1);
    expect(container.textContent).toContain("写 Param 词，读 ");
  });

  it("多记号与普通文本混合", () => {
    const { container } = render(
      <HighlightedField
        label="描述"
        value="读 Param.a 和 Param.b，建 NewParam.c"
        onChange={() => {}}
      />,
    );
    expect(container.querySelectorAll(".hl-param")).toHaveLength(2);
    expect(container.querySelectorAll(".hl-newparam")).toHaveLength(1);
  });

  it("label 渲染与输入框透传 value", () => {
    render(<HighlightedField label="描述" value="hello" onChange={() => {}} />);
    expect(screen.getByText("描述")).toBeInTheDocument();
    expect(screen.getByDisplayValue("hello")).toBeInTheDocument();
  });
});