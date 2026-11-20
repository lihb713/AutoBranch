import type { TextareaHTMLAttributes } from "react";

type TextAreaFieldProps = {
  label: string;
} & TextareaHTMLAttributes<HTMLTextAreaElement>;

export function TextAreaField({ label, className, ...rest }: TextAreaFieldProps) {
  return (
    <label className="text-field">
      <span className="text-field__label">{label}</span>
      <textarea
        className={`text-field__input${className ? ` ${className}` : ""}`}
        {...rest}
      />
    </label>
  );
}
