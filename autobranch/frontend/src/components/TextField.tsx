import type { InputHTMLAttributes } from "react";

type TextFieldProps = {
  label?: string;
} & InputHTMLAttributes<HTMLInputElement>;

export function TextField({ label, className, ...rest }: TextFieldProps) {
  return (
    <label className="text-field">
      {label ? <span className="text-field__label">{label}</span> : null}
      <input className={`text-field__input${className ? ` ${className}` : ""}`} {...rest} />
    </label>
  );
}