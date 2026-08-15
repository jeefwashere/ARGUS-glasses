import { ArrowUpRight, Github, Play } from "lucide-react";

export function Footer() {
  return (
    <footer className="section-pad min-h-screen">
      <div className="eyebrow flex justify-between border-t hairline pt-4 text-argus-muted">
        <span>ARGUS / Intelligence in motion</span>
        <span>Prototype 2026</span>
      </div>
      <div className="flex min-h-[68vh] flex-col justify-center">
        <h2 className="display-type">Intelligence. Attached.</h2>
        <p className="mt-8 max-w-2xl text-2xl font-semibold leading-tight md:text-4xl">
          See more. Understand faster. Keep your world in view.
        </p>
        <div className="mt-10 flex flex-wrap gap-3">
          <a className="industrial-button" data-variant="dark" href="https://github.com/" target="_blank" rel="noreferrer">
            <Github size={15} /> View GitHub
          </a>
          <a className="industrial-button" data-variant="light" href="#demo">
            <Play size={15} /> Watch demo
          </a>
        </div>
      </div>
      <div className="eyebrow flex flex-wrap items-center justify-between gap-3 border-t hairline pt-4 text-argus-muted">
        <span>ARGUS · ATTACHABLE AI · PROTOTYPE 2026</span>
        <a href="#top" className="inline-flex items-center gap-1 text-argus-ink">
          Return <ArrowUpRight size={14} />
        </a>
      </div>
    </footer>
  );
}
