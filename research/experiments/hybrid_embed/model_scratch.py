"""WP2 — encoder/decoder transformer written from scratch.

torch is used as a tensor/autograd library only: attention, blocks, and the
seq2seq wiring are implemented here (no nn.Transformer*, no nn.MultiheadAttention).

Design, sized for a ~25K-running-token corpus:
  * pre-norm blocks, learned positional embeddings
  * one embedding matrix shared by encoder input, decoder input, and the
    output projection (three-way weight tying — the single biggest
    overfitting lever at this corpus size)
  * encoder returns per-token states (late interaction, WP3) and a masked
    mean-pool (fusion block)
  * decoder is standard causal + cross-attention; used for denoising
    reconstruction and later for lacuna restoration (WP5/WP8)
"""

from __future__ import annotations

import math

import torch
import torch.nn as nn
import torch.nn.functional as F

PAD = 0


class MultiHeadAttention(nn.Module):
    def __init__(self, d_model: int, n_heads: int, dropout: float):
        super().__init__()
        assert d_model % n_heads == 0
        self.h = n_heads
        self.dk = d_model // n_heads
        self.wq = nn.Linear(d_model, d_model, bias=False)
        self.wk = nn.Linear(d_model, d_model, bias=False)
        self.wv = nn.Linear(d_model, d_model, bias=False)
        self.wo = nn.Linear(d_model, d_model, bias=False)
        self.drop = nn.Dropout(dropout)

    def forward(self, q, kv, key_pad_mask=None, causal=False):
        B, Tq, D = q.shape
        Tk = kv.size(1)
        Q = self.wq(q).view(B, Tq, self.h, self.dk).transpose(1, 2)
        K = self.wk(kv).view(B, Tk, self.h, self.dk).transpose(1, 2)
        V = self.wv(kv).view(B, Tk, self.h, self.dk).transpose(1, 2)
        scores = Q @ K.transpose(-2, -1) / math.sqrt(self.dk)  # [B,h,Tq,Tk]
        if key_pad_mask is not None:  # [B,Tk] True = pad
            scores = scores.masked_fill(key_pad_mask[:, None, None, :], -1e9)
        if causal:
            cm = torch.triu(torch.ones(Tq, Tk, dtype=torch.bool, device=q.device), 1)
            scores = scores.masked_fill(cm, -1e9)
        attn = self.drop(F.softmax(scores, dim=-1))
        out = (attn @ V).transpose(1, 2).contiguous().view(B, Tq, D)
        return self.wo(out)


class FFN(nn.Module):
    def __init__(self, d_model: int, d_ff: int, dropout: float):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(d_model, d_ff), nn.GELU(), nn.Dropout(dropout),
            nn.Linear(d_ff, d_model),
        )

    def forward(self, x):
        return self.net(x)


class EncoderBlock(nn.Module):
    def __init__(self, d_model, n_heads, d_ff, dropout):
        super().__init__()
        self.n1, self.n2 = nn.LayerNorm(d_model), nn.LayerNorm(d_model)
        self.attn = MultiHeadAttention(d_model, n_heads, dropout)
        self.ffn = FFN(d_model, d_ff, dropout)
        self.drop = nn.Dropout(dropout)

    def forward(self, x, pad_mask):
        h = self.n1(x)
        x = x + self.drop(self.attn(h, h, key_pad_mask=pad_mask))
        x = x + self.drop(self.ffn(self.n2(x)))
        return x


class DecoderBlock(nn.Module):
    def __init__(self, d_model, n_heads, d_ff, dropout):
        super().__init__()
        self.n1, self.n2, self.n3 = (nn.LayerNorm(d_model) for _ in range(3))
        self.self_attn = MultiHeadAttention(d_model, n_heads, dropout)
        self.cross_attn = MultiHeadAttention(d_model, n_heads, dropout)
        self.ffn = FFN(d_model, d_ff, dropout)
        self.drop = nn.Dropout(dropout)

    def forward(self, y, mem, y_pad_mask, mem_pad_mask):
        h = self.n1(y)
        y = y + self.drop(self.self_attn(h, h, key_pad_mask=y_pad_mask, causal=True))
        h = self.n2(y)
        y = y + self.drop(self.cross_attn(h, mem, key_pad_mask=mem_pad_mask))
        y = y + self.drop(self.ffn(self.n3(y)))
        return y


class Seq2Seq(nn.Module):
    def __init__(self, vocab_size: int, d_model: int = 128, n_heads: int = 4,
                 n_enc: int = 3, n_dec: int = 3, d_ff: int = 256,
                 dropout: float = 0.15, max_len: int = 64):
        super().__init__()
        self.d_model = d_model
        self.max_len = max_len
        self.emb = nn.Embedding(vocab_size, d_model, padding_idx=PAD)
        # tied three ways (encoder in, decoder in, output projection): default
        # N(0,1) init makes the tied logits explode — 0.02 keeps them sane
        nn.init.normal_(self.emb.weight, std=0.02)
        nn.init.zeros_(self.emb.weight[PAD])
        self.pos_enc_emb = nn.Parameter(torch.zeros(1, max_len, d_model))
        self.pos_dec_emb = nn.Parameter(torch.zeros(1, max_len, d_model))
        nn.init.normal_(self.pos_enc_emb, std=0.02)
        nn.init.normal_(self.pos_dec_emb, std=0.02)
        self.encoder = nn.ModuleList(
            [EncoderBlock(d_model, n_heads, d_ff, dropout) for _ in range(n_enc)])
        self.decoder = nn.ModuleList(
            [DecoderBlock(d_model, n_heads, d_ff, dropout) for _ in range(n_dec)])
        self.enc_norm = nn.LayerNorm(d_model)
        self.dec_norm = nn.LayerNorm(d_model)
        self.out_bias = nn.Parameter(torch.zeros(vocab_size))
        self.drop = nn.Dropout(dropout)

    def encode(self, x):
        """x: [B,T] -> (states [B,T,D], pad_mask [B,T])"""
        pad_mask = x == PAD
        h = self.drop(self.emb(x) + self.pos_enc_emb[:, : x.size(1)])
        for blk in self.encoder:
            h = blk(h, pad_mask)
        return self.enc_norm(h), pad_mask

    def pool(self, states, pad_mask):
        m = (~pad_mask).unsqueeze(-1).float()
        return (states * m).sum(1) / m.sum(1).clamp(min=1)

    def decode(self, y, mem, mem_pad_mask, return_hidden: bool = False):
        """y: [B,Ty] decoder input ids -> logits [B,Ty,V] (tied projection)."""
        y_pad = y == PAD
        h = self.drop(self.emb(y) + self.pos_dec_emb[:, : y.size(1)])
        for blk in self.decoder:
            h = blk(h, mem, y_pad, mem_pad_mask)
        h = self.dec_norm(h)
        logits = h @ self.emb.weight.T + self.out_bias
        if return_hidden:
            return logits, h
        return logits

    def forward(self, x, y_in):
        mem, mem_pad = self.encode(x)
        return self.decode(y_in, mem, mem_pad)
