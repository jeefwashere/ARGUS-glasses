import { SectionLabel } from "./SectionLabel";

const reasons = [
  ["01", "Attachable", "Works with existing glasses - your frames, upgraded."],
  ["02", "Affordable", "A prototype built from accessible, replaceable hardware."],
  ["03", "Multimodal", "Vision, voice, and a display working as one interface."],
  ["04", "AI-powered", "Understands questions about the world in front of you."],
] as const;

export function WhyArgus() {
  return (
    <section className="section-pad border-b hairline">
      <SectionLabel code="07 / Why ARGUS">Positioning</SectionLabel>
      <h2 className="headline-type mt-12 max-w-6xl">Not another pair of glasses.</h2>
      <div className="mt-16 grid grid-cols-1 border-t hairline md:grid-cols-2">
        {reasons.map(([number, title, body]) => (
          <article key={number} className="min-h-72 border-b hairline p-6 md:border-r md:border-black/15">
            <span className="font-mono text-sm text-argus-muted">{number}</span>
            <h3 className="mt-16 text-4xl font-black uppercase md:text-6xl">{title}</h3>
            <p className="mt-5 max-w-md text-lg leading-8 text-argus-muted">{body}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
