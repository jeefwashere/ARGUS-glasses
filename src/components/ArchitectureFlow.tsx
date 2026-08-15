import { motion } from "framer-motion";
import { SectionLabel } from "./SectionLabel";

const nodes = ["Camera / Voice", "Deepgram", "Backboard AI", "ElevenLabs", "Voice + Display"];

export function ArchitectureFlow() {
  return (
    <section id="works" className="section-pad border-b hairline">
      <SectionLabel code="04 / How ARGUS Works">Signal chain</SectionLabel>
      <div className="mt-12 grid gap-10 lg:grid-cols-[0.75fr_1.25fr]">
        <div>
          <h2 className="headline-type">From perception to response.</h2>
          <p className="mt-7 max-w-xl text-lg leading-8 text-argus-muted">
            A compact chain of sensory capture, speech recognition, agent reasoning, and voice synthesis designed to disappear into a natural interaction.
          </p>
        </div>
        <motion.div
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-20% 0px" }}
          className="grid grid-cols-1 border-y hairline md:grid-cols-[repeat(5,minmax(0,1fr))]"
        >
          {nodes.map((node, index) => (
            <div key={node} className="relative min-h-40 border-b hairline p-5 md:border-b-0 md:border-r md:border-black/15">
              <motion.div
                className="absolute left-0 top-0 h-[2px] bg-argus-ink md:h-full md:w-[2px]"
                variants={{ hidden: { scaleX: 0, scaleY: 0 }, visible: { scaleX: 1, scaleY: 1 } }}
                transition={{ duration: 0.65, delay: index * 0.14, ease: "easeOut" }}
                style={{ transformOrigin: "left top" }}
              />
              <span className="eyebrow text-argus-muted">{String(index + 1).padStart(2, "0")}</span>
              <h3 className="mt-16 font-mono text-xl font-semibold uppercase leading-tight">{node}</h3>
            </div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
