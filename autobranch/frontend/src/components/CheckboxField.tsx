import type { InputHTMLAttributes, ReactNode } from "react";

type CheckboxFieldProps = {
  label: ReactNode;
} & Omit<InputHTMLAttributes<HTMLInputElement>, "type">;

export function CheckboxField({ label, className, ...rest }: CheckboxFieldProps) {
  return (
    <label className={`checkbox-field${className ? ` ${className}` : ""}`}>
      <input type="checkbox" {...rest} />
      <span>{label}</span>
    </label>
  );
}
