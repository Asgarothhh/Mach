from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_FORBIDDEN = ("torch", "transformers", "sentence-transformers", "sentence_transformers")


def test_requirements_files_have_no_torch_family() -> None:
    files = [ROOT / "requirements.txt", ROOT / "requirements-rag.txt"]
    for path in files:
        text = path.read_text(encoding="utf-8").lower()
        for name in _FORBIDDEN:
            assert name not in text, f"{name} found in {path}"


def test_api_image_bakes_live_speech_weights() -> None:
    dockerfile = (ROOT / "apps/api/Dockerfile").read_text(encoding="utf-8")
    assert "requirements-speech.txt" in dockerfile
    assert "fetch_models.py" in dockerfile
    assert "prefetch_runtime_weights.py" in dockerfile
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "VOICE_ASR_MODE: live" in compose
    assert "VOICE_TTS_MODE: real" in compose
    assert "VOICE_ASR_MODE: mock" not in compose
