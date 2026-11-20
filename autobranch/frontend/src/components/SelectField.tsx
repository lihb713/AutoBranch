import type { ReactNode, SelectHTMLAttributes } from "react";

type SelectFieldProps = {
  label: string;
  children: ReactNode;
} & SelectHTMLAttributes<HTMLSelectElement>;

export function SelectField({ label, children, className, ...rest }: SelectFieldProps) {
  return (
    <label className="text-field">
      <span className="text-field__label">{label}</span>
      <select className={`text-field__input${className ? ` ${className}` : ""}`} {...rest}>
        {children}
      </select>
    </label>
  );
}
