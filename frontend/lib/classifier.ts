/**
 * ONNX Classifier Engine - ported from web/classifier.js
 *
 * Runs CNN and Transformer models client-side via onnxruntime-web (WASM).
 * Both models share the same vocab, max_len, and 7-class label set.
 */

import * as ort from "onnxruntime-web";

export interface ModelMeta {
  arch: string;
  max_len: number;
  labels: string[];
  vocab: {
    char_to_idx: Record<string, number>;
    vocab_size: number;
  };
}

export interface ClassificationResult {
  label: string;
  probability: number;
}

export interface ClassifierOutput {
  arch: string;
  predictions: ClassificationResult[];
  inferenceMs: number;
}

/** Epigraphic type descriptions (academic) */
export const CLASS_DESCRIPTIONS: Record<string, string> = {
  funerary:
    "Tomb inscriptions, epitaphs, and funerary monuments. Contains death/life formulae, kinship terms, and age markers.",
  votive:
    "Offerings to deities. Contains dedication verbs (turce, mulvanice), gift terms (alpan), and divine epithets.",
  boundary:
    "Boundary stones and territorial markers. Contains civic terms (spura, tular, rasna) and district designations.",
  ownership:
    'Object ownership marks. Typically begins with "mi" (I am) followed by the owner\'s name.',
  legal:
    "Administrative and legal texts. Contains magistrate titles (zilχ, marunuχ) and official terminology.",
  commercial:
    "Trade and commercial records. Contains numerals, weights, measures, and vessel terminology.",
  dedicatory:
    "Temple dedications and sacred texts. Contains deity names from the Etruscan pantheon.",
};

function softmax(logits: number[]): number[] {
  const max = Math.max(...logits);
  const exps = logits.map((x) => Math.exp(x - max));
  const sum = exps.reduce((a, b) => a + b, 0);
  return exps.map((x) => x / sum);
}

function tokenize(text: string, meta: ModelMeta): bigint[] {
  const charToIdx = meta.vocab.char_to_idx;
  const maxLen = meta.max_len;
  const lower = text.toLowerCase();
  const ids: bigint[] = [];

  for (let i = 0; i < Math.min(lower.length, maxLen); i++) {
    const ch = lower[i];
    const idx = charToIdx[ch];
    ids.push(BigInt(idx !== undefined ? idx : 1)); // 1 = [UNK]
  }
  while (ids.length < maxLen) ids.push(BigInt(0)); // 0 = [PAD]

  return ids;
}

export async function loadAndClassify(
  text: string,
  modelName: "cnn" | "transformer"
): Promise<ClassifierOutput> {
  // Load metadata
  const metaRes = await fetch(`/models/${modelName}.json`);
  if (!metaRes.ok) throw new Error(`Cannot load ${modelName} metadata`);
  const meta: ModelMeta = await metaRes.json();

  // Load ONNX session
  const session = await ort.InferenceSession.create(
    `/models/${modelName}.onnx`,
    { executionProviders: ["wasm"] }
  );

  // Tokenize and run
  const ids = tokenize(text, meta);
  const inputTensor = new ort.Tensor(
    "int64",
    new BigInt64Array(ids),
    [1, meta.max_len]
  );

  const t0 = performance.now();
  const results = await session.run({ input: inputTensor });
  const inferenceMs = performance.now() - t0;

  const logits = Array.from(results.logits.data as Float32Array);
  const probs = softmax(logits);

  const predictions = meta.labels
    .map((label, i) => ({ label, probability: probs[i] }))
    .sort((a, b) => b.probability - a.probability);

  return {
    arch: modelName === "cnn" ? "CharCNN" : "Transformer",
    predictions,
    inferenceMs,
  };
}
