import type { NodeType } from "./treeModel";

const ITEMS: { type: NodeType; title: string; hint: string }[] = [
  { type: "Step", title: "Step", hint: "操作 + 验证" },
  { type: "Sequence", title: "Sequence", hint: "按序执行动作" },
  { type: "IfThenElse", title: "IfThenElse", hint: "判 if 分流" },
  { type: "Branch", title: "Branch", hint: "先操作再按条件分流" },
  { type: "Retry", title: "Retry", hint: "失败重试限次" },
  { type: "LoopUntil", title: "LoopUntil", hint: "直到条件满足" },
  { type: "Action", title: "Action", hint: "单个操作（叶子）" },
  { type: "FunctionCall", title: "FunctionCall", hint: "确定性调用插件函数" },
  { type: "ref", title: "ref", hint: "引用另一文档" },
];

type NodePaletteProps = {
  onAdd: (type: NodeType) => void;
};

export function NodePalette({ onAdd }: NodePaletteProps) {
  return (
    <aside className="palette" aria-label="节点面板">
      <p className="palette__title">节点面板（点击添加为游离树）</p>
      {ITEMS.map((item) => (
        <button
          key={item.type}
          type="button"
          className="palette__item"
          data-node-type={item.type}
          data-testid={`palette-${item.type}`}
          onClick={() => onAdd(item.type)}
        >
          <div className="palette__item-title">{item.title}</div>
          <div className="palette__item-hint">{item.hint}</div>
        </button>
      ))}
    </aside>
  );
}