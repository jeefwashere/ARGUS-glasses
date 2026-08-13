# ARGUS Smart Glasses

ARGUS is a low-cost, modular AI smart-glasses prototype designed to add AI vision, voice interaction, translation, and visual responses to a wearable glasses form factor.

The project combines an ESP32-based hardware client with a FastAPI backend that handles real-time speech transcription, multimodal AI requests, conversational memory, and text-to-speech generation.

The core idea is to make the system **attachable to different pairs of glasses rather than requiring a completely custom glasses frame**.

---

## Features

The current MVP is designed around four main capabilities:

* **Voice interaction** — speak naturally to the glasses.
* **AI vision** — optionally capture an image and ask a question about what the camera sees.
* **Heads-up text display** — show the AI response on the glasses display.
* **Voice responses** — generate spoken AI responses using ElevenLabs.

Example interactions:

* "What am I looking at?"
* "Translate this sign."
* "What does this object do?"
* "Read this text for me."
* "Explain what I'm seeing."
* Follow-up questions that reuse the same conversation thread.

---

# Architecture

```text
                         ARGUS ARCHITECTURE

                    ┌─────────────────────┐
                    │       USER          │
                    │  Voice / Environment│
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    ESP32 Client     │
                    │                     │
                    │ Camera              │
                    │ Microphone/audio    │
                    │ Display             │
                    │ Speaker/audio out   │
                    └──────────┬──────────┘
                               │
                         WebSocket /ask
                               │
                               ▼
                    ┌─────────────────────┐
                    │    FastAPI Backend  │
                    └──────────┬──────────┘
                               │
               ┌───────────────┼────────────────┐
               │               │                │
               ▼               ▼                ▼
        ┌────────────┐   ┌────────────┐   ┌────────────┐
        │ Deepgram   │   │ Backboard  │   │ ElevenLabs │
        │            │   │            │   │            │
        │ Speech →   │   │ AI / LLM   │   │ Text →     │
        │ Text       │   │ + threads  │   │ Speech     │
        └─────┬──────┘   └─────┬──────┘   └─────┬──────┘
              │                │                │
              └──────────┐     │     ┌──────────┘
                         ▼     ▼     ▼
                    ┌─────────────────────┐
                    │ WebSocket Response  │
                    │                     │
                    │ JSON text           │
                    │ PCM audio bytes     │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │       ESP32         │
                    │                     │
                    │ Display response    │
                    │ Play response       │
                    └─────────────────────┘
```

---

# Request Flow

A normal speech request follows this path:

```text
User speaks
    ↓
ESP32 sends audio bytes
    ↓
FastAPI /ask WebSocket
    ↓
Deepgram
    ↓
Final transcript
    ↓
Backboard
    ↓
AI text response
    ├──────────────→ JSON → glasses display
    │
    └→ ElevenLabs
           ↓
       PCM audio
           ↓
       WebSocket
           ↓
       speaker
```

For a vision request:

```text
ESP32 captures image
    ↓
image_start
    ↓
image bytes
    ↓
image_end
    ↓

User speech
    ↓
Deepgram transcript
    ↓

transcript + image
    ↓
Backboard
    ↓
AI response
```

An image is optional. Normal voice questions do not require a camera capture.

---

# Backend Stack

| Component         | Technology     | Responsibility                                        |
| ----------------- | -------------- | ----------------------------------------------------- |
| API server        | FastAPI        | Main backend                                          |
| Transport         | WebSocket      | Bidirectional hardware communication                  |
| Speech-to-text    | Deepgram       | Converts microphone audio to text                     |
| AI / conversation | Backboard      | Processes questions, images, and conversation threads |
| Text-to-speech    | ElevenLabs     | Converts AI responses into speech                     |
| Language          | Python 3.12    | Backend implementation                                |
| Testing           | pytest         | Unit and WebSocket tests                              |
| Async testing     | pytest-asyncio | Async service tests                                   |
| Containerization  | Docker         | Backend packaging                                     |
| CI                | GitHub Actions | Automated tests and Docker builds                     |
| Deployment target | Render         | Hosted backend                                        |

---

# Project Structure

A simplified structure looks like:

```text
cutc-2026-glasses/
│
├── app/
│   ├── main.py
│   │
│   ├── routes/
│   │   └── ask.py
│   │
│   ├── services/
│   │   ├── backboard_service.py
│   │   ├── deepgram_service.py
│   │   └── elevenlabs_service.py
│   │
│   └── utils/
│       └── list_elevenlabs_voices.py
│
├── tests/
│   ├── test_ask_websocket.py
│   ├── test_health.py
│   ├── test_elevenlabs_service.py
│   └── test_elevenlabs_integration.py
│
├── .github/
│   └── workflows/
│       └── ...
│
├── Dockerfile
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

# FastAPI Endpoints

## `GET /`

Basic API status endpoint.

Example:

```json
{
  "message": "Glasses API is running"
}
```

## `GET /health`

Health check endpoint.

Example:

```json
{
  "status": "ok"
}
```

## `WS /ask`

The main ARGUS communication channel.

This WebSocket handles:

* microphone audio
* image uploads
* conversation state
* Deepgram transcription
* Backboard requests
* AI text responses
* ElevenLabs audio responses

---

# WebSocket Protocol

The same WebSocket carries both JSON control messages and binary data.

This allows ARGUS to keep a persistent connection between the hardware and backend.

## Client → Server

### Microphone audio

Binary frames sent while no image upload is active are forwarded to Deepgram.

```text
[BINARY AUDIO]
```

---

## Start image upload

```json
{
  "type": "image_start",
  "content_type": "image/jpeg"
}
```

Supported image formats:

```text
image/jpeg
image/png
image/webp
```

Server response:

```json
{
  "type": "image_started"
}
```

The ESP32 can then send image bytes as binary WebSocket frames.

---

## Finish image upload

```json
{
  "type": "image_end"
}
```

Server response:

```json
{
  "type": "image_received"
}
```

The image is temporarily stored until it can be paired with the user's transcript.

---

## Restore a Backboard conversation

```json
{
  "type": "set_thread",
  "thread_id": "existing-thread-id"
}
```

Server:

```json
{
  "type": "thread_set",
  "thread_id": "existing-thread-id"
}
```

This allows the device to continue an existing conversation.

---

## Close connection

Either:

```text
close
```

or:

```json
{
  "type": "close"
}
```

---

# Server → Client

## Transcript

After Deepgram produces a final transcript:

```json
{
  "type": "transcript",
  "text": "What am I looking at?"
}
```

This is useful for debugging and can also be shown in the UI if desired.

---

## AI answer

After Backboard responds:

```json
{
  "type": "answer",
  "text": "You are looking at a coffee mug.",
  "thread_id": "thread-123"
}
```

The ESP32 can send the `text` field to the glasses display.

---

## Audio start

If ElevenLabs successfully generates speech:

```json
{
  "type": "audio_start",
  "audio_format": "pcm_16000"
}
```

The next binary WebSocket data contains the generated speech audio.

---

## Audio data

```text
[BINARY PCM AUDIO]
```

The current TTS format is:

```text
PCM
16 kHz
16-bit audio
```

This avoids Base64 encoding audio inside JSON and keeps binary transport more efficient.

---

## Audio error

If Backboard succeeds but ElevenLabs fails:

```json
{
  "type": "audio_error",
  "message": "Speech generation failed."
}
```

The text response remains available even if audio generation fails.

This provides graceful degradation:

```text
Backboard + ElevenLabs succeed
→ text + voice

Backboard succeeds, ElevenLabs fails
→ text only

Backboard fails
→ error
```

---

# Conversation State

Backboard thread IDs are preserved between questions.

On the first request:

```text
thread_id = None
```

Backboard creates a thread and returns an ID.

The backend stores that ID for subsequent questions:

```text
Question 1
→ thread_id=None
→ Backboard returns thread-123

Question 2
→ thread_id=thread-123

Question 3
→ thread_id=thread-123
```

This allows follow-up questions to retain conversational context.

A device can also restore an existing conversation using `set_thread`.

---

# Image Handling

Images are uploaded in chunks over the existing WebSocket.

The backend creates a temporary file when it receives:

```json
{
  "type": "image_start",
  "content_type": "image/jpeg"
}
```

Incoming binary frames are written into the file until:

```json
{
  "type": "image_end"
}
```

The resulting image is then attached to the next pending Backboard request.

Temporary files are deleted after processing or when a client disconnects.

---

# Deepgram

Deepgram provides real-time speech-to-text.

The backend creates one `DeepgramSession` for each `/ask` WebSocket connection.

```text
ESP32 microphone
    ↓
WebSocket binary frames
    ↓
DeepgramSession.send_audio()
    ↓
Deepgram
    ↓
final transcript callback
    ↓
submit_pending_turn()
```

Only finalized transcript text is submitted to Backboard.

---

# Backboard

Backboard serves as the conversational AI layer.

It receives:

```text
question text
optional image
optional existing thread ID
```

and returns information including:

```text
content
thread_id
```

The response content is used for both:

1. the text shown on the glasses
2. ElevenLabs speech generation

---

# ElevenLabs

ElevenLabs converts the Backboard response into speech.

The current service uses:

```python
AsyncElevenLabs
```

with:

```text
model: eleven_flash_v2_5
output: pcm_16000
```

The asynchronous ElevenLabs API returns audio chunks, which are collected into a single byte sequence for the current MVP.

Conceptually:

```python
audio = client.text_to_speech.convert(...)

audio_bytes = b"".join(
    [chunk async for chunk in audio]
)
```

The complete PCM response is then sent to the ESP32 as a binary WebSocket frame.

Future work can stream these chunks directly instead of waiting for the complete TTS response.

---

# Environment Variables

Create a `.env` file in the project root.

Example:

```env
DEEPGRAM_API_KEY=your_deepgram_key

ELEVENLABS_API_KEY=your_elevenlabs_key
ELEVENLABS_VOICE_ID=your_voice_id

# Add the credentials required by backboard_service.py
# using the variable names configured by that service.
```

Do **not** commit `.env` or production API keys to Git.

---

# Installation

## 1. Clone the repository

```bash
git clone <repository-url>
cd cutc-2026-glasses
```

## 2. Create a virtual environment

Windows:

```powershell
python -m venv venv
venv\Scripts\activate
```

macOS/Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

## 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Configure `.env`

Add the required API keys.

## 5. Start FastAPI

```bash
uvicorn app.main:app --reload
```

The development API will normally be available at:

```text
http://127.0.0.1:8000
```

The WebSocket endpoint is:

```text
ws://127.0.0.1:8000/ask
```

---

# Testing

Run the normal test suite with:

```bash
pytest -m "not integration"
```

This should run tests without making real ElevenLabs API calls.

---

## WebSocket Tests

The project contains WebSocket tests covering behavior such as:

* speech-only questions
* conversation thread reuse
* image + speech questions
* chunked images
* transcript arriving before image completion
* image arriving before transcript
* unsupported image formats
* duplicate image uploads
* invalid control messages
* temporary file cleanup
* Backboard failures
* client disconnects
* restoring conversation thread IDs

External services are mocked for these tests.

---

## ElevenLabs Unit Tests

Unit tests should mock ElevenLabs rather than make real API requests.

They verify behavior such as:

```text
async chunks:
b"abc"
b"def"
b"ghi"

→

b"abcdefghi"
```

They also verify:

* correct response text is sent
* correct voice ID is used
* model is `eleven_flash_v2_5`
* output format is `pcm_16000`
* empty responses fail cleanly
* ElevenLabs errors propagate to the route

---

# ElevenLabs Integration Test

A separate integration test can make a real ElevenLabs API request.

Run:

```bash
pytest -m integration -v
```

The integration test should only run when:

```text
ELEVENLABS_API_KEY
ELEVENLABS_VOICE_ID
```

are configured.

Real integration tests may consume ElevenLabs credits and depend on account permissions and voice availability.

They should therefore remain separate from normal CI tests.

---

# CI/CD

GitHub Actions runs CI on:

```text
push → main
pull request → main
manual workflow dispatch
```

The pipeline:

```text
Checkout repository
        ↓
Set up Python 3.12
        ↓
Install requirements
        ↓
Run non-integration tests
        ↓
Build Docker image
```

Recommended test command:

```yaml
- name: Run tests
  run: pytest -m "not integration"
```

Real ElevenLabs integration tests should not run on every normal CI execution.

---

# Docker

The backend is containerized using Python 3.12.

Build:

```bash
docker build -t glasses-api .
```

Run:

```bash
docker run -p 10000:10000 glasses-api
```

The container launches:

```text
uvicorn app.main:app
```

on:

```text
0.0.0.0:10000
```

The Docker image also installs FFmpeg.

---

# Deployment

The backend is intended to be deployable to Render.

Conceptually:

```text
ESP32
    ↓ Internet
Render
    ↓
FastAPI WebSocket
    ↓
Deepgram / Backboard / ElevenLabs
```

This allows the wearable device and backend to operate across different networks rather than requiring the ESP32 and development computer to be on the same LAN.

Production environment variables should be configured through the deployment platform rather than committed to the repository.

---

# Hardware

The ARGUS prototype is centered around an ESP32-based wearable hardware system.

The current hardware responsibilities are approximately:

```text
ESP32
├── capture camera images
├── capture/send user audio
├── maintain backend connection
├── receive text
├── control display
├── receive PCM audio
└── output speech audio
```

The broader wearable prototype includes:

* ESP32 camera hardware
* small display
* optical projection/combiner system
* microphone/audio input
* speaker/audio output
* portable power
* glasses-mounted enclosure

The optical prototype is intended to project a small display through optics and reflect it toward the user's eye using the glasses lens or a small partially reflective combiner.

---

# Hardware / Backend Responsibility Split

The ESP32 should remain relatively lightweight.

## ESP32

```text
Capture
Transmit
Receive
Display
Playback
```

## Backend

```text
Speech recognition
AI reasoning
Image understanding
Conversation state
Speech synthesis
```

This avoids trying to run large AI models directly on the wearable hardware.

---

# Design Goals

## Low cost

ARGUS is intended to use inexpensive, commonly available hardware rather than specialized commercial AR components wherever possible.

## Modular

The project is intended to become a module that can attach to different glasses frames.

## Cloud-assisted

Computationally expensive AI operations run remotely.

## Multimodal

The same interface supports:

```text
voice
+
vision
+
text
+
audio
```

## Graceful degradation

Individual cloud services should not unnecessarily break the entire user experience.

For example:

```text
ElevenLabs failure
≠
lost AI response
```

The user can still receive text.

---

# Current MVP Scope

The MVP does **not** need to solve every smart-glasses problem.

The immediate target is:

```text
1. User speaks

2. ESP32 sends audio

3. Deepgram transcribes it

4. Optional camera image is attached

5. Backboard generates an answer

6. Answer text appears on glasses

7. ElevenLabs generates speech

8. ESP32 plays the speech
```

If this complete loop works reliably, ARGUS has its core end-to-end demo.

---

# Future Improvements

Potential improvements after the MVP include:

### Streaming TTS

Instead of:

```text
generate entire ElevenLabs response
→ join chunks
→ send full PCM response
```

use:

```text
ElevenLabs chunk
→ WebSocket
→ ESP32 playback

ElevenLabs next chunk
→ WebSocket
→ ESP32 playback
```

This should reduce perceived response latency.

### Better WebSocket framing

Add IDs to turns and audio messages:

```json
{
  "type": "audio_start",
  "turn_id": "123",
  "audio_format": "pcm_16000"
}
```

This would make concurrent or interrupted interactions easier to handle.

### Audio interruption

Allow the user to begin a new question while the previous TTS response is playing.

### Display-specific responses

Instead of sending the same content to the display and speaker:

```text
Backboard
├── display_text → concise
└── speech_text  → detailed
```

This would improve readability on a small display.

### Streaming AI responses

Stream AI output instead of waiting for a complete Backboard response.

### Improved hardware enclosure

Develop a compact clip-on enclosure that can mount the camera, optics, display, and electronics to different glasses frames.

### Battery optimization

Reduce ESP32 power usage and optimize Wi-Fi/audio behavior for wearable operation.

---

# Development Principles

Keep the MVP architecture simple:

```text
ESP32
→ FastAPI
→ specialized cloud services
→ ESP32
```

Avoid adding additional services unless they solve a concrete problem.

For normal tests:

```text
mock external APIs
```

For explicit integration tests:

```text
use real APIs
```

For production:

```text
never store API secrets in source control
```

---

# ARGUS

**AI vision and voice, designed to attach to the glasses you already own.**
