import { motion, useReducedMotion, useScroll, useTransform } from "framer-motion";
import { ArrowDown, Play } from "lucide-react";
import { lazy, Suspense, useRef } from "react";

const ArgusProductScene = lazy(() =>
  import("./ArgusProductScene").then((module) => ({ default: module.ArgusProductScene })),
);

export function Hero() {
  const ref = useRef<HTMLElement>(null);
  const reducedMotion = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end start"] });
  const copyOpacity = useTransform(scrollYProgress, [0, 0.72], [1, reducedMotion ? 1 : 0.38]);
  const copyY = useTransform(scrollYProgress, [0, 1], [0, reducedMotion ? 0 : -54]);

  return (
    <section id="top" ref={ref} className="relative min-h-[150vh] border-b hairline">
      <div className="sticky top-0 flex min-h-screen items-center overflow-hidden px-[var(--page-pad)] pt-16">
        <motion.div style={{ opacity: copyOpacity, y: copyY }} className="relative z-10 grid w-full grid-cols-1 gap-8 lg:grid-cols-[0.95fr_1.05fr]">
          <div className="flex min-h-[72vh] max-w-5xl flex-col justify-between py-8">
            <div>
              <div className="eyebrow mb-8 flex max-w-md justify-between border-t hairline pt-4 text-argus-muted">
                <span>ARGUS / 01</span>
                <span>Hardware intelligence</span>
              </div>
              <h1 className="display-type max-w-6xl">
                AN AI MODULE
                <br />
                FOR EVERYDAY VISION
              </h1>
            </div>
            <div className="max-w-xl">
              <p className="mb-4 text-xl font-semibold md:text-3xl">AI for the glasses you already own.</p>
              <p className="mb-8 max-w-lg text-base leading-7 text-argus-muted md:text-lg">
                ARGUS attaches vision, voice, translation, and real-time AI assistance to the frames already in your life.
              </p>
              <div className="flex flex-wrap gap-3">
                <a href="#demo" className="industrial-button" data-variant="dark">
                  <Play size={15} /> Watch demo
                </a>
                <a href="#works" className="industrial-button" data-variant="light">
                  How it works <ArrowDown size={15} />
                </a>
              </div>
            </div>
          </div>
        </motion.div>
        <Suspense fallback={<div className="pointer-events-none absolute inset-y-16 right-[-16vw] z-0 w-[115vw] md:right-[-10vw] md:w-[88vw] lg:right-[-6vw] lg:w-[64vw]" />}>
          <ArgusProductScene
            progress={scrollYProgress}
            className="pointer-events-none absolute inset-y-16 right-[-16vw] z-0 w-[115vw] md:right-[-10vw] md:w-[88vw] lg:right-[-6vw] lg:w-[64vw]"
            config={{ initialScale: 1.32, finalScale: 0.78, xMovement: 1.2, yMovement: -0.1, rotation: 0.92 }}
          />
        </Suspense>
      </div>
    </section>
  );
}
