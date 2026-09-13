import type { NodeType } from "./treeModel";

const ITEMS: { type: NodeType; title: string; hint: string }[] = [
  { type: "Step", title: "步骤", hint: "操作 + 验证" },
  { type: "Sequence", title: "顺序", hint: "按序执行动作" },
  { type: "IfThenElse", title: "判断", hint: "判 if 分流" },
  { type: "Branch", title: "分支", hint: "先操作再按条件分流" },
  { type: "Retry", title: "重试", hint: "失败重试限次" },
  { type: "LoopUntil", title: "循环", hint: "直到条件满足" },
  { type: "Action", title: "动作", hint: "单个操作（叶子）" },
  { type: "ref", title: "引用", hint: "引用另一文档" },
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