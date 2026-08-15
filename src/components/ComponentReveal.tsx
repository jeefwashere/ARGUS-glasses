import { motion, useReducedMotion, useScroll, useTransform } from "framer-motion";
import { useRef } from "react";
import { Cpu, Eye, Mic, ScanEye, Server } from "lucide-react";
import { SectionLabel } from "./SectionLabel";

const parts = [
  { id: "01", title: "Camera", icon: ScanEye, x: [-20, -210], y: [-8, -92] },
  { id: "02", title: "Optical display", icon: Eye, x: [18, 230], y: [0, -80] },
  { id: "03", title: "ESP32", icon: Cpu, x: [-8, -160], y: [6, 112] },
  { id: "04", title: "Audio", icon: Mic, x: [10, 175], y: [8, 118] },
  { id: "05", title: "AI backend", icon: Server, x: [0, 0], y: [12, 186] },
];

type RevealPartProps = {
  part: (typeof parts)[number];
  progress: ReturnType<typeof useScroll>["scrollYProgress"];
  reducedMotion: boolean | null;
};

function RevealPart({ part, progress, reducedMotion }: RevealPartProps) {
  const x = useTransform(progress, [0.12, 0.82], reducedMotion ? [part.x[1], part.x[1]] : part.x);
  const y = useTransform(progress, [0.12, 0.82], reducedMotion ? [part.y[1], part.y[1]] : part.y);
  const Icon = part.icon;

  return (
    <motion.div
      style={{ x, y }}
      className="absolute left-1/2 top-1/2 flex w-48 -translate-x-1/2 -translate-y-1/2 items-center gap-3 border border-black/15 bg-argus-paper/90 p-3 backdrop-blur"
    >
      <Icon size={18} strokeWidth={1.5} />
      <div>
        <div className="font-mono text-[10px] text-argus-muted">{part.id}</div>
        <div className="text-sm font-semibold uppercase">{part.title}</div>
      </div>
    </motion.div>
  );
}

export function ComponentReveal() {
  const ref = useRef<HTMLElement>(null);
  const reducedMotion = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });

  return (
    <section id="product" ref={ref} className="section-pad min-h-[150vh] border-b hairline">
      <SectionLabel code="02 / Component Reveal">Exploded system</SectionLabel>
      <div className="sticky top-20 mt-12 grid min-h-[76vh] grid-cols-1 gap-10 lg:grid-cols-[0.9fr_1.1fr]">
        <div className="self-center">
          <h2 className="headline-type max-w-4xl">A small module. A much larger world.</h2>
          <p className="mt-8 max-w-lg text-lg leading-8 text-argus-muted">
            The frame stays familiar. The intelligence arrives as a compact clip-in stack: optics, sensing, compute, audio, and cloud reasoning.
          </p>
        </div>
        <div className="relative min-h-[520px] overflow-hidden border-l hairline">
          <div className="absolute inset-8 md:inset-14">
            <div className="absolute left-1/2 top-1/2 h-24 w-[58%] -translate-x-1/2 -translate-y-1/2 border-y border-black/35" />
            <div className="absolute left-[20%] top-1/2 h-28 w-28 -translate-y-1/2 rounded-full border border-black/40 bg-white/30" />
            <div className="absolute right-[20%] top-1/2 h-28 w-28 -translate-y-1/2 rounded-full border border-black/40 bg-white/30" />
            {parts.map((part) => (
              <RevealPart key={part.id} part={part} progress={scrollYProgress} reducedMotion={reducedMotion} />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
