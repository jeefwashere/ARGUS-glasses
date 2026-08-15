import { SectionLabel } from "./SectionLabel";

const stack = ["ESP32-CAM", "FastAPI", "Render", "Deepgram", "Backboard AI", "ElevenLabs"];

export function TechStack() {
  return (
    <section className="section-pad border-b hairline">
      <SectionLabel code="08 / Tech Stack">Engineering metadata</SectionLabel>
      <div className="mt-12 grid gap-8 lg:grid-cols-[0.72fr_1.28fr]">
        <h2 className="headline-type">Prototype stack.</h2>
        <div className="border-t hairline">
          {stack.map((item, index) => (
            <div key={item} className="grid grid-cols-[4rem_1fr] border-b hairline py-5 font-mono uppercase">
              <span className="text-argus-muted">{String(index + 1).padStart(2, "0")}</span>
              <span className="text-2xl font-semibold md:text-4xl">{item}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
