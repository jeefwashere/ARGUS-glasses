import { SectionLabel } from "./SectionLabel";

const items = [
  ["ESP32-CAM / Vision Board", "Embedded capture and control.", "md:col-span-2"],
  ["Optical Display", "Information in your line of sight.", ""],
  ["3D-Printed Enclosure", "Designed for the real world.", ""],
  ["Glasses Mounting System", "The frames stay yours.", "md:col-span-2"],
] as const;

export function PhysicalHardware() {
  return (
    <section className="section-pad border-b hairline">
      <SectionLabel code="05 / Physical Hardware">Prototype materials</SectionLabel>
      <div className="mt-12 flex flex-col gap-8">
        <div className="max-w-5xl">
          <h2 className="headline-type">Built to clip in. Built to go out.</h2>
        </div>
        <div className="grid auto-rows-[minmax(360px,auto)] grid-cols-1 gap-4 md:grid-cols-4">
          {items.map(([title, body, span]) => (
            <article key={title} className={`image-placeholder ${span} flex min-h-80 flex-col justify-end p-5`}>
              <span className="eyebrow mb-auto text-argus-muted">Replace with product photo</span>
              <h3 className="font-mono text-2xl font-semibold uppercase leading-tight">{title}</h3>
              <p className="mt-2 text-argus-muted">{body}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
