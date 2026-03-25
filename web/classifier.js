/* =====================================================================
   classifier.js — In-Browser ONNX Neural Classifier
   Runs the CharCNN model entirely client-side via onnxruntime-web (WASM).
   Zero API calls, zero server dependency, full privacy.
   ===================================================================== */

let classifierSession = null;
let classifierMeta = null;
let classifierReady = false;

const CLASS_COLORS = {
    funerary:    { bg: 'rgba(248,113,113,0.12)', border: '#f87171', text: '#f87171' },
    votive:      { bg: 'rgba(251,191,36,0.12)',  border: '#fbbf24', text: '#fbbf24' },
    boundary:    { bg: 'rgba(99,149,242,0.12)',  border: '#6395f2', text: '#6395f2' },
    ownership:   { bg: 'rgba(196,112,75,0.12)',  border: '#c4704b', text: '#d4855f' },
    legal:       { bg: 'rgba(192,132,252,0.12)', border: '#c084fc', text: '#c084fc' },
    commercial:  { bg: 'rgba(74,222,128,0.12)',  border: '#4ade80', text: '#4ade80' },
    dedicatory:  { bg: 'rgba(244,114,182,0.12)', border: '#f472b6', text: '#f472b6' },
};

const CLASS_ICONS = {
    funerary:   '⚱️',
    votive:     '🏛️',
    boundary:   '🗿',
    ownership:  '✋',
    legal:      '⚖️',
    commercial: '🏺',
    dedicatory: '🙏',
};

const CLASS_DESCRIPTIONS = {
    funerary:   'Tomb inscriptions, epitaphs, and funerary monuments. Contains death/life formulae, kinship terms, and age markers.',
    votive:     'Offerings to deities. Contains dedication verbs (turce, mulvanice), gift terms (alpan), and divine epithets.',
    boundary:   'Boundary stones and territorial markers. Contains civic terms (spura, tular, rasna) and district designations.',
    ownership:  'Object ownership marks. Typically starts with "mi" (I am) followed by the owner name.',
    legal:      'Administrative and legal texts. Contains magistrate titles (zilχ, marunuχ) and official terminology.',
    commercial: 'Trade and commercial records. Contains numerals, weights, measures, and vessel terminology.',
    dedicatory: 'Temple dedications and sacred texts. Contains deity names from the Etruscan pantheon.',
};

// ── Load ONNX Model ─────────────────────────────────────────────────
async function initClassifier() {
    const statusEl = document.getElementById('classifierStatus');
    statusEl.textContent = 'Loading model…';
    statusEl.className = 'classifier-status loading';

    try {
        // Load metadata (vocab + labels)
        const metaRes = await fetch('models/cnn.json');
        if (!metaRes.ok) throw new Error('Cannot load model metadata');
        classifierMeta = await metaRes.json();

        // Load ONNX session
        classifierSession = await ort.InferenceSession.create('models/cnn.onnx', {
            executionProviders: ['wasm'],
        });

        classifierReady = true;
        statusEl.textContent = `Model loaded · ${classifierMeta.vocab_size} chars · ${classifierMeta.labels.length} classes`;
        statusEl.className = 'classifier-status ready';

        // Enable the button
        document.getElementById('classifyBtn').disabled = false;
    } catch (err) {
        statusEl.textContent = 'Failed to load model: ' + err.message;
        statusEl.className = 'classifier-status error';
        console.error('ONNX load error:', err);
    }
}

// ── Tokenize Text ───────────────────────────────────────────────────
function tokenize(text) {
    const charToIdx = classifierMeta.vocab.char_to_idx;
    const maxLen = classifierMeta.max_len;
    const lower = text.toLowerCase();
    const ids = [];

    for (let i = 0; i < Math.min(lower.length, maxLen); i++) {
        const ch = lower[i];
        ids.push(charToIdx[ch] !== undefined ? charToIdx[ch] : 1); // 1 = [UNK]
    }
    // Pad to max_len
    while (ids.length < maxLen) ids.push(0); // 0 = [PAD]

    return ids;
}

// ── Softmax ─────────────────────────────────────────────────────────
function softmax(logits) {
    const max = Math.max(...logits);
    const exps = logits.map(x => Math.exp(x - max));
    const sum = exps.reduce((a, b) => a + b, 0);
    return exps.map(x => x / sum);
}

// ── Run Classification ──────────────────────────────────────────────
async function classifyInscription() {
    if (!classifierReady) return;

    const text = document.getElementById('classifierInput').value.trim();
    if (!text) return;

    const btn = document.getElementById('classifyBtn');
    btn.classList.add('btn-loading');

    try {
        const ids = tokenize(text);
        const inputTensor = new ort.Tensor('int64', BigInt64Array.from(ids.map(BigInt)), [1, classifierMeta.max_len]);

        const results = await classifierSession.run({ input: inputTensor });
        const logits = Array.from(results.logits.data);
        const probs = softmax(logits);

        renderResults(text, probs);
    } catch (err) {
        console.error('Classification error:', err);
        document.getElementById('classifierResults').innerHTML =
            `<div style="color:#f87171; padding:1rem;">Error: ${err.message}</div>`;
    } finally {
        btn.classList.remove('btn-loading');
    }
}

// ── Render Results ──────────────────────────────────────────────────
function renderResults(text, probs) {
    const labels = classifierMeta.labels;
    const ranked = labels.map((label, i) => ({ label, prob: probs[i] }))
        .sort((a, b) => b.prob - a.prob);

    const top = ranked[0];
    const colors = CLASS_COLORS[top.label] || CLASS_COLORS.ownership;
    const icon = CLASS_ICONS[top.label] || '📜';
    const desc = CLASS_DESCRIPTIONS[top.label] || '';

    let html = `
        <div class="classify-result-card">
            <div class="classify-verdict">
                <span class="classify-icon">${icon}</span>
                <div class="classify-verdict-text">
                    <span class="classify-label" style="color:${colors.text}">${top.label.toUpperCase()}</span>
                    <span class="classify-confidence">${(top.prob * 100).toFixed(1)}% confidence</span>
                </div>
            </div>
            <div class="classify-description">${desc}</div>
            <div class="classify-input-echo">
                <span class="classify-echo-label">Input</span>
                <span class="classify-echo-text">${escClassifier(text)}</span>
            </div>
            <div class="classify-bars">`;

    for (const item of ranked) {
        const c = CLASS_COLORS[item.label] || CLASS_COLORS.ownership;
        const pct = (item.prob * 100).toFixed(1);
        const barWidth = Math.max(2, item.prob * 100);
        html += `
            <div class="classify-bar-row">
                <span class="classify-bar-label">${CLASS_ICONS[item.label] || ''} ${item.label}</span>
                <div class="classify-bar-track">
                    <div class="classify-bar-fill" style="width:${barWidth}%; background:${c.border};"></div>
                </div>
                <span class="classify-bar-pct" style="color:${c.text}">${pct}%</span>
            </div>`;
    }

    html += `</div></div>`;
    document.getElementById('classifierResults').innerHTML = html;
}

function escClassifier(s) {
    const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
    return s ? String(s).replace(/[&<>"']/g, c => map[c]) : '';
}

// ── Example Loader ──────────────────────────────────────────────────
const CLASSIFIER_EXAMPLES = [
    { text: 'mi araθia velθurus', desc: 'Ownership mark' },
    { text: 'arnθ cutnas zilcte lupu', desc: 'Funerary (magistrate death)' },
    { text: 'turce menrvas alpan', desc: 'Votive offering' },
    { text: 'tular rasna spural', desc: 'Boundary marker' },
    { text: 'tinia uni menerva', desc: 'Dedicatory (Capitoline triad)' },
    { text: 'zilχ marunuχ cepen tenu', desc: 'Legal (magistrate titles)' },
    { text: 'zal ci pruχ aska', desc: 'Commercial (trade goods)' },
];

function loadClassifierExample(idx) {
    document.getElementById('classifierInput').value = CLASSIFIER_EXAMPLES[idx].text;
    classifyInscription();
}
