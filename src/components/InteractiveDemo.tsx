import { ChangeEvent, useEffect, useMemo, useState } from "react";
import { ImageUp, Power, Send } from "lucide-react";
import { useArgusWebSocket } from "../hooks/useArgusWebSocket";
import { SectionLabel } from "./SectionLabel";

export function InteractiveDemo() {
  const { connectionState, inferenceState, response, transcript, error, ask, connect, disconnect, url } = useArgusWebSocket();
  const [image, setImage] = useState<File | null>(null);
  const [question, setQuestion] = useState("What am I looking at?");
  const previewUrl = useMemo(() => (image ? URL.createObjectURL(image) : ""), [image]);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const handleImage = (event: ChangeEvent<HTMLInputElement>) => {
    setImage(event.target.files?.[0] ?? null);
  };

  return (
    <section id="demo" className="section-pad border-b hairline">
      <SectionLabel code="06 / Interactive Demo">ARGUS / Live Inference</SectionLabel>
      <div className="mt-12 grid gap-8 lg:grid-cols-[0.76fr_1.24fr]">
        <div>
          <h2 className="headline-type">Ask ARGUS what you see.</h2>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <button className="industrial-button" data-variant="dark" onClick={connect}>
              <Power size={15} /> Connect
            </button>
            <button className="industrial-button" data-variant="light" onClick={disconnect}>
              Disconnect
            </button>
          </div>
          <p className="mt-5 font-mono text-xs uppercase text-argus-muted">{url}</p>
        </div>
        <div className="border border-black/15 bg-[#eeebe4]">
          <div className="eyebrow flex items-center justify-between border-b hairline p-4 text-argus-muted">
            <span>ARGUS / LIVE INFERENCE</span>
            <span>{connectionState} · {inferenceState}</span>
          </div>
          <label className="image-placeholder flex aspect-[16/10] cursor-pointer items-center justify-center">
            {previewUrl ? (
              <img src={previewUrl} alt="Uploaded camera frame" className="h-full w-full object-cover" />
            ) : (
              <span className="eyebrow flex items-center gap-2 text-argus-muted">
                <ImageUp size={18} /> Drop an image or capture a frame
              </span>
            )}
            <input className="sr-only" type="file" accept="image/png,image/jpeg,image/webp" onChange={handleImage} />
          </label>
          <div className="grid gap-3 border-t hairline p-4 md:grid-cols-[1fr_auto]">
            <input
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="What am I looking at?"
              className="min-h-12 border border-black/15 bg-argus-paper px-4 outline-none focus:border-black"
            />
            <button className="industrial-button" data-variant="dark" onClick={() => ask(question, image)} disabled={!question.trim()}>
              <Send size={15} /> Ask ARGUS
            </button>
          </div>
          <div className="min-h-48 border-t hairline p-4">
            <div className="eyebrow mb-5 text-argus-muted">ARGUS Response</div>
            {transcript && <p className="mb-4 font-mono text-xs uppercase text-argus-muted">Transcript: {transcript}</p>}
            <p className="text-xl leading-8">{error || response || "Thinking through the frame..."}</p>
          </div>
        </div>
      </div>
    </section>
  );
}
