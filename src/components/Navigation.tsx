import { ArrowUpRight } from "lucide-react";

const navItems = ["Product", "Modes", "Hardware", "Demo"];

export function Navigation() {
  return (
    <header className="fixed left-0 right-0 top-0 z-50 border-b hairline bg-argus-paper/80 px-[var(--page-pad)] py-3 backdrop-blur-md">
      <nav className="mx-auto flex max-w-[1800px] items-center justify-between">
        <a href="#top" className="eyebrow text-argus-ink">
          ARGUS / 01
        </a>
        <div className="hidden items-center gap-7 md:flex">
          {navItems.map((item) => (
            <a key={item} href={`#${item.toLowerCase()}`} className="eyebrow text-argus-muted transition hover:text-argus-ink">
              {item}
            </a>
          ))}
        </div>
        <a href="#demo" className="eyebrow inline-flex items-center gap-1 text-argus-ink">
          Live demo <ArrowUpRight size={14} strokeWidth={1.6} />
        </a>
      </nav>
    </header>
  );
}
