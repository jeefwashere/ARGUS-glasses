from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_demo_serves_voice_assistant():
    response = client.get("/demo")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "ARGUS Exploded Glasses Demo" in response.text
    assert "Innovation you can" in response.text
    assert "From perception" in response.text
    assert "Ask what you see" in response.text
    assert "/static/app.js" in response.text


def test_demo_static_assets_are_available():
    app_js = client.get("/static/app.js")
    worklet_js = client.get("/static/pcm-worklet.js")
    stylesheet = client.get("/static/styles.css")

    assert app_js.status_code == 200
    assert "pcm16-downsampler" in app_js.text
    assert worklet_js.status_code == 200
    assert 'registerProcessor("pcm16-downsampler"' in worklet_js.text
    assert stylesheet.status_code == 200


def test_demo_client_forwards_wav_and_display_to_esp32():
    app_js = client.get("/static/app.js").text

    assert 'globalThis.ARGUS_ESP32_BASE_URL || "http://10.0.0.97"' in app_js
    assert '"/display"' in app_js
    assert '"text/plain; charset=utf-8"' in app_js
    assert '"/audio"' in app_js
    assert '"audio/wav"' in app_js
    assert 'responseAudioFormat === "wav_44100_stereo"' in app_js
    assert "expectingEsp32Audio = false" in app_js
