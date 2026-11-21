import { useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

type HoverTooltipProps = {
  content: string;
  children: ReactNode;
  maxWidth?: number;
  className?: string;
  dataTestid?: string;
};

/** 固定定位气泡提示：用于表格长文本，避免被 overflow 容器裁切。 */
export function HoverTooltip({
  content,
  children,
  maxWidth = 420,
  className,
  dataTestid,
}: HoverTooltipProps) {
  const anchorRef = useRef<HTMLSpanElement | null>(null);
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);

  const show = () => {
    const rect = anchorRef.current?.getBoundingClientRect();
    if (!rect) return;
    setPosition({
      left: Math.max(8, Math.min(rect.left, window.innerWidth - maxWidth - 16)),
      top: rect.bottom + 8,
    });
  };
  const hide = () => setPosition(null);

  return (
    <>
      <span
        ref={anchorRef}
        className={className}
        data-testid={dataTestid}
        tabIndex={0}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
      >
        {children}
      </span>
      {position
        ? createPortal(
            <div
              className="hover-tooltip"
              role="tooltip"
              style={{ left: position.left, top: position.top, maxWidth }}
            >
              {content}
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
