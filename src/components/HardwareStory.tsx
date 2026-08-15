import { Reveal } from "./Reveal";
import { SectionLabel } from "./SectionLabel";

const hardware = [
  ["01 / VISION", "See what you see.", "A forward-facing camera gives ARGUS visual context."],
  ["02 / COMPUTE", "Small hardware. A much larger capability.", "Compact onboard hardware connects the physical world to ARGUS intelligence."],
  ["03 / DISPLAY", "Information in your line of sight.", "A compact display brings useful information directly into view."],
  ["04 / SYSTEM", "Built from simple parts.", "Camera. Compute. Display. Enclosure. One wearable system."],
] as const;

export function HardwareStory() {
  return (
    <section id="hardware" className="section-pad border-b hairline">
      <SectionLabel code="ARGUS / Hardware">Built to clip in</SectionLabel>
      <div className="mt-12 grid gap-5 lg:grid-cols-[0.92fr_1.08fr]">
        <div>
          <h2 className="headline-type">Built to clip in.</h2>
          <p className="mt-6 text-2xl font-semibold">AI for the glasses you already own.</p>
        </div>
        <div className="space-y-20">
          {hardware.map(([label, title, body], index) => (
            <Reveal key={label}>
              <article className={`grid gap-8 md:grid-cols-2 ${index % 2 ? "md:[&>*:first-child]:order-2" : ""}`}>
                <div className="image-placeholder aspect-[4/3] min-h-72">
                  <span className="eyebrow absolute bottom-4 left-4 text-argus-muted">Product image placeholder</span>
                </div>
                <div className="flex flex-col justify-between border-t hairline py-5">
                  <span className="eyebrow text-argus-muted">{label}</span>
                  <div>
                    <h3 className="text-4xl font-black leading-none md:text-6xl">{title}</h3>
                    <p className="mt-5 text-lg leading-8 text-argus-muted">{body}</p>
                  </div>
                </div>
              </article>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
