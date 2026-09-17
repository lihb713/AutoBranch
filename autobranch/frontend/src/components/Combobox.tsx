import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";

export type ComboboxOption = {
  /** 提交给 onChange 的值（如函数全名 / 节点 id / 文档名）。 */
  value: string;
  /** 下拉展示文本（如函数全名 / 节点显示名）。 */
  label: string;
  description?: string;
};

type ComboboxProps = {
  label: string;
  value: string;
  options: ComboboxOption[];
  placeholder?: string;
  disabled?: boolean;
  dataTestid?: string;
  onChange: (value: string) => void;
};

/**
 * 可搜索下拉：输入过滤 + 键盘导航（↑/↓/回车/Esc）+ 点击选择。
 *
 * 当前值不在选项清单中时仍原样显示并可保存（兼容旧树 / 手输 / 插件已删除）。
 */
export function Combobox({
  label,
  value,
  options,
  placeholder,
  disabled,
  dataTestid,
  onChange,
}: ComboboxProps) {
  const valueLabel = options.find((o) => o.value === value)?.label ?? value;
  const [text, setText] = useState(valueLabel);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const [dirty, setDirty] = useState(false);
  const controlRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setText(options.find((o) => o.value === value)?.label ?? value);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  useEffect(() => {
    const onDocMouseDown = (e: MouseEvent) => {
      if (controlRef.current && !controlRef.current.contains(e.target as Node)) {
        if (dirty && text !== value) {
          commitRaw(text);
        } else {
          setOpen(false);
        }
      }
    };
    document.addEventListener("mousedown", onDocMouseDown);
    return () => document.removeEventListener("mousedown", onDocMouseDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, value, options, dirty]);

  const filtered = useMemo(() => {
    const q = dirty ? text.trim().toLowerCase() : "";
    if (!q) return options;
    const starts: ComboboxOption[] = [];
    const contains: ComboboxOption[] = [];
    for (const o of options) {
      const hay = `${o.label} ${o.value} ${o.description ?? ""}`.toLowerCase();
      if (!hay.includes(q)) continue;
      if (o.label.toLowerCase().startsWith(q)) starts.push(o);
      else contains.push(o);
    }
    return [...starts, ...contains];
  }, [text, options, dirty]);

  const commit = (opt: ComboboxOption) => {
    onChange(opt.value);
    setText(opt.label);
    setDirty(false);
    setOpen(false);
  };

  const commitRaw = (raw: string) => {
    const exact = options.find((o) => o.value === raw || o.label === raw);
    if (exact) {
      commit(exact);
      return;
    }
    onChange(raw);
    setText(raw);
    setDirty(false);
    setOpen(false);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setHighlight((h) => (filtered.length ? Math.min(h + 1, filtered.length - 1) : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (open && filtered.length > 0 && highlight < filtered.length) {
        commit(filtered[highlight]);
      } else {
        commitRaw(text);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
      setDirty(false);
      setText(valueLabel);
    }
  };

  return (
    <label className="text-field combobox">
      <span className="text-field__label">{label}</span>
      <div className="combobox__control" ref={controlRef}>
        <input
          className="text-field__input combobox__input"
          value={text}
          placeholder={placeholder}
          disabled={disabled}
          data-testid={dataTestid}
          onFocus={() => {
            setDirty(false);
            setOpen(true);
          }}
          onChange={(e) => {
            setText(e.target.value);
            setDirty(true);
            setOpen(true);
            setHighlight(0);
          }}
          onKeyDown={onKeyDown}
        />
        {open && !disabled ? (
          <ul className="combobox__list" role="listbox">
            {filtered.length === 0 ? (
              <li className="combobox__empty">无匹配项</li>
            ) : (
              filtered.map((o, i) => (
                <li
                  key={`${o.value}-${i}`}
                  role="option"
                  aria-selected={i === highlight}
                  className={`combobox__option${i === highlight ? " combobox__option--active" : ""}`}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    commit(o);
                  }}
                  onMouseEnter={() => setHighlight(i)}
                >
                  <span className="combobox__label">{o.label}</span>
                  {o.description ? <span className="combobox__desc">{o.description}</span> : null}
                </li>
              ))
            )}
          </ul>
        ) : null}
      </div>
    </label>
  );
}