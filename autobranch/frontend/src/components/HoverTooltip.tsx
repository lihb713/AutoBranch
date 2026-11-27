import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
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
  const tooltipRef = useRef<HTMLDivElement | null>(null);
  const [position, setPosition] = useState<{
    left: number;
    top: number;
    anchorTop: number;
  } | null>(null);

  const show = () => {
    const rect = anchorRef.current?.getBoundingClientRect();
    if (!rect) return;
    setPosition({
      left: Math.max(8, Math.min(rect.left, window.innerWidth - maxWidth - 16)),
      top: rect.bottom + 8,
      anchorTop: rect.top,
    });
  };
  const hide = () => setPosition(null);

  useLayoutEffect(() => {
    if (!position || !tooltipRef.current) return;
    const tooltipRect = tooltipRef.current.getBoundingClientRect();
    const overflowBottom = position.top + tooltipRect.height > window.innerHeight - 8;
    if (!overflowBottom) return;
    const above = Math.max(8, position.anchorTop - tooltipRect.height - 8);
    if (above !== position.top) {
      setPosition({ ...position, top: above });
    }
  }, [position]);

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
              ref={tooltipRef}
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
