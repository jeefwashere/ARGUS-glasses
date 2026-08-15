const elements = {
  audioInput: document.querySelector("#audio-input"),
  enableMicrophone: document.querySelector("#enable-microphone"),
  refreshDevices: document.querySelector("#refresh-devices"),
  startListening: document.querySelector("#start-listening"),
  stopListening: document.querySelector("#stop-listening"),
  permissionState: document.querySelector("#permission-state"),
  connectionState: document.querySelector("#connection-state"),
  websocketUrl: document.querySelector("#websocket-url"),
  statusMessage: document.querySelector("#status-message"),
  transcript: document.querySelector("#transcript"),
  answer: document.querySelector("#answer"),
  meterFill: document.querySelector("#meter-fill"),
  errorPanel: document.querySelector("#error-panel"),
  errorMessage: document.querySelector("#error-message"),
};

const websocketProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
const websocketUrl = `${websocketProtocol}//${window.location.host}/ask`;
const ESP32_BASE_URL = (globalThis.ARGUS_ESP32_BASE_URL || "http://10.0.0.97").replace(/\/$/, "");
const ESP32_DISPLAY_TIMEOUT_MS = 10000;
const ESP32_AUDIO_TIMEOUT_MS = 120000;
elements.websocketUrl.textContent = websocketUrl;

let socket = null;
let socketPromise = null;
let microphoneStream = null;
let recordingContext = null;
let playbackContext = null;
let sourceNode = null;
let workletNode = null;
let silentGain = null;
let isRecording = false;
let receivingTtsAudio = false;
let responseAudioFormat = null;
let expectingEsp32Audio = false;
let nextPlaybackTime = 0;

function setStatus(message) {
  elements.statusMessage.textContent = message;
}

function showError(message) {
  elements.errorMessage.textContent = message;
  elements.errorPanel.hidden = false;
}

function clearError() {
  elements.errorPanel.hidden = true;
  elements.errorMessage.textContent = "";
}

async function postToEsp32(path, body, contentType, timeoutMs, failureMessage) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${ESP32_BASE_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": contentType },
      body,
      signal: controller.signal,
    });

    if (!response.ok) {
      const responseBody = await response.text().catch(() => "");
      console.error(`${failureMessage}: HTTP ${response.status}${responseBody ? ` — ${responseBody}` : ""}`);
    }
  } catch (error) {
    const detail = error?.name === "AbortError" ? "request timed out" : error?.message || String(error);
    console.error(`${failureMessage}: ${detail}`);
  } finally {
    window.clearTimeout(timeout);
  }
}

function forwardDisplayToEsp32(answerText) {
  if (!answerText) return Promise.resolve();
  return postToEsp32(
    "/display",
    answerText,
    "text/plain; charset=utf-8",
    ESP32_DISPLAY_TIMEOUT_MS,
    "Failed to send display text to ESP32",
  );
}

function forwardAudioToEsp32(wavBytes) {
  return postToEsp32(
    "/audio",
    wavBytes,
    "text/plain",
    ESP32_AUDIO_TIMEOUT_MS,
    "Failed to send audio to ESP32",
  );
}

function setTextResult(element, text) {
  element.textContent = text;
  element.classList.toggle("muted", !text);
}

function readableMicrophoneError(error) {
  if (error && error.name === "NotAllowedError") {
    return "Microphone permission was denied. Allow microphone access in the browser and try again.";
  }

  if (error && error.name === "NotFoundError") {
    return "No microphone was found. Connect AirPods or choose another computer microphone.";
  }

  if (error && error.name === "NotReadableError") {
    return "The microphone is busy in another application. Close the other application and try again.";
  }

  return error && error.message
    ? error.message
    : "The microphone could not be opened.";
}

async function enableMicrophoneAccess() {
  clearError();

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    showError("This browser does not provide microphone access. Open this page in a current version of Chrome.");
    return;
  }

  try {
    const permissionStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    permissionStream.getTracks().forEach((track) => track.stop());

    await refreshAudioInputs();
    elements.permissionState.textContent = "Permission granted";
    elements.permissionState.classList.add("live");
    elements.refreshDevices.disabled = false;
    elements.startListening.disabled = elements.audioInput.options.length === 0;
    setStatus("Choose the AirPods microphone, then start listening.");
  } catch (error) {
    showError(readableMicrophoneError(error));
  }
}

async function refreshAudioInputs() {
  const previousValue = elements.audioInput.value;
  const devices = await navigator.mediaDevices.enumerateDevices();
  const inputs = devices.filter((device) => device.kind === "audioinput");

  elements.audioInput.replaceChildren();

  inputs.forEach((device, index) => {
    const option = document.createElement("option");
    option.value = device.deviceId;
    option.textContent = device.label || `Microphone ${index + 1}`;
    elements.audioInput.append(option);
  });

  elements.audioInput.disabled = inputs.length === 0;
  elements.startListening.disabled = inputs.length === 0 || isRecording;

  if (inputs.some((device) => device.deviceId === previousValue)) {
    elements.audioInput.value = previousValue;
  } else {
    const airpodsInput = inputs.find((device) =>
      device.label.toLowerCase().includes("airpods"),
    );

    if (airpodsInput) {
      elements.audioInput.value = airpodsInput.deviceId;
    }
  }

  if (inputs.length === 0) {
    setStatus("No microphone input is available.");
  }
}

function updateSocketState(text, live = false) {
  elements.connectionState.textContent = text;
  elements.connectionState.classList.toggle("live", live);
}

function connectWebSocket() {
  if (socket && socket.readyState === WebSocket.OPEN) {
    return Promise.resolve(socket);
  }

  if (socketPromise) {
    return socketPromise;
  }

  updateSocketState("Connecting");

  socketPromise = new Promise((resolve, reject) => {
    const candidate = new WebSocket(websocketUrl);
    candidate.binaryType = "arraybuffer";
    let connectionOpened = false;

    candidate.addEventListener("open", () => {
      connectionOpened = true;
      socket = candidate;
      socketPromise = null;
      updateSocketState("Connected", true);
      resolve(candidate);
    });

    candidate.addEventListener("message", (event) => {
      handleSocketMessage(event).catch((error) => {
        showError(error.message || "The response audio could not be played.");
      });
    });

    candidate.addEventListener("error", () => {
      socketPromise = null;
      updateSocketState("Connection failed");
      reject(new Error("The WebSocket connection failed. Confirm that the backend is running and API keys are configured."));
    });

    candidate.addEventListener("close", () => {
      if (!connectionOpened) {
        reject(new Error("The backend closed the WebSocket before the session started."));
      }

      if (socket === candidate) {
        socket = null;
      }
      socketPromise = null;
      receivingTtsAudio = false;
      responseAudioFormat = null;
      expectingEsp32Audio = false;
      updateSocketState("Disconnected");

      if (isRecording) {
        stopListening("The backend connection closed.");
      }
    });
  });

  return socketPromise;
}

async function handleSocketMessage(event) {
  if (typeof event.data !== "string") {
    if (expectingEsp32Audio && event.data instanceof ArrayBuffer) {
      expectingEsp32Audio = false;
      void forwardAudioToEsp32(event.data);
    }
    if (responseAudioFormat === "pcm_16000" && event.data instanceof ArrayBuffer) {
      await playPcm16(event.data);
    }
    return;
  }

  let message;
  try {
    message = JSON.parse(event.data);
  } catch {
    showError("The backend returned a text message that was not valid JSON.");
    return;
  }

  if (message.type === "transcript") {
    setTextResult(elements.transcript, message.text || "");
    setStatus("Speech recognized. ARGUS is preparing an answer.");
    return;
  }

  if (message.type === "wake_detected") {
    setTextResult(elements.transcript, message.text || "Hi Spider");
    setStatus("Hi Spider detected. Ask your question within ten seconds.");
    return;
  }

  if (message.type === "wake_ignored") {
    setTextResult(elements.transcript, message.text || "");
    setStatus("No reply was requested. Begin with Hi Spider.");
    return;
  }

  if (message.type === "answer") {
    setTextResult(elements.answer, message.text || "");
    void forwardDisplayToEsp32(message.text);
    setStatus("Answer received. You can continue with another question.");
    return;
  }

  if (message.type === "audio_start") {
    responseAudioFormat = message.audio_format || null;
    receivingTtsAudio = responseAudioFormat === "pcm_16000" || responseAudioFormat === "wav_16000_mono";
    expectingEsp32Audio = responseAudioFormat === "wav_16000_mono";
    if (!receivingTtsAudio) {
      showError(`Unsupported response audio format: ${message.audio_format || "unknown"}`);
    }
    return;
  }

  if (message.type === "audio_end") {
    receivingTtsAudio = false;
    responseAudioFormat = null;
    expectingEsp32Audio = false;
    return;
  }

  if (message.type === "audio_error" || message.type === "error") {
    receivingTtsAudio = false;
    responseAudioFormat = null;
    expectingEsp32Audio = false;
    showError(message.message || "The backend reported an error.");
  }
}

async function ensurePlaybackContext() {
  if (!playbackContext || playbackContext.state === "closed") {
    playbackContext = new AudioContext();
    nextPlaybackTime = 0;
  }

  if (playbackContext.state === "suspended") {
    await playbackContext.resume();
  }

  return playbackContext;
}

async function playPcm16(arrayBuffer) {
  const context = await ensurePlaybackContext();
  const sourceSamples = new Int16Array(arrayBuffer);
  const audioBuffer = context.createBuffer(1, sourceSamples.length, 16000);
  const channel = audioBuffer.getChannelData(0);

  for (let index = 0; index < sourceSamples.length; index += 1) {
    channel[index] = sourceSamples[index] / 0x8000;
  }

  const source = context.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(context.destination);

  const startAt = Math.max(context.currentTime, nextPlaybackTime);
  source.start(startAt);
  nextPlaybackTime = startAt + audioBuffer.duration;
}

function selectedDeviceConstraints() {
  const deviceId = elements.audioInput.value;
  const audio = {
    channelCount: { ideal: 1 },
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  };

  if (deviceId) {
    audio.deviceId = { exact: deviceId };
  }

  return { audio };
}

function responseAudioIsPlaying() {
  return Boolean(
    playbackContext &&
    playbackContext.state !== "closed" &&
    playbackContext.currentTime < nextPlaybackTime + 0.1,
  );
}

async function startListening() {
  clearError();
  elements.startListening.disabled = true;

  try {
    await connectWebSocket();
    await ensurePlaybackContext();

    microphoneStream = await navigator.mediaDevices.getUserMedia(
      selectedDeviceConstraints(),
    );
    recordingContext = new AudioContext();
    await recordingContext.audioWorklet.addModule("/static/pcm-worklet.js");
    await recordingContext.resume();

    sourceNode = recordingContext.createMediaStreamSource(microphoneStream);
    workletNode = new AudioWorkletNode(recordingContext, "pcm16-downsampler", {
      numberOfInputs: 1,
      numberOfOutputs: 1,
      outputChannelCount: [1],
      processorOptions: {
        targetSampleRate: 16000,
        chunkSamples: 320,
      },
    });
    silentGain = recordingContext.createGain();
    silentGain.gain.value = 0;

    workletNode.port.onmessage = (event) => {
      if (
        isRecording &&
        !receivingTtsAudio &&
        !responseAudioIsPlaying() &&
        socket &&
        socket.readyState === WebSocket.OPEN
      ) {
        socket.send(event.data);
      }
    };

    sourceNode.connect(workletNode);
    workletNode.connect(silentGain);
    silentGain.connect(recordingContext.destination);

    isRecording = true;
    elements.stopListening.disabled = false;
    elements.audioInput.disabled = true;
    elements.refreshDevices.disabled = true;
    elements.meterFill.style.width = "100%";
    setStatus("Listening. Say Hi Spider, ask your question, then pause for the answer.");
  } catch (error) {
    await releaseMicrophoneResources();
    elements.startListening.disabled = elements.audioInput.options.length === 0;
    showError(readableMicrophoneError(error));
  }
}

async function releaseMicrophoneResources() {
  isRecording = false;
  elements.meterFill.style.width = "2%";

  if (workletNode) {
    workletNode.port.onmessage = null;
    workletNode.disconnect();
    workletNode = null;
  }

  if (sourceNode) {
    sourceNode.disconnect();
    sourceNode = null;
  }

  if (silentGain) {
    silentGain.disconnect();
    silentGain = null;
  }

  if (microphoneStream) {
    microphoneStream.getTracks().forEach((track) => track.stop());
    microphoneStream = null;
  }

  if (recordingContext && recordingContext.state !== "closed") {
    await recordingContext.close();
  }
  recordingContext = null;
}

async function stopListening(message = "Listening stopped. Start again when you are ready.") {
  await releaseMicrophoneResources();
  elements.stopListening.disabled = true;
  elements.audioInput.disabled = false;
  elements.refreshDevices.disabled = false;
  elements.startListening.disabled = elements.audioInput.options.length === 0;
  setStatus(message);
}

elements.enableMicrophone.addEventListener("click", enableMicrophoneAccess);
elements.refreshDevices.addEventListener("click", async () => {
  clearError();
  try {
    await refreshAudioInputs();
  } catch (error) {
    showError(readableMicrophoneError(error));
  }
});
elements.startListening.addEventListener("click", startListening);
elements.stopListening.addEventListener("click", () => stopListening());

if (navigator.mediaDevices) {
  navigator.mediaDevices.addEventListener("devicechange", () => {
    if (!isRecording && !elements.refreshDevices.disabled) {
      refreshAudioInputs().catch((error) => showError(readableMicrophoneError(error)));
    }
  });
}

window.addEventListener("beforeunload", () => {
  microphoneStream?.getTracks().forEach((track) => track.stop());
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: "close" }));
  }
});
