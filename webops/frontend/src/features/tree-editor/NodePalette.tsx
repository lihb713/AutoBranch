import type { CompositeNodeType } from "../../types/node";

const PALETTE_ITEMS: { type: CompositeNodeType; title: string; hint: string }[] = [
  { type: "Step", title: "Step 单步", hint: "操作 + 验证" },
  { type: "Branch", title: "Branch 多路分支", hint: "操作后按条件分流" },
  { type: "LoopUntil", title: "LoopUntil 循环直到", hint: "直到页面条件满足" },
  { type: "IfThenElse", title: "IfThenElse 按状态分支", hint: "不先操作，直接判页面" },
  { type: "Retry", title: "Retry 重试", hint: "失败重试，限次" },
  { type: "Sequence", title: "Sequence 顺序", hint: "按顺序执行子节点" },
  { type: "ref", title: "ref 块引用", hint: "引用命名块" },
];

export function NodePalette() {
  return (
    <aside className="palette" aria-label="节点面板">
      <p className="palette__title">节点面板（拖拽到画布）</p>
      {PALETTE_ITEMS.map((item) => (
        <div
          key={item.type}
          className="palette__item"
          draggable
          onDragStart={(e) => {
            e.dataTransfer.setData("text/webops-node-type", item.type);
            e.dataTransfer.effectAllowed = "copy";
          }}
          data-node-type={item.type}
          data-testid={`palette-${item.type}`}
        >
          <div className="palette__item-title">{item.title}</div>
          <div className="palette__item-hint">{item.hint}</div>
        </div>
      ))}
    </aside>
  );
}