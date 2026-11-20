import type { HTMLAttributes, ReactNode } from "react";

export type BadgeTone = "neutral" | "primary" | "success" | "failure" | "warning";

type BadgeProps = {
  tone?: BadgeTone;
  children: ReactNode;
} & HTMLAttributes<HTMLSpanElement>;

export function Badge({
  tone = "neutral",
  children,
  className,
  ...rest
}: BadgeProps) {
  return (
    <span className={`badge badge-${tone}${className ? ` ${className}` : ""}`} {...rest}>
      {children}
    </span>
  );
}
