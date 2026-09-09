import { Button } from "../../components/Button";
import type { BlockDoc } from "./model";

type BlockListPanelProps = {
  blocks: BlockDoc[];
  mainBlock: string;
  activeBlock: string;
  onSelect: (name: string) => void;
  onCreate: () => void;
  onDelete: (name: string) => void;
};

export function BlockListPanel({
  blocks,
  mainBlock,
  activeBlock,
  onSelect,
  onCreate,
  onDelete,
}: BlockListPanelProps) {
  return (
    <aside className="block-list" aria-label="块列表">
      <p className="palette__title">块列表（主块 + 附属块）</p>
      {blocks.map((block) => {
        const isMain = block.name === mainBlock;
        return (
          <div
            key={block.name}
            className={`block-list__item${block.name === activeBlock ? " block-list__item--active" : ""}`}
            data-testid={`block-${block.name}`}
          >
            <button
              type="button"
              className="block-list__name"
              onClick={() => onSelect(block.name)}
              title={`${isMain ? "主块（行为树名）" : "附属块"}：${block.name}`}
            >
              {block.name}
              {isMain ? <span className="block-list__badge">主</span> : null}
            </button>
            {!isMain ? (
              <button
                type="button"
                className="block-list__delete"
                onClick={() => onDelete(block.name)}
                aria-label={`删除块 ${block.name}`}
              >
                删除
              </button>
            ) : null}
          </div>
        );
      })}
      <Button variant="ghost" onClick={onCreate} data-testid="block-create">
        + 新建块
      </Button>
    </aside>
  );
}