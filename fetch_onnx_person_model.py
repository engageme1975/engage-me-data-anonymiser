"""
Pre-fetches the experimental ONNX PERSON model (see onnx_person_recognizer.py)
into models/bert-base-ner-onnx/ so it ships as a local file rather than being
downloaded at redaction time - keeps the "no data leaves customer control"
guarantee intact (only model *weights* are fetched here, at build time, never
customer data). Run once during Docker build / EXE build, not at app runtime.
"""

from pathlib import Path
from huggingface_hub import hf_hub_download

from onnx_person_recognizer import MODEL_REPO, MODEL_FILENAME

OUT_DIR = Path(__file__).parent / "models" / "bert-base-ner-onnx"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, out_name in [
        (MODEL_FILENAME, "model_int8.onnx"),
        ("tokenizer.json", "tokenizer.json"),
    ]:
        downloaded = hf_hub_download(MODEL_REPO, filename)
        target = OUT_DIR / out_name
        target.write_bytes(Path(downloaded).read_bytes())
        print(f"{filename} -> {target} ({target.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
