"""
Train a PyTorch intent classifier for FundPilot router.

Architecture:
  Character-level n-gram bag-of-features → Embedding lookup → mean pool → MLP

This approach works well for short Chinese/English queries without needing
a large pretrained model download.

Run:
    python tools/train_intent_classifier.py
Outputs:
    data/intent_model/vocab.json
    data/intent_model/model.pt
    data/intent_model/meta.json
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import List, Tuple

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, Dataset

# ── Config ────────────────────────────────────────────────────────────────────

LABELS      = ["overlap", "compare", "portfolio", "ask"]
LABEL2ID    = {l: i for i, l in enumerate(LABELS)}
ID2LABEL    = {i: l for l, i in LABEL2ID.items()}

NGRAM_SIZES = [1, 2, 3]   # character n-grams
VOCAB_SIZE  = 8000         # cap vocabulary
EMBED_DIM   = 64
HIDDEN_DIM  = 128
DROPOUT     = 0.3

EPOCHS      = 40
BATCH_SIZE  = 32
LR          = 2e-3

BASE_DIR    = Path(__file__).resolve().parent.parent
DATA_DIR    = BASE_DIR / "data"
MODEL_DIR   = DATA_DIR / "intent_model"


# ── Text → features ───────────────────────────────────────────────────────────

def extract_ngrams(text: str, sizes: List[int] = NGRAM_SIZES) -> List[str]:
    """Extract character n-grams from text (lowercased)."""
    t = text.lower().strip()
    ngrams: List[str] = []
    for n in sizes:
        for i in range(len(t) - n + 1):
            ngrams.append(t[i:i + n])
    return ngrams


def build_vocab(examples: List[dict], max_size: int = VOCAB_SIZE) -> dict:
    counter: Counter = Counter()
    for ex in examples:
        counter.update(extract_ngrams(ex["text"]))
    vocab = {"<PAD>": 0, "<UNK>": 1}
    for token, _ in counter.most_common(max_size - 2):
        vocab[token] = len(vocab)
    return vocab


def encode(text: str, vocab: dict, max_len: int = 200) -> List[int]:
    ngrams = extract_ngrams(text)[:max_len]
    return [vocab.get(g, vocab["<UNK>"]) for g in ngrams]


# ── Dataset ───────────────────────────────────────────────────────────────────

class IntentDataset(Dataset):
    def __init__(self, examples: List[dict], vocab: dict, max_len: int = 200):
        self.vocab   = vocab
        self.max_len = max_len
        self.data = [
            (encode(ex["text"], vocab, max_len), LABEL2ID[ex["label"]])
            for ex in examples
        ]

    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, int]:
        ids, label = self.data[idx]
        return torch.tensor(ids, dtype=torch.long), label


def collate_fn(batch):
    texts, labels = zip(*batch)
    max_len = max(t.size(0) for t in texts)
    padded = torch.zeros(len(texts), max_len, dtype=torch.long)
    for i, t in enumerate(texts):
        padded[i, : t.size(0)] = t
    return padded, torch.tensor(labels, dtype=torch.long)


# ── Model ─────────────────────────────────────────────────────────────────────

class IntentClassifier(nn.Module):
    def __init__(
        self,
        vocab_size: int,
        embed_dim: int,
        hidden_dim: int,
        num_classes: int,
        dropout: float = 0.3,
    ):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embed_dim, padding_idx=0)
        self.fc1       = nn.Linear(embed_dim, hidden_dim)
        self.relu      = nn.ReLU()
        self.dropout   = nn.Dropout(dropout)
        self.fc2       = nn.Linear(hidden_dim, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, seq_len)
        mask   = (x != 0).float().unsqueeze(-1)          # (B, L, 1)
        emb    = self.embedding(x)                        # (B, L, E)
        pooled = (emb * mask).sum(1) / mask.sum(1).clamp(min=1)  # mean pool
        out    = self.fc1(pooled)
        out    = self.relu(out)
        out    = self.dropout(out)
        out    = self.fc2(out)
        return out


# ── Train / eval ──────────────────────────────────────────────────────────────

def load_jsonl(path: Path) -> List[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def evaluate(model: nn.Module, loader: DataLoader, device: torch.device) -> float:
    model.eval()
    correct = total = 0
    with torch.no_grad():
        for x, y in loader:
            x, y = x.to(device), y.to(device)
            preds = model(x).argmax(dim=-1)
            correct += (preds == y).sum().item()
            total   += y.size(0)
    model.train()
    return correct / total if total else 0.0


def train():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    train_path = DATA_DIR / "intent_train.jsonl"
    test_path  = DATA_DIR / "intent_test.jsonl"

    if not train_path.exists():
        raise FileNotFoundError(
            f"{train_path} not found. Run generate_training_data.py first."
        )

    train_data = load_jsonl(train_path)
    test_data  = load_jsonl(test_path) if test_path.exists() else []

    print(f"Train: {len(train_data)} examples | Test: {len(test_data)} examples")

    vocab = build_vocab(train_data)
    print(f"Vocabulary size: {len(vocab)}")

    # Save vocab
    with open(MODEL_DIR / "vocab.json", "w", encoding="utf-8") as f:
        json.dump(vocab, f, ensure_ascii=False)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    train_ds = IntentDataset(train_data, vocab)
    train_loader = DataLoader(
        train_ds, batch_size=BATCH_SIZE, shuffle=True, collate_fn=collate_fn
    )

    test_loader = None
    if test_data:
        test_ds = IntentDataset(test_data, vocab)
        test_loader = DataLoader(
            test_ds, batch_size=BATCH_SIZE, shuffle=False, collate_fn=collate_fn
        )

    model = IntentClassifier(
        vocab_size=len(vocab),
        embed_dim=EMBED_DIM,
        hidden_dim=HIDDEN_DIM,
        num_classes=len(LABELS),
        dropout=DROPOUT,
    ).to(device)

    optimizer  = optim.Adam(model.parameters(), lr=LR)
    scheduler  = optim.lr_scheduler.StepLR(optimizer, step_size=15, gamma=0.5)
    criterion  = nn.CrossEntropyLoss()

    t0 = time.time()
    for epoch in range(1, EPOCHS + 1):
        total_loss = 0.0
        for x, y in train_loader:
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad()
            loss = criterion(model(x), y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        scheduler.step()

        if epoch % 5 == 0 or epoch == EPOCHS:
            msg = f"Epoch {epoch:02d}/{EPOCHS}  loss={total_loss:.4f}"
            if test_loader:
                acc = evaluate(model, test_loader, device)
                msg += f"  test_acc={acc:.1%}"
            print(msg)

    elapsed = time.time() - t0
    print(f"Training done in {elapsed:.1f}s")

    # Final accuracy
    train_acc = evaluate(model, train_loader, device)
    print(f"Train accuracy : {train_acc:.1%}")
    if test_loader:
        test_acc = evaluate(model, test_loader, device)
        print(f"Test accuracy  : {test_acc:.1%}")
    else:
        test_acc = None

    # Save model
    torch.save(model.state_dict(), MODEL_DIR / "model.pt")

    meta = {
        "labels":     LABELS,
        "label2id":   LABEL2ID,
        "vocab_size": len(vocab),
        "embed_dim":  EMBED_DIM,
        "hidden_dim": HIDDEN_DIM,
        "ngram_sizes": NGRAM_SIZES,
        "train_acc":  round(train_acc, 4),
        "test_acc":   round(test_acc, 4) if test_acc is not None else None,
        "train_size": len(train_data),
        "test_size":  len(test_data),
    }
    with open(MODEL_DIR / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"Model saved → {MODEL_DIR}/model.pt")
    print(f"Meta  saved → {MODEL_DIR}/meta.json")

    # Quick per-class accuracy
    if test_loader:
        print("\nPer-class accuracy on test set:")
        model.eval()
        class_correct = [0] * len(LABELS)
        class_total   = [0] * len(LABELS)
        with torch.no_grad():
            for x, y in test_loader:
                x, y = x.to(device), y.to(device)
                preds = model(x).argmax(dim=-1)
                for pred, true in zip(preds.cpu(), y.cpu()):
                    class_total[true] += 1
                    class_correct[true] += int(pred == true)
        for i, label in enumerate(LABELS):
            n = class_total[i]
            c = class_correct[i]
            print(f"  {label:12s}: {c}/{n}  ({c/n:.1%})" if n else f"  {label:12s}: N/A")

    # Rule-based baseline for comparison
    print("\nRule-based baseline (for comparison):")
    _eval_rule_based(test_data if test_data else train_data)


def _eval_rule_based(examples: List[dict]):
    """Evaluate the existing regex router against the labeled data."""
    import sys
    sys.path.insert(0, str(BASE_DIR))
    try:
        from core.router import classify_intent
        correct = total = 0
        for ex in examples:
            pred_intent, _ = classify_intent(ex["text"], [])
            if pred_intent == ex["label"]:
                correct += 1
            total += 1
        print(f"  Rule-based accuracy: {correct}/{total} ({correct/total:.1%})")
    except Exception as e:
        print(f"  Could not evaluate rule-based: {e}")


if __name__ == "__main__":
    train()
