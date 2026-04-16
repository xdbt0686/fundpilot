"""
FundPilot intent classifier — PyTorch inference wrapper.

Loads the trained character n-gram MLP from data/intent_model/.
Falls back to None if the model file is not found (rule-based router takes over).

Usage:
    from core.intent_classifier import IntentClassifier
    clf = IntentClassifier()          # singleton, cached on first import
    intent, confidence = clf.predict("VUAG和CSP1重叠严重吗？")
    # intent = "overlap", confidence = 0.97
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

_INSTANCE: Optional["IntentClassifier"] = None

BASE_DIR  = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "data" / "intent_model"


# ── Re-declare helpers (mirrors train script, no shared import needed) ─────────

def _extract_ngrams(text: str, sizes: List[int]) -> List[str]:
    t = text.lower().strip()
    ngrams: List[str] = []
    for n in sizes:
        for i in range(len(t) - n + 1):
            ngrams.append(t[i:i + n])
    return ngrams


def _encode(text: str, vocab: dict, ngram_sizes: List[int], max_len: int = 200) -> List[int]:
    unk = vocab.get("<UNK>", 1)
    return [vocab.get(g, unk) for g in _extract_ngrams(text, ngram_sizes)[:max_len]]


# ── Model architecture (must match train script) ───────────────────────────────

def _build_model(vocab_size: int, embed_dim: int, hidden_dim: int, num_classes: int):
    import torch.nn as nn

    class _Model(nn.Module):
        def __init__(self):
            super().__init__()
            self.embedding = nn.Embedding(vocab_size, embed_dim, padding_idx=0)
            self.fc1       = nn.Linear(embed_dim, hidden_dim)
            self.relu      = nn.ReLU()
            self.dropout   = nn.Dropout(0.0)   # inference: no dropout
            self.fc2       = nn.Linear(hidden_dim, num_classes)

        def forward(self, x):
            import torch
            mask   = (x != 0).float().unsqueeze(-1)
            emb    = self.embedding(x)
            pooled = (emb * mask).sum(1) / mask.sum(1).clamp(min=1)
            return self.fc2(self.relu(self.fc1(pooled)))

    return _Model()


# ── Classifier class ──────────────────────────────────────────────────────────

class IntentClassifier:
    """
    Singleton wrapper around the trained PyTorch intent model.

    Attributes:
        available (bool): True when the model is loaded successfully.
    """

    def __init__(self):
        self.available = False
        self._model     = None
        self._vocab: dict      = {}
        self._labels: List[str] = []
        self._ngram_sizes: List[int] = [1, 2, 3]
        self._torch = None
        self._load()

    def _load(self):
        model_pt  = MODEL_DIR / "model.pt"
        vocab_f   = MODEL_DIR / "vocab.json"
        meta_f    = MODEL_DIR / "meta.json"

        if not model_pt.exists():
            logger.debug("Intent model not found at %s — rule-based fallback active", model_pt)
            return

        try:
            import torch
            self._torch = torch

            with open(vocab_f, encoding="utf-8") as f:
                self._vocab = json.load(f)
            with open(meta_f, encoding="utf-8") as f:
                meta = json.load(f)

            self._labels      = meta["labels"]
            self._ngram_sizes = meta.get("ngram_sizes", [1, 2, 3])
            embed_dim         = meta["embed_dim"]
            hidden_dim        = meta["hidden_dim"]
            vocab_size        = meta["vocab_size"]

            model = _build_model(vocab_size, embed_dim, hidden_dim, len(self._labels))
            model.load_state_dict(torch.load(model_pt, map_location="cpu", weights_only=True))
            model.eval()
            self._model   = model
            self.available = True
            logger.info(
                "IntentClassifier loaded (test_acc=%.1f%%)",
                (meta.get("test_acc") or 0) * 100,
            )
        except Exception as exc:
            logger.warning("Failed to load intent classifier: %s", exc)

    def predict(self, text: str) -> Tuple[str, float]:
        """
        Returns (intent_label, confidence).
        Raises RuntimeError if model is not available.
        """
        if not self.available:
            raise RuntimeError("IntentClassifier not available")

        import torch
        import torch.nn.functional as F

        ids = _encode(text, self._vocab, self._ngram_sizes)
        if not ids:
            return self._labels[-1], 0.0   # fall back to "ask"

        x      = torch.tensor([ids], dtype=torch.long)
        with torch.no_grad():
            logits = self._model(x)
            probs  = F.softmax(logits, dim=-1)[0]
            idx    = int(probs.argmax())
        return self._labels[idx], float(probs[idx])


def get_classifier() -> IntentClassifier:
    """Return the cached singleton classifier."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = IntentClassifier()
    return _INSTANCE
