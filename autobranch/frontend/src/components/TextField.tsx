import type { InputHTMLAttributes } from "react";

type TextFieldProps = {
  label: string;
} & InputHTMLAttributes<HTMLInputElement>;

export function TextField({ label, className, ...rest }: TextFieldProps) {
  return (
    <label className="text-field">
      <span className="text-field__label">{label}</span>
      <input className={`text-field__input${className ? ` ${className}` : ""}`} {...rest} />
    </label>
  );
}