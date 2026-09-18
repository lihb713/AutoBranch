import { useMemo, useState, type InputHTMLAttributes, type TextareaHTMLAttributes } from "react";

/**
 * 参数记号高亮输入框：叠加层渲染 `Param.x`（蓝）与 `NewParam.x[:type]`（绿），
 * 上层为透明文字的原生输入框（保留光标/IME/滚动）。反引号转义段不高亮。
 */

const TOKEN_RX =
  /`[^`]*`|(?<![A-Za-z0-9_])NewParam\.([A-Za-z_][A-Za-z0-9_]*)(?::(str|int|float|bool|page_ref|object))?|(?<![A-Za-z0-9_])Param\.([A-Za-z_][A-Za-z0-9_]*)/g;

type HighlightedFieldProps = {
  label: string;
  multiline?: boolean;
} & Omit<InputHTMLAttributes<HTMLInputElement>, "onScroll"> &
  Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "onScroll">;

function highlightText(text: string) {
  const nodes: React.ReactNode[] = [];
  let last = 0;
  let key = 0;
  TOKEN_RX.lastIndex = 0;
  for (const m of text.matchAll(TOKEN_RX)) {
    const idx = m.index ?? 0;
    if (idx > last) nodes.push(text.slice(last, idx));
    const token = m[0];
    if (token.startsWith("`")) {
      nodes.push(token.slice(1, -1));
    } else if (token.startsWith("NewParam.")) {
      nodes.push(
        <span className="hl-newparam" data-testid="hl-newparam" key={key++}>
          {token}
        </span>,
      );
    } else {
      nodes.push(
        <span className="hl-param" data-testid="hl-param" key={key++}>
          {token}
        </span>,
      );
    }
    last = idx + token.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

export function HighlightedField({ label, multiline, className, ...rest }: HighlightedFieldProps) {
  const [pos, setPos] = useState({ left: 0, top: 0 });
  const text = String(rest.value ?? "");
  const highlighted = useMemo(() => highlightText(text), [text]);

  const inputClass = `text-field__input hl-field__input${className ? ` ${className}` : ""}`;
  return (
    <label className="text-field">
      <span className="text-field__label">{label}</span>
      <div className="hl-field">
        <div className="hl-field__overlay" aria-hidden="true">
          <div
            className="hl-field__overlay-text"
            style={{ transform: `translate(${-pos.left}px, ${-pos.top}px)` }}
          >
            {highlighted}
          </div>
        </div>
        {multiline ? (
          <textarea
            className={inputClass}
            {...(rest as TextareaHTMLAttributes<HTMLTextAreaElement>)}
            onScroll={(e) => setPos({ left: e.currentTarget.scrollLeft, top: e.currentTarget.scrollTop })}
          />
        ) : (
          <input
            className={inputClass}
            {...(rest as InputHTMLAttributes<HTMLInputElement>)}
            onScroll={(e) => setPos({ left: e.currentTarget.scrollLeft, top: e.currentTarget.scrollTop })}
          />
        )}
      </div>
    </label>
  );
}