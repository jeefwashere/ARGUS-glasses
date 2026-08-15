import type { ReactNode } from "react";

type SectionLabelProps = {
  code: string;
  children: ReactNode;
};

export function SectionLabel({ code, children }: SectionLabelProps) {
  return (
    <div className="eyebrow flex items-center justify-between border-t hairline pt-4 text-argus-muted">
      <span>{code}</span>
      <span>{children}</span>
    </div>
  );
}
