/**
 * OpenEtruscan Web Converter — app.js
 *
 * Self-contained normalizer running entirely in the browser.
 * No backend, no API calls, no data leaves the user's machine.
 */

// =============================================================================
// ETRUSCAN ALPHABET MAPPING (mirroring etruscan.yaml)
// =============================================================================

const ALPHABET = {
    a: { unicode: '\u{10300}', ipa: 'a', variants: ['A', 'a'] },
    c: { unicode: '\u{10302}', ipa: 'k', variants: ['C', 'c'] },
    e: { unicode: '\u{10304}', ipa: 'e', variants: ['E', 'e'] },
    v: { unicode: '\u{10305}', ipa: 'v', variants: ['V', 'v', 'w', 'W'] },
    z: { unicode: '\u{10306}', ipa: 'ts', variants: ['Z'] },
    h: { unicode: '\u{10307}', ipa: 'h', variants: ['H'] },
    'θ': { unicode: '\u{10308}', ipa: 'tʰ', variants: ['θ', 'Θ'] },
    i: { unicode: '\u{10309}', ipa: 'i', variants: ['I', 'i'] },
    k: { unicode: '\u{1030A}', ipa: 'k', variants: ['K'] },
    l: { unicode: '\u{1030B}', ipa: 'l', variants: ['L', 'l'] },
    m: { unicode: '\u{1030C}', ipa: 'm', variants: ['M', 'm'] },
    n: { unicode: '\u{1030D}', ipa: 'n', variants: ['N', 'n'] },
    p: { unicode: '\u{10310}', ipa: 'p', variants: ['P', 'p'] },
    'ś': { unicode: '\u{10311}', ipa: 'ʃ', variants: ['Ś', 'ś'] },
    q: { unicode: '\u{10312}', ipa: 'k', variants: ['Q', 'q'] },
    r: { unicode: '\u{10313}', ipa: 'r', variants: ['R', 'r'] },
    s: { unicode: '\u{10314}', ipa: 's', variants: ['S', 's'] },
    t: { unicode: '\u{10315}', ipa: 't', variants: ['T', 't'] },
    u: { unicode: '\u{10316}', ipa: 'u', variants: ['U', 'u'] },
    'φ': { unicode: '\u{10318}', ipa: 'pʰ', variants: ['φ', 'Φ'] },
    'χ': { unicode: '\u{10317}', ipa: 'kʰ', variants: ['χ', 'Χ'] },
    f: { unicode: '\u{1031A}', ipa: 'f', variants: ['F', 'f'] },
};

// Multi-character equivalence classes (tried first, longest match)
const DIGRAPHS = {
    'th': 'θ', 'TH': 'θ', 'Th': 'θ',
    'ph': 'φ', 'PH': 'φ', 'Ph': 'φ',
    'ch': 'χ', 'CH': 'χ', 'Ch': 'χ',
    'kh': 'χ', 'KH': 'χ', 'Kh': 'χ',
    'sh': 'ś', 'SH': 'ś', 'Sh': 'ś',
};

// Build reverse lookup tables
const variantToCanonical = {};
const canonicalToUnicode = {};
const canonicalToIPA = {};
const unicodeToCanonical = {};

for (const [canonical, data] of Object.entries(ALPHABET)) {
    canonicalToUnicode[canonical] = data.unicode;
    canonicalToIPA[canonical] = data.ipa;
    unicodeToCanonical[data.unicode] = canonical;
    variantToCanonical[canonical] = canonical;
    for (const v of data.variants) {
        variantToCanonical[v] = canonical;
    }
}

// Add digraph mappings
for (const [digraph, canonical] of Object.entries(DIGRAPHS)) {
    variantToCanonical[digraph] = canonical;
}

// =============================================================================
// NORMALIZER ENGINE
// =============================================================================

function isOldItalic(char) {
    const cp = char.codePointAt(0);
    return cp >= 0x10300 && cp <= 0x1032F;
}

function detectSourceSystem(text) {
    for (const char of text) {
        if (isOldItalic(char)) return 'unicode';
    }
    const philoChars = new Set(['θ', 'φ', 'χ', 'ś', 'Θ', 'Φ', 'Χ', 'Ś']);
    for (const c of text) {
        if (philoChars.has(c)) return 'philological';
    }
    const alpha = [...text].filter(c => /[a-zA-Z]/.test(c));
    if (alpha.length > 0 && alpha.every(c => c === c.toUpperCase())) return 'cie';
    return 'web_safe';
}

function unicodeToCanonicalText(text) {
    let result = '';
    for (const char of text) {
        if (isOldItalic(char)) {
            result += unicodeToCanonical[char] || char;
        } else {
            result += char;
        }
    }
    return result;
}

function foldToCanonical(text) {
    const result = [];
    const warnings = [];
    let i = 0;
    const chars = [...text]; // Handle surrogate pairs properly

    // Convert back to string indices for substring operations
    const str = text;

    while (i < str.length) {
        let matched = false;

        // Try longest match first (3, 2, 1)
        for (let len = Math.min(3, str.length - i); len > 0; len--) {
            const chunk = str.substring(i, i + len);
            const resolved = variantToCanonical[chunk];
            if (resolved !== undefined) {
                result.push(resolved);
                i += len;
                matched = true;
                break;
            }
        }

        if (!matched) {
            const char = str[i];
            if (/[a-zA-Z]/.test(char)) {
                const lower = char.toLowerCase();
                const resolved = variantToCanonical[lower];
                if (resolved !== undefined) {
                    result.push(resolved);
                } else {
                    warnings.push(`Unknown character '${char}'`);
                    result.push(lower);
                }
            } else if (' .,-;:\'[]()'.includes(char) || char === '\n' || char === '\t') {
                result.push(char);
            } else {
                warnings.push(`Unknown character '${char}'`);
                result.push(char);
            }
            i++;
        }
    }

    return { canonical: result.join(''), warnings };
}

function toPhonetic(canonical) {
    const parts = [];
    for (const char of canonical) {
        const ipa = canonicalToIPA[char];
        if (ipa) parts.push(ipa);
        else if (char === ' ') parts.push(' ');
        else parts.push(char);
    }
    const words = parts.join('').split(' ').filter(Boolean);
    return '/' + words.join('.') + '/';
}

function toOldItalic(canonical) {
    let result = '';
    for (const char of canonical) {
        const uc = canonicalToUnicode[char];
        if (uc) result += uc;
        else if (char === ' ') result += ' ';
        else result += char;
    }
    return result;
}

function normalize(text) {
    text = text.trim();
    if (!text) {
        return {
            canonical: '', phonetic: '', old_italic: '',
            source_system: '', tokens: [], confidence: 1.0, warnings: []
        };
    }

    const sourceSystem = detectSourceSystem(text);

    // Pre-process Unicode input
    if (sourceSystem === 'unicode') {
        text = unicodeToCanonicalText(text);
    }

    // Fold variants
    const { canonical, warnings } = foldToCanonical(text);

    // Generate outputs
    const phonetic = toPhonetic(canonical);
    const oldItalic = toOldItalic(canonical);
    const tokens = canonical.split(/\s+/).filter(Boolean);
    const confidence = Math.max(0, 1.0 - (warnings.length * 0.15));

    return {
        canonical, phonetic, old_italic: oldItalic,
        source_system: sourceSystem, tokens, confidence, warnings
    };
}

// =============================================================================
// UI WIRING
// =============================================================================

const input = document.getElementById('input-text');
const grid = document.getElementById('output-grid');
const detectedEl = document.getElementById('detected-system');

const outputs = {
    canonical: document.getElementById('out-canonical'),
    old_italic: document.getElementById('out-old-italic'),
    phonetic: document.getElementById('out-phonetic'),
    tokens: document.getElementById('out-tokens'),
    confidence: document.getElementById('out-confidence'),
    warnings: document.getElementById('out-warnings'),
    confidenceBar: document.getElementById('confidence-bar'),
};

// Live normalization on input
input.addEventListener('input', () => {
    const text = input.value;
    if (!text.trim()) {
        grid.classList.remove('active');
        detectedEl.classList.remove('visible');
        resetOutputs();
        return;
    }

    grid.classList.add('active');
    const result = normalize(text);

    outputs.canonical.textContent = result.canonical;
    outputs.old_italic.textContent = result.old_italic;
    outputs.phonetic.textContent = result.phonetic;
    outputs.tokens.textContent = result.tokens.map(t => `[${t}]`).join(' ');
    outputs.confidence.textContent = `${Math.round(result.confidence * 100)}%`;

    // Confidence bar
    const pct = result.confidence * 100;
    outputs.confidenceBar.style.width = pct + '%';
    outputs.confidenceBar.style.backgroundColor =
        pct >= 80 ? 'var(--success)' :
            pct >= 50 ? 'var(--warning)' : 'var(--error)';

    // Warnings
    outputs.warnings.textContent = result.warnings.length
        ? '⚠️ ' + result.warnings.join(' | ')
        : '';

    // Detected system badge
    const systemNames = {
        cie: 'CIE Standard', philological: 'Philological',
        unicode: 'Old Italic Unicode', web_safe: 'Web-safe', latex: 'LaTeX'
    };
    detectedEl.textContent = `Detected: ${systemNames[result.source_system] || result.source_system}`;
    detectedEl.classList.add('visible');
});

function resetOutputs() {
    outputs.canonical.textContent = '—';
    outputs.old_italic.textContent = '—';
    outputs.phonetic.textContent = '—';
    outputs.tokens.textContent = '—';
    outputs.confidence.textContent = '—';
    outputs.warnings.textContent = '';
    outputs.confidenceBar.style.width = '0%';
}

// Clear button
document.getElementById('btn-clear').addEventListener('click', () => {
    input.value = '';
    grid.classList.remove('active');
    detectedEl.classList.remove('visible');
    resetOutputs();
    input.focus();
});

// Example buttons
document.querySelectorAll('.btn-example').forEach(btn => {
    btn.addEventListener('click', () => {
        input.value = btn.dataset.text;
        input.dispatchEvent(new Event('input'));
    });
});

// Copy buttons
document.querySelectorAll('.btn-copy').forEach(btn => {
    btn.addEventListener('click', async () => {
        const target = btn.dataset.target;
        const el = document.getElementById('out-' + target.replace('_', '-'));
        const text = el?.textContent;
        if (!text || text === '—') return;

        try {
            await navigator.clipboard.writeText(text);
            btn.textContent = '✅';
            btn.classList.add('copied');
            setTimeout(() => {
                btn.textContent = '📋';
                btn.classList.remove('copied');
            }, 1500);
        } catch {
            // Fallback
            const textarea = document.createElement('textarea');
            textarea.value = text;
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
            btn.textContent = '✅';
            setTimeout(() => { btn.textContent = '📋'; }, 1500);
        }
    });
});
