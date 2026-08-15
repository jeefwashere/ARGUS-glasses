import { useCallback, useEffect, useMemo, useRef, useState } from "react";

export const ARGUS_WS_URL = import.meta.env.VITE_ARGUS_WS_URL ?? "ws://127.0.0.1:8000/ask";

type ConnectionState = "disconnected" | "connecting" | "connected" | "error";
type InferenceState = "idle" | "uploading" | "thinking" | "responding";

type ServerMessage =
  | { type: "answer"; text: string; thread_id?: string }
  | { type: "transcript"; text: string }
  | { type: "thread_set"; thread_id: string }
  | { type: "image_started" | "image_received" | "audio_start" | "audio_end" }
  | { type: "error" | "audio_error"; message: string };

export function useArgusWebSocket(url = ARGUS_WS_URL) {
  const socketRef = useRef<WebSocket | null>(null);
  const [connectionState, setConnectionState] = useState<ConnectionState>("disconnected");
  const [inferenceState, setInferenceState] = useState<InferenceState>("idle");
  const [response, setResponse] = useState("ARGUS standby. Upload an image and ask a question.");
  const [transcript, setTranscript] = useState("");
  const [error, setError] = useState("");
  const [threadId, setThreadId] = useState<string | null>(null);

  const connect = useCallback(() => {
    if (socketRef.current?.readyState === WebSocket.OPEN || socketRef.current?.readyState === WebSocket.CONNECTING) {
      return;
    }

    setConnectionState("connecting");
    setError("");
    const socket = new WebSocket(url);
    socket.binaryType = "arraybuffer";
    socketRef.current = socket;

    socket.onopen = () => setConnectionState("connected");
    socket.onclose = () => {
      setConnectionState("disconnected");
      setInferenceState("idle");
    };
    socket.onerror = () => {
      setConnectionState("error");
      setError("Unable to reach ARGUS backend.");
    };
    socket.onmessage = (event) => {
      if (typeof event.data !== "string") return;
      const message = JSON.parse(event.data) as ServerMessage;

      if (message.type === "answer") {
        setResponse(message.text);
        setThreadId(message.thread_id ?? null);
        setInferenceState("responding");
        window.setTimeout(() => setInferenceState("idle"), 800);
      }

      if (message.type === "transcript") setTranscript(message.text);
      if (message.type === "image_received") setInferenceState("thinking");
      if (message.type === "error" || message.type === "audio_error") {
        setError(message.message);
        setInferenceState("idle");
      }
    };
  }, [url]);

  const disconnect = useCallback(() => {
    socketRef.current?.send(JSON.stringify({ type: "close" }));
    socketRef.current?.close();
    socketRef.current = null;
  }, []);

  const ask = useCallback(
    async (question: string, image?: File | null) => {
      connect();
      const socket = socketRef.current;
      if (!socket) return;

      await new Promise<void>((resolve, reject) => {
        if (socket.readyState === WebSocket.OPEN) {
          resolve();
          return;
        }
        socket.addEventListener("open", () => resolve(), { once: true });
        socket.addEventListener("error", () => reject(new Error("WebSocket connection failed")), { once: true });
      });

      setResponse("");
      setError("");
      setTranscript("");
      setInferenceState(image ? "uploading" : "thinking");

      if (threadId) {
        socket.send(JSON.stringify({ type: "set_thread", thread_id: threadId }));
      }

      if (image) {
        socket.send(JSON.stringify({ type: "image_start", content_type: image.type }));
        socket.send(await image.arrayBuffer());
        socket.send(JSON.stringify({ type: "image_end" }));
      }

      socket.send(JSON.stringify({ type: "question", text: question }));
    },
    [connect, threadId],
  );

  useEffect(() => () => disconnect(), [disconnect]);

  return useMemo(
    () => ({ connectionState, inferenceState, response, transcript, error, ask, connect, disconnect, url }),
    [ask, connect, connectionState, disconnect, error, inferenceState, response, transcript, url],
  );
}
