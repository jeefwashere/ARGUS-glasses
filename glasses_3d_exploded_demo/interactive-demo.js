const elements = {
  endpoint: document.querySelector("#ask-endpoint"),
  connect: document.querySelector("#connect-argus"),
  connectionState: document.querySelector("#connection-state"),
  inferenceState: document.querySelector("#inference-state"),
  status: document.querySelector("#demo-status"),
  error: document.querySelector("#demo-error"),
  imageInput: document.querySelector("#image-input"),
  imageDropZone: document.querySelector("#image-drop-zone"),
  imagePreview: document.querySelector("#image-preview"),
  imagePlaceholder: document.querySelector("#image-placeholder"),
  clearImage: document.querySelector("#clear-image"),
  audioInput: document.querySelector("#audio-input"),
  enableMicrophone: document.querySelector("#enable-microphone"),
  toggleListening: document.querySelector("#toggle-listening"),
  microphoneState: document.querySelector("#microphone-state"),
  voiceMeter: document.querySelector("#voice-meter-fill"),
  questionForm: document.querySelector("#question-form"),
  questionText: document.querySelector("#question-text"),
  sendQuestion: document.querySelector("#send-question"),
  transcript: document.querySelector("#transcript"),
  answer: document.querySelector("#answer"),
  audioIndicator: document.querySelector("#audio-indicator"),
  audioState: document.querySelector("#audio-state"),
  promptSuggestions: document.querySelectorAll("[data-prompt]"),
};

let socket = null;
let socketPromise = null;
let selectedImage = null;
let imagePreviewUrl = "";
let imageUploaded = false;
let microphoneStream = null;
let recordingContext = null;
let sourceNode = null;
let workletNode = null;
let silentGain = null;
let isRecording = false;
let receivingTtsAudio = false;
let playbackContext = null;
let nextPlaybackTime = 0;
let threadId = sessionStorage.getItem("argus-thread-id");

function setStatus(message) {
  elements.status.textContent = message;
}

function setInference(state) {
  elements.inferenceState.textContent = state.toUpperCase();
  elements.inferenceState.dataset.state = state.toLowerCase();
}

function showError(message) {
  elements.error.textContent = message;
  elements.error.hidden = false;
  setInference("error");
}

function clearError() {
  elements.error.hidden = true;
  elements.error.textContent = "";
}

function updateConnection(label, live = false) {
  elements.connectionState.textContent = label;
  elements.connectionState.closest("div").classList.toggle("is-live", live);
  elements.connect.textContent = live ? "Disconnect" : "Connect";
  elements.endpoint.disabled = live;
}

function readableMicrophoneError(error) {
  if (error?.name === "NotAllowedError") {
    return "Microphone permission was denied. Allow access in the browser and try again.";
  }
  if (error?.name === "NotFoundError") {
    return "No microphone was found. Connect a microphone and refresh the device list.";
  }
  if (error?.name === "NotReadableError") {
    return "The microphone is already in use by another application.";
  }
  return error?.message || "The microphone could not be opened.";
}

function getEndpoint() {
  const endpoint = elements.endpoint.value.trim();
  if (!/^wss?:\/\//i.test(endpoint)) {
    throw new Error("The ask endpoint must begin with ws:// or wss://.");
  }
  return endpoint;
}

function connectWebSocket() {
  if (socket?.readyState === WebSocket.OPEN) {
    return Promise.resolve(socket);
  }
  if (socketPromise) return socketPromise;

  clearError();
  updateConnection("Connecting");
  setStatus("Opening a live connection to ARGUS.");

  socketPromise = new Promise((resolve, reject) => {
    let candidate;
    try {
      candidate = new WebSocket(getEndpoint());
    } catch (error) {
      socketPromise = null;
      reject(error);
      return;
    }

    candidate.binaryType = "arraybuffer";
    let opened = false;

    candidate.addEventListener("open", () => {
      opened = true;
      socket = candidate;
      socketPromise = null;
      updateConnection("Connected", true);
      setInference("ready");
      setStatus("ARGUS is connected. Add a frame, type a question, or start listening.");
      if (threadId) {
        candidate.send(JSON.stringify({ type: "set_thread", thread_id: threadId }));
      }
      resolve(candidate);
    });

    candidate.addEventListener("message", (event) => {
      handleSocketMessage(event).catch((error) => showError(error.message));
    });

    candidate.addEventListener("error", () => {
      socketPromise = null;
      updateConnection("Connection failed");
      reject(new Error("Could not reach the configured ARGUS WebSocket endpoint. Confirm the service is available and try again."));
    });

    candidate.addEventListener("close", () => {
      if (!opened) {
        reject(new Error("The ARGUS backend closed the connection before the session started."));
      }
      if (socket === candidate) socket = null;
      socketPromise = null;
      receivingTtsAudio = false;
      updateConnection("Disconnected");
      setInference("offline");
      if (isRecording) void stopListening("Listening stopped because the backend disconnected.");
    });
  });

  return socketPromise;
}

async function disconnectWebSocket() {
  if (isRecording) await stopListening("Listening stopped.");
  if (socket?.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: "close" }));
    socket.close();
  }
  socket = null;
  updateConnection("Disconnected");
  setInference("offline");
  setStatus("Session disconnected. Connect again to continue the same conversation.");
}

async function handleSocketMessage(event) {
  if (typeof event.data !== "string") {
    if (receivingTtsAudio && event.data instanceof ArrayBuffer) {
      await playPcm16(event.data);
    }
    return;
  }

  let message;
  try {
    message = JSON.parse(event.data);
  } catch {
    throw new Error("ARGUS returned an invalid text response.");
  }

  if (message.type === "thread_set") return;

  if (message.type === "image_started") {
    setStatus("Uploading the camera frame.");
    return;
  }

  if (message.type === "image_received") {
    setStatus("Camera frame received. ARGUS is waiting for or processing the question.");
    return;
  }

  if (message.type === "wake_detected") {
    elements.transcript.textContent = message.text || "Hi Spider";
    setInference("listening");
    setStatus("Wake phrase detected. Ask your question within ten seconds.");
    return;
  }

  if (message.type === "wake_ignored") {
    elements.transcript.textContent = message.text || "Speech detected";
    setInference("standby");
    setStatus("Speech was heard without the wake phrase. Begin with “Hi Spider.”");
    return;
  }

  if (message.type === "transcript") {
    elements.transcript.textContent = message.text || "Question received";
    setInference("thinking");
    setStatus("Speech recognized. ARGUS is reasoning over the available context.");
    imageUploaded = false;
    return;
  }

  if (message.type === "answer") {
    elements.answer.textContent = message.text || "No answer was returned.";
    elements.sendQuestion.disabled = false;
    setInference("answer");
    setStatus("Answer received. ARGUS is preparing the voice response.");
    if (message.thread_id) {
      threadId = message.thread_id;
      sessionStorage.setItem("argus-thread-id", threadId);
    }
    clearImageSelection();
    return;
  }

  if (message.type === "audio_start") {
    receivingTtsAudio = message.audio_format === "pcm_16000";
    if (!receivingTtsAudio) {
      throw new Error(`Unsupported response audio format: ${message.audio_format || "unknown"}.`);
    }
    elements.audioIndicator.classList.add("is-playing");
    elements.audioState.textContent = "Speaking response";
    setInference("speaking");
    return;
  }

  if (message.type === "audio_end") {
    receivingTtsAudio = false;
    const remainingMs = Math.max(0, (nextPlaybackTime - (playbackContext?.currentTime || 0)) * 1000);
    window.setTimeout(() => {
      elements.audioIndicator.classList.remove("is-playing");
      elements.audioState.textContent = "Voice response complete";
      setInference("ready");
    }, remainingMs);
    return;
  }

  if (message.type === "audio_error") {
    receivingTtsAudio = false;
    elements.audioIndicator.classList.remove("is-playing");
    elements.audioState.textContent = "Text response only";
    showError(message.message || "Speech generation failed.");
    return;
  }

  if (message.type === "error") {
    elements.sendQuestion.disabled = false;
    showError(message.message || "The backend reported an error.");
  }
}

async function ensurePlaybackContext() {
  if (!playbackContext || playbackContext.state === "closed") {
    playbackContext = new AudioContext();
    nextPlaybackTime = 0;
  }
  if (playbackContext.state === "suspended") await playbackContext.resume();
  return playbackContext;
}

async function playPcm16(arrayBuffer) {
  const context = await ensurePlaybackContext();
  const view = new DataView(arrayBuffer);
  const sampleCount = Math.floor(arrayBuffer.byteLength / 2);
  const audioBuffer = context.createBuffer(1, sampleCount, 16000);
  const channel = audioBuffer.getChannelData(0);
  for (let index = 0; index < sampleCount; index += 1) {
    channel[index] = view.getInt16(index * 2, true) / 0x8000;
  }
  const source = context.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(context.destination);
  const startAt = Math.max(context.currentTime, nextPlaybackTime);
  source.start(startAt);
  nextPlaybackTime = startAt + audioBuffer.duration;
}

function setImage(file) {
  if (!file) return;
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
    showError("Choose a JPEG, PNG, or WebP image.");
    return;
  }
  if (imageUploaded) {
    showError("The current image is already armed for the next question. Ask it before choosing another frame.");
    return;
  }
  if (imagePreviewUrl) URL.revokeObjectURL(imagePreviewUrl);
  selectedImage = file;
  imagePreviewUrl = URL.createObjectURL(file);
  elements.imagePreview.src = imagePreviewUrl;
  elements.imagePreview.hidden = false;
  elements.imagePlaceholder.hidden = true;
  elements.clearImage.hidden = false;
  elements.imageDropZone.classList.add("has-image");
  setStatus("Camera frame selected. It will be attached to the next question.");
  if (isRecording && socket?.readyState === WebSocket.OPEN) {
    uploadSelectedImage(socket).catch((error) => showError(error.message));
  }
}

function clearImageSelection() {
  if (imagePreviewUrl) URL.revokeObjectURL(imagePreviewUrl);
  imagePreviewUrl = "";
  selectedImage = null;
  imageUploaded = false;
  elements.imageInput.value = "";
  elements.imagePreview.removeAttribute("src");
  elements.imagePreview.hidden = true;
  elements.imagePlaceholder.hidden = false;
  elements.clearImage.hidden = true;
  elements.imageDropZone.classList.remove("has-image");
}

async function uploadSelectedImage(activeSocket) {
  if (!selectedImage || imageUploaded) return;
  activeSocket.send(JSON.stringify({ type: "image_start", content_type: selectedImage.type }));
  activeSocket.send(await selectedImage.arrayBuffer());
  activeSocket.send(JSON.stringify({ type: "image_end" }));
  imageUploaded = true;
}

async function submitQuestion(event) {
  event.preventDefault();
  clearError();
  const question = elements.questionText.value.trim();
  if (!question) return;

  elements.sendQuestion.disabled = true;
  elements.transcript.textContent = question;
  elements.answer.textContent = "Analyzing request…";
  setInference(selectedImage ? "seeing" : "thinking");

  try {
    await ensurePlaybackContext();
    const activeSocket = await connectWebSocket();
    await uploadSelectedImage(activeSocket);
    activeSocket.send(JSON.stringify({ type: "question", text: question }));
    elements.questionText.value = "";
    setStatus(selectedImage ? "Frame and question sent to ARGUS." : "Question sent to ARGUS.");
  } catch (error) {
    elements.sendQuestion.disabled = false;
    showError(error.message || "The question could not be sent.");
  }
}

async function refreshAudioInputs() {
  const previous = elements.audioInput.value;
  const devices = await navigator.mediaDevices.enumerateDevices();
  const inputs = devices.filter((device) => device.kind === "audioinput");
  elements.audioInput.replaceChildren();
  inputs.forEach((device, index) => {
    const option = document.createElement("option");
    option.value = device.deviceId;
    option.textContent = device.label || `Microphone ${index + 1}`;
    elements.audioInput.append(option);
  });
  elements.audioInput.disabled = inputs.length === 0 || isRecording;
  elements.toggleListening.disabled = inputs.length === 0;
  if (inputs.some((device) => device.deviceId === previous)) {
    elements.audioInput.value = previous;
  }
}

async function enableMicrophone() {
  clearError();
  if (!navigator.mediaDevices?.getUserMedia) {
    showError("This browser does not support microphone capture.");
    return;
  }
  try {
    const permissionStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    permissionStream.getTracks().forEach((track) => track.stop());
    await refreshAudioInputs();
    elements.microphoneState.textContent = "Ready";
    elements.microphoneState.classList.add("is-live");
    elements.enableMicrophone.textContent = "Refresh mics";
    setStatus("Microphone ready. Start listening and say “Hi Spider.”");
  } catch (error) {
    showError(readableMicrophoneError(error));
  }
}

function selectedDeviceConstraints() {
  const audio = {
    channelCount: { ideal: 1 },
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  };
  if (elements.audioInput.value) audio.deviceId = { exact: elements.audioInput.value };
  return { audio };
}

function responseAudioIsPlaying() {
  return Boolean(playbackContext && playbackContext.state !== "closed" && playbackContext.currentTime < nextPlaybackTime + 0.1);
}

async function startListening() {
  clearError();
  elements.toggleListening.disabled = true;
  try {
    const activeSocket = await connectWebSocket();
    await ensurePlaybackContext();
    await uploadSelectedImage(activeSocket);
    microphoneStream = await navigator.mediaDevices.getUserMedia(selectedDeviceConstraints());
    recordingContext = new AudioContext();
    await recordingContext.audioWorklet.addModule(new URL("./pcm-worklet.js", import.meta.url));
    await recordingContext.resume();
    sourceNode = recordingContext.createMediaStreamSource(microphoneStream);
    workletNode = new AudioWorkletNode(recordingContext, "pcm16-downsampler", {
      numberOfInputs: 1,
      numberOfOutputs: 1,
      outputChannelCount: [1],
      processorOptions: { targetSampleRate: 16000, chunkSamples: 320 },
    });
    silentGain = recordingContext.createGain();
    silentGain.gain.value = 0;
    workletNode.port.onmessage = (event) => {
      if (isRecording && !receivingTtsAudio && !responseAudioIsPlaying() && socket?.readyState === WebSocket.OPEN) {
        socket.send(event.data);
      }
    };
    sourceNode.connect(workletNode);
    workletNode.connect(silentGain);
    silentGain.connect(recordingContext.destination);
    isRecording = true;
    elements.audioInput.disabled = true;
    elements.toggleListening.disabled = false;
    elements.toggleListening.classList.add("is-listening");
    elements.toggleListening.innerHTML = '<span aria-hidden="true">■</span> Stop listening';
    elements.microphoneState.textContent = "Listening";
    elements.voiceMeter.classList.add("is-listening");
    setInference("listening");
    setStatus("Listening. Say “Hi Spider,” ask your question, then pause.");
  } catch (error) {
    await releaseMicrophoneResources();
    elements.toggleListening.disabled = elements.audioInput.options.length === 0;
    showError(readableMicrophoneError(error));
  }
}

async function releaseMicrophoneResources() {
  isRecording = false;
  workletNode?.disconnect();
  sourceNode?.disconnect();
  silentGain?.disconnect();
  workletNode = null;
  sourceNode = null;
  silentGain = null;
  microphoneStream?.getTracks().forEach((track) => track.stop());
  microphoneStream = null;
  if (recordingContext && recordingContext.state !== "closed") await recordingContext.close();
  recordingContext = null;
}

async function stopListening(message = "Listening stopped. Typed questions remain available.") {
  await releaseMicrophoneResources();
  elements.audioInput.disabled = false;
  elements.toggleListening.disabled = false;
  elements.toggleListening.classList.remove("is-listening");
  elements.toggleListening.innerHTML = '<span aria-hidden="true">●</span> Start listening';
  elements.microphoneState.textContent = "Ready";
  elements.voiceMeter.classList.remove("is-listening");
  setInference("ready");
  setStatus(message);
}

elements.connect.addEventListener("click", async () => {
  clearError();
  try {
    if (socket?.readyState === WebSocket.OPEN) await disconnectWebSocket();
    else await connectWebSocket();
  } catch (error) {
    showError(error.message);
  }
});

elements.imageInput.addEventListener("change", () => setImage(elements.imageInput.files?.[0]));
elements.clearImage.addEventListener("click", clearImageSelection);
elements.imageDropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  elements.imageDropZone.classList.add("is-dragging");
});
elements.imageDropZone.addEventListener("dragleave", () => elements.imageDropZone.classList.remove("is-dragging"));
elements.imageDropZone.addEventListener("drop", (event) => {
  event.preventDefault();
  elements.imageDropZone.classList.remove("is-dragging");
  setImage(event.dataTransfer.files?.[0]);
});
elements.enableMicrophone.addEventListener("click", enableMicrophone);
elements.toggleListening.addEventListener("click", () => isRecording ? stopListening() : startListening());
elements.questionForm.addEventListener("submit", submitQuestion);
elements.promptSuggestions.forEach((button) => {
  button.addEventListener("click", () => {
    elements.questionText.value = button.dataset.prompt;
    elements.questionText.focus();
  });
});

if (navigator.mediaDevices) {
  navigator.mediaDevices.addEventListener("devicechange", () => {
    if (!isRecording && !elements.audioInput.disabled) refreshAudioInputs().catch((error) => showError(error.message));
  });
}

window.addEventListener("beforeunload", () => {
  microphoneStream?.getTracks().forEach((track) => track.stop());
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "close" }));
  if (imagePreviewUrl) URL.revokeObjectURL(imagePreviewUrl);
});
