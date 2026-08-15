from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_demo_serves_voice_assistant():
    response = client.get("/demo")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "ARGUS Voice Assistant" in response.text
    assert "Say Hi Spider, then ask" in response.text
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
