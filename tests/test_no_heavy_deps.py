from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_FORBIDDEN = ("torch", "transformers", "sentence-transformers", "sentence_transformers")


def test_requirements_files_have_no_torch_family() -> None:
    files = [ROOT / "requirements.txt", ROOT / "requirements-rag.txt"]
    for path in files:
        text = path.read_text(encoding="utf-8").lower()
        for name in _FORBIDDEN:
            assert name not in text, f"{name} found in {path}"
