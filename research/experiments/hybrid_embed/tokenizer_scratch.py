#!/usr/bin/env python3
"""WP1 — subword tokenizer implemented from scratch (no external tokenizer
library). Byte/char-level BPE with an end-of-word marker.

Trained on the deduplicated training split only, so repeated formulae do not
bias the merges. The end-of-word marker (▁ appended to the final char of
each word) lets suffix pieces like ``al</w>`` ``us</w>`` ``isa</w>`` — the
Etruscan genitive chain — become single tokens, which is the morphology we
want the encoder to see.

API:
    tok = BPETokenizer.train(texts, vocab_size=1000)
    ids = tok.encode(text)          # list[int], no padding
    text = tok.decode(ids)
    tok.save(path) / BPETokenizer.load(path)

Special ids: 0=[PAD], 1=[UNK], 2=[MASK], 3=[BOS], 4=[EOS].

Run as a script: trains on out/train.csv, writes out/bpe_tokenizer.json and
prints fertility + a suffix-emergence table (the WP1 gate).
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

EOW = "▁"  # appended to the last char of every word
SPECIALS = ["[PAD]", "[UNK]", "[MASK]", "[BOS]", "[EOS]"]
PAD, UNK, MASK, BOS, EOS = range(5)
WORD_SEP = re.compile(r"\s+")


class BPETokenizer:
    def __init__(self, merges: list[tuple[str, str]], vocab: dict[str, int]):
        self.merges = merges
        self.vocab = vocab
        self.inv_vocab = {v: k for k, v in vocab.items()}
        self.merge_rank = {pair: i for i, pair in enumerate(merges)}
        self._cache: dict[str, list[str]] = {}

    # -------------------------------------------------------------- training
    @classmethod
    def train(cls, texts: list[str], vocab_size: int = 1000) -> "BPETokenizer":
        word_freq: Counter = Counter()
        for t in texts:
            for w in WORD_SEP.split(t.strip().lower()):
                if w:
                    word_freq[w] += 1

        # each word as a tuple of symbols; last char carries the EOW marker
        words: dict[tuple[str, ...], int] = {}
        for w, f in word_freq.items():
            syms = tuple(list(w[:-1]) + [w[-1] + EOW])
            words[syms] = words.get(syms, 0) + f

        alphabet = sorted({s for syms in words for s in syms})
        merges: list[tuple[str, str]] = []
        n_base = len(SPECIALS) + len(alphabet)

        while n_base + len(merges) < vocab_size:
            pairs: Counter = Counter()
            for syms, f in words.items():
                for a, b in zip(syms, syms[1:]):
                    pairs[(a, b)] += f
            if not pairs:
                break
            (a, b), freq = pairs.most_common(1)[0]
            if freq < 2:
                break
            merges.append((a, b))
            merged = a + b
            new_words: dict[tuple[str, ...], int] = {}
            for syms, f in words.items():
                out = []
                i = 0
                while i < len(syms):
                    if i < len(syms) - 1 and syms[i] == a and syms[i + 1] == b:
                        out.append(merged)
                        i += 2
                    else:
                        out.append(syms[i])
                        i += 1
                key = tuple(out)
                new_words[key] = new_words.get(key, 0) + f
            words = new_words

        pieces = sorted({s for syms in words for s in syms} | set(alphabet)
                        | {a + b for a, b in merges})
        vocab = {sp: i for i, sp in enumerate(SPECIALS)}
        for p in pieces:
            vocab[p] = len(vocab)
        return cls(merges, vocab)

    # -------------------------------------------------------------- encoding
    def _bpe_word(self, word: str) -> list[str]:
        if word in self._cache:
            return self._cache[word]
        syms = list(word[:-1]) + [word[-1] + EOW]
        while len(syms) > 1:
            best, best_rank = None, None
            for i, pair in enumerate(zip(syms, syms[1:])):
                r = self.merge_rank.get(pair)
                if r is not None and (best_rank is None or r < best_rank):
                    best, best_rank = i, r
            if best is None:
                break
            syms[best : best + 2] = [syms[best] + syms[best + 1]]
        self._cache[word] = syms
        return syms

    def encode(self, text: str, bos_eos: bool = False) -> list[int]:
        ids = [BOS] if bos_eos else []
        for w in WORD_SEP.split(text.strip().lower()):
            if w:
                ids += [self.vocab.get(p, UNK) for p in self._bpe_word(w)]
        if bos_eos:
            ids.append(EOS)
        return ids

    def decode(self, ids: list[int]) -> str:
        out = []
        for i in ids:
            p = self.inv_vocab.get(i, "")
            if p in SPECIALS:
                continue
            out.append(p)
        return "".join(out).replace(EOW, " ").strip()

    def tokens(self, text: str) -> list[str]:
        return [self.inv_vocab[i] for i in self.encode(text)]

    def __len__(self) -> int:
        return len(self.vocab)

    # -------------------------------------------------------------- persistence
    def save(self, path: Path) -> None:
        path.write_text(json.dumps(
            {"merges": self.merges, "vocab": self.vocab}, ensure_ascii=False))

    @classmethod
    def load(cls, path: Path) -> "BPETokenizer":
        d = json.loads(path.read_text())
        return cls([tuple(m) for m in d["merges"]], d["vocab"])


def main() -> None:
    import pandas as pd

    here = Path(__file__).parent
    out = here / "out"
    train_df = pd.read_csv(out / "train.csv", dtype={"surface": str})
    texts = train_df["surface"].fillna("")
    texts = [t for t in texts if t]

    tok = BPETokenizer.train(texts, vocab_size=1000)
    tok.save(out / "bpe_tokenizer.json")

    n_words = sum(len(t.split()) for t in texts)
    n_pieces = sum(len(tok.encode(t)) for t in texts)
    print(f"vocab {len(tok)} | words {n_words:,} | pieces {n_pieces:,} | "
          f"fertility {n_pieces / n_words:.2f} pieces/word")

    # WP1 gate: do genitive suffixes emerge as single pieces?
    suffixes = ["al" + EOW, "us" + EOW, "isa" + EOW, "śa" + EOW, "s" + EOW,
                "ial" + EOW, "es" + EOW, "sa" + EOW]
    print("suffix pieces in vocab:",
          {s.replace(EOW, "</w>"): (s in tok.vocab) for s in suffixes})

    for demo in ["mi mulu larisale velχainasi", "larθ velus clan", "θania pulfnei tutnasa"]:
        print(f"  {demo!r} -> {[t.replace(EOW,'</w>') for t in tok.tokens(demo)]}")

    roundtrip_fail = sum(tok.decode(tok.encode(t)) != " ".join(t.lower().split()) for t in texts)
    print(f"round-trip failures: {roundtrip_fail}/{len(texts)}")


if __name__ == "__main__":
    main()
