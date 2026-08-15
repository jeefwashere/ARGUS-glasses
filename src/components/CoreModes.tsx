import { Camera, Languages, MessageCircle } from "lucide-react";
import { Reveal } from "./Reveal";
import { SectionLabel } from "./SectionLabel";

const modes = [
  ["01 / SEE", "Ask what's in front of you.", "ARGUS turns a live camera frame into a conversation. Point, ask, understand.", Camera],
  ["02 / TRANSLATE", "Meaning, in the moment.", "Translate what you hear or see, then surface the essential response where it matters.", Languages],
  ["03 / ASK", "Speak naturally. Hear the answer.", "A hands-free interface that listens, thinks, and replies without breaking your stride.", MessageCircle],
] as const;

export function CoreModes() {
  return (
    <section id="modes" className="section-pad border-b hairline">
      <SectionLabel code="03 / Core Modes">Perception modes</SectionLabel>
      <div className="mt-12 space-y-6">
        {modes.map(([label, title, body, Icon], index) => (
          <Reveal key={label} delay={index * 0.08}>
            <article className="grid min-h-[420px] grid-cols-1 border-t hairline py-8 md:grid-cols-[0.72fr_1.28fr] md:py-12">
              <div className="eyebrow mb-8 flex items-start gap-4 text-argus-muted md:mb-0">
                <Icon size={18} strokeWidth={1.4} />
                {label}
              </div>
              <div className="grid gap-8 lg:grid-cols-[1fr_0.72fr]">
                <h3 className="mid-type">{title}</h3>
                <p className="self-end text-lg leading-8 text-argus-muted">{body}</p>
              </div>
            </article>
          </Reveal>
        ))}
      </div>
    </section>
  );
}
