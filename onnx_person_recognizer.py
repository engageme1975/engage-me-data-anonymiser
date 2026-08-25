"""
Experimental: ONNX-based PERSON recognizer (Xenova/bert-base-NER, int8
quantized - originally dslim/bert-base-NER fine-tuned on CoNLL-2003).

Evaluated as a candidate fix for a documented weak spot: spaCy's en_core_web_md
has materially lower PERSON recall (~75% vs ~92-97%) for names that are also
ordinary English words (Cole, Thompson, Walker, Davies, ...), which flood the
Residual Flags sheet as POSSIBLE_MISSED_NAME noise on real data.

Runs on onnxruntime + tokenizers only - verified to pull in zero torch or
transformers as dependencies, unlike GLiNER (whose pip package hard-imports
torch in model.py regardless of ONNX/INT8 mode).

An earlier version of this experiment used protectai/bert-base-NER-onnx
(fp32, 431MB) - that repo turned out to be archived/unmaintained by Protect
AI. Switched to Xenova/bert-base-NER's int8 export instead: actively
maintained (Xenova - transformers.js author, 41.5k downloads, last updated
2025-07), same base model, identical accuracy in testing, but 108.5MB
(~4x smaller) and ~1.5x faster.

Two real bugs were found and fixed while wiring this in (see git history):
RecognizerRegistry.add_recognizer() never calls .load() itself, so the
model silently never loaded until this called .load() explicitly - and
BERT's 512-token position-embedding cap crashed on a real complaint cell
that tokenized to 663 tokens, fixed with manual sliding-window chunking
(510 tokens, 50-token stride). A further precision bug (WordPiece
continuation tokens like "##p" being treated as independent predictions)
produced garbled partial-word false positives ("Dam" instead of "Damp",
"As" instead of "Aspect") until fixed by aggregating to word level.

Real, measured trade-off on the 728-row Beyond Housing pilot file, PERSON
entity only, after all three fixes:
- +172 additional PERSON detections (1335 -> 1507, +12.9%) - genuine
  recall gain on names spaCy misses (e.g. "Chase Walker", "Hunter Davies").
- Genuine remaining false positives: general-purpose CoNLL-2003 training
  data doesn't know UK social-housing vocabulary or this client's own org
  name - "Damp", "Mould", "Membrane" (repair terms) and "Freebridge"
  (the housing association's own name) get misclassified as PERSON. Not
  a bug - a real domain-mismatch limitation of this specific model.
- model_int8.onnx is ~108.5MB on disk - would add roughly 40% to the current
  ~269MB EXE bundle.
- ~11.2 cells/sec single-threaded on realistic complaint-length text, vs
  45-66 cells/sec for the ENTIRE current pipeline (all entity types) on the
  same real data - and this only covers PERSON; spaCy is still required for
  every other entity type, so this is a strict addition to runtime, not a
  replacement (~4x slower for the PERSON pass alone).
- Presidio's custom-recognizer analyze() calls run in the main process
  (n_process only parallelises spaCy's own NLP pipeline), so this cost is
  NOT offset by the existing multi-worker parallelism.

Disabled by default (enable_onnx_person=False in create_beyond_analyzer) -
this module exists to make the trade-off testable, not to ship it.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import numpy as np

from presidio_analyzer import EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts

MODEL_REPO = "Xenova/bert-base-NER"
MODEL_FILENAME = "onnx/model_int8.onnx"
ID2LABEL = {
    0: "O", 1: "B-MISC", 2: "I-MISC", 3: "B-PER", 4: "I-PER",
    5: "B-ORG", 6: "I-ORG", 7: "B-LOC", 8: "I-LOC",
}


def _resolve_model_paths() -> Optional[tuple[Path, Path]]:
    """
    Returns (model_onnx_path, tokenizer_json_path), looking for a locally-
    bundled copy first (populated at build time by
    fetch_onnx_person_model.py - see Dockerfile), falling back to the
    huggingface_hub cache used when running from source. Never downloads at
    redaction time - only weight download is deferred to build/setup, never
    anything touching customer data.
    """
    local_dir = Path(__file__).parent / "models" / "bert-base-ner-onnx"
    local_model = local_dir / "model_int8.onnx"
    local_tokenizer = local_dir / "tokenizer.json"
    if local_model.exists() and local_tokenizer.exists():
        return local_model, local_tokenizer

    try:
        from huggingface_hub import try_to_load_from_cache
    except ImportError:
        return None

    cached_model = try_to_load_from_cache(MODEL_REPO, MODEL_FILENAME)
    cached_tokenizer = try_to_load_from_cache(MODEL_REPO, "tokenizer.json")
    if (
        cached_model and Path(cached_model).exists()
        and cached_tokenizer and Path(cached_tokenizer).exists()
    ):
        return Path(cached_model), Path(cached_tokenizer)
    return None


class OnnxPersonRecognizer(EntityRecognizer):
    """Experimental BERT-NER (ONNX) PERSON recognizer. See module docstring."""

    def __init__(self) -> None:
        super().__init__(
            supported_entities=["PERSON"],
            name="Experimental ONNX BERT-NER Person",
            supported_language="en",
        )
        self._session = None
        self._tokenizer = None

    def load(self) -> None:
        paths = _resolve_model_paths()
        if paths is None:
            # Model not available locally - recognizer degrades to a no-op
            # rather than failing analyzer construction, so a machine
            # without the model pre-fetched still runs (just without this
            # experimental pass).
            return
        model_path, tokenizer_path = paths

        import onnxruntime as ort
        from tokenizers import Tokenizer

        self._tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self._cls_id = self._tokenizer.token_to_id("[CLS]")
        self._sep_id = self._tokenizer.token_to_id("[SEP]")
        self._session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])

    # BERT's absolute position embeddings hard-cap input at 512 tokens
    # ([CLS] + content + [SEP], so 510 content tokens) - real complaint
    # narratives can exceed this (found via a real crash on the 728-row
    # Beyond Housing pilot file: one cell tokenized to 663 tokens). Chunked
    # manually with a stride below, since the tokenizers library's built-in
    # truncation(stride=...) only produces ONE overflow chunk - not enough
    # to fully cover text requiring 3+ windows, which real longer cells do.
    _CHUNK_TOKENS = 510
    _STRIDE_TOKENS = 50

    def _run_chunk(
        self, ids: List[int], offsets: List[tuple], tokens: List[str]
    ) -> List[RecognizerResult]:
        chunk_ids = [self._cls_id] + ids + [self._sep_id]
        chunk_offsets = [(0, 0)] + offsets + [(0, 0)]
        chunk_tokens = ["[CLS]"] + tokens + ["[SEP]"]
        input_ids = np.array([chunk_ids], dtype=np.int64)
        attention_mask = np.ones_like(input_ids)
        token_type_ids = np.zeros_like(input_ids)
        outputs = self._session.run(
            None,
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "token_type_ids": token_type_ids,
            },
        )
        pred_ids = outputs[0][0].argmax(axis=-1)

        # BERT's WordPiece tokenizer splits many words into multiple
        # subword pieces (e.g. "Damp" -> "Dam" + "##p", "Aspect" ->
        # "As" + "##pect"). The model only produces a reliable label on
        # the FIRST piece of each word - predictions on "##"-prefixed
        # continuation pieces are noise and must never be used to start or
        # end a span on their own, or a random subword fragment ("Dam",
        # "As", "Free", "pps", "Z", "Co", "Me") gets redacted as if it were
        # a whole word. Found via a real precision spot-check on the 728-
        # row Beyond Housing pilot file - roughly a third of the "new"
        # detections before this fix were exactly this kind of garbled
        # partial-word artifact, not genuine model disagreement with spaCy.
        words = []  # list of (label, start, end)
        for offset, token, pid in zip(chunk_offsets, chunk_tokens, pred_ids):
            if offset == (0, 0):
                continue
            if token.startswith("##") and words:
                _, w_start, _ = words[-1]
                words[-1] = (words[-1][0], w_start, offset[1])
                continue
            words.append((ID2LABEL[int(pid)], offset[0], offset[1]))

        results = []
        cur_start: Optional[int] = None
        cur_end: Optional[int] = None
        for label, w_start, w_end in words:
            is_person = label in ("B-PER", "I-PER")
            starts_new = label == "B-PER" or (label == "I-PER" and cur_start is None)
            if is_person and not starts_new and cur_end is not None:
                cur_end = w_end
                continue
            if cur_start is not None:
                results.append(
                    RecognizerResult(entity_type="PERSON", start=cur_start, end=cur_end, score=0.75)
                )
                cur_start, cur_end = None, None
            if is_person:
                cur_start, cur_end = w_start, w_end
        if cur_start is not None:
            results.append(
                RecognizerResult(entity_type="PERSON", start=cur_start, end=cur_end, score=0.75)
            )
        return results

    def analyze(
        self,
        text: str,
        entities: List[str],
        nlp_artifacts: Optional[NlpArtifacts] = None,
    ) -> List[RecognizerResult]:
        if self._session is None or self._tokenizer is None:
            return []
        if "PERSON" not in entities and "ALL" not in entities:
            return []
        if not text.strip():
            return []

        enc = self._tokenizer.encode(text, add_special_tokens=False)
        ids, offsets, tokens = enc.ids, enc.offsets, enc.tokens
        if not ids:
            return []

        step = self._CHUNK_TOKENS - self._STRIDE_TOKENS
        seen_spans = set()
        results = []
        start = 0
        while True:
            end = min(start + self._CHUNK_TOKENS, len(ids))
            for result in self._run_chunk(ids[start:end], offsets[start:end], tokens[start:end]):
                span = (result.start, result.end)
                if span in seen_spans:
                    # Overlapping stride windows can re-detect the same
                    # entity near a chunk boundary - keep the first hit.
                    continue
                seen_spans.add(span)
                results.append(result)
            if end == len(ids):
                break
            start += step
        return results
