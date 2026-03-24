/* =====================================================================
   stats-app.js — Statistics tab logic (frequency, clusters, dating)
   ===================================================================== */

let statsInitialized = false;
const CLUSTER_COLORS = ['#c4704b', '#6395f2', '#4ade80', '#c084fc', '#fbbf24', '#f472b6'];

function initStats() {
    statsInitialized = true;
    // Sub-tab switching
    document.querySelectorAll('.stats-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.stats-tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.stats-panel').forEach(p => p.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById('stab-' + btn.dataset.stab).classList.add('active');
            if (btn.dataset.stab === 'clusters' && !statsClusterMap) initStatsClusterMap();
        });
    });

    // Enter-key shortcuts
    document.getElementById('dateText').addEventListener('keydown', e => { if (e.key === 'Enter') estimateDate(); });
    document.getElementById('freqSiteA').addEventListener('keydown', e => { if (e.key === 'Enter') loadFrequency(); });

    // Auto-load frequency
    loadFrequency();
}

// ── 1. Letter Frequency ─────────────────────────────────────────────
let freqChartInstance = null;

window.loadFrequency = async function () {
    const siteA = document.getElementById('freqSiteA').value.trim();
    const siteB = document.getElementById('freqSiteB').value.trim();
    const url = new URL(API_BASE + '/stats/frequency', location.origin);
    if (siteA) url.searchParams.set('findspot', siteA);
    if (siteB) url.searchParams.set('findspot_b', siteB);

    document.getElementById('freqBtn').disabled = true;
    try {
        const res = await fetch(url.toString());
        if (!res.ok) throw new Error(res.status === 429 ? 'Rate limit exceeded.' : 'Server error: ' + res.status);
        const data = await res.json();
        renderFrequencyChart(data);
    } catch (e) { alert(e.message || 'Connection error'); console.error(e); }
    document.getElementById('freqBtn').disabled = false;
};

function renderFrequencyChart(data) {
    const primary = data.primary;
    const labels = primary.letters.map(l => l.letter);
    const freqs = primary.letters.map(l => l.frequency);

    document.getElementById('freqStats').style.display = 'flex';
    document.getElementById('freqStats').innerHTML = `
        <div class="stat-badge"><div class="value">${primary.inscription_count.toLocaleString()}</div><div class="label">Inscriptions</div></div>
        <div class="stat-badge"><div class="value">${primary.total_chars.toLocaleString()}</div><div class="label">Characters</div></div>
        <div class="stat-badge"><div class="value">${primary.letters.length}</div><div class="label">Letters</div></div>
    `;

    const datasets = [{
        label: data.label_a, data: freqs,
        backgroundColor: 'rgba(196,112,75,0.7)', borderColor: '#c4704b', borderWidth: 1, borderRadius: 3,
    }];
    if (data.secondary) {
        datasets.push({
            label: data.label_b, data: data.secondary.letters.map(l => l.frequency),
            backgroundColor: 'rgba(99,149,242,0.7)', borderColor: '#6395f2', borderWidth: 1, borderRadius: 3,
        });
    }

    if (freqChartInstance) freqChartInstance.destroy();
    freqChartInstance = new Chart(document.getElementById('freqChart'), {
        type: 'bar', data: { labels, datasets },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: {
                legend: { labels: { color: '#9a9890', font: { family: 'Inter' } } },
                tooltip: { backgroundColor: '#1e1e28', borderColor: '#2a2a36', borderWidth: 1 },
            },
            scales: {
                x: { ticks: { color: '#9a9890', font: { family: 'JetBrains Mono', size: 13 } }, grid: { color: '#2a2a36' } },
                y: { ticks: { color: '#9a9890', callback: v => (v * 100).toFixed(0) + '%' }, grid: { color: '#2a2a36' }, title: { display: true, text: 'Relative Frequency', color: '#6b6962' } },
            },
        },
    });

    document.getElementById('freqSubtitle').textContent = data.label_a + (data.label_b ? ` vs. ${data.label_b}` : '');

    const cmpEl = document.getElementById('comparisonResult');
    if (data.comparison) {
        const c = data.comparison;
        const cls = c.significant ? 'sig' : 'not-sig';
        const icon = c.significant ? '✦' : '≈';
        const text = c.significant
            ? `Statistically significant (χ²=${c.chi2.toFixed(1)}, p=${c.p_value < 0.001 ? '<0.001' : c.p_value.toFixed(4)}, Cramér's V=${c.effect_size.toFixed(3)})`
            : `No significant difference (χ²=${c.chi2.toFixed(1)}, p=${c.p_value.toFixed(4)})`;
        cmpEl.innerHTML = `<div class="comparison-badge ${cls}">${icon} ${text}</div>`;
        cmpEl.style.display = 'block';
    } else { cmpEl.style.display = 'none'; }
}

// ── 2. Dialect Clusters ─────────────────────────────────────────────
let statsClusterMap = null;
let statsClusterMarkers = [];
let pcaChartInstance = null;

const SITE_COORDS = {
    "Vulci": [42.4208, 11.6306], "Tarquinia": [42.2488, 11.7553],
    "Cerveteri": [42.0009, 12.1067], "Chiusi": [43.0174, 11.9492],
    "Perugia": [43.1107, 12.3908], "Volterra": [43.4015, 10.8619],
    "Orvieto": [42.7182, 12.1122], "Arezzo": [43.4613, 11.8802],
    "Bolsena": [42.6455, 11.9864], "Cortona": [43.2745, 11.9854],
    "Sovana": [42.6594, 11.6478], "Populonia": [42.9862, 10.4918],
    "Vetulonia": [42.8328, 10.9567], "Roselle": [42.7744, 11.1178],
    "Clusium": [43.0174, 11.9492], "Faesulae": [43.8059, 11.2944],
    "Veii": [42.0273, 12.3979], "Campania": [40.85, 14.25],
    "Tuscania": [42.4181, 11.8709], "Norchia": [42.3406, 11.9403],
    "Musarna": [42.4431, 11.8686], "Pyrgi": [42.0098, 11.9676],
    "San Giovenale": [42.2333, 11.9167], "Blera": [42.2744, 12.0285],
};

function initStatsClusterMap() {
    statsClusterMap = L.map('clusterMap', { zoomControl: false }).setView([42.8, 12.0], 7);
    L.control.zoom({ position: 'topleft' }).addTo(statsClusterMap);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: 'CARTO', subdomains: 'abcd', maxZoom: 19,
    }).addTo(statsClusterMap);
    loadClusters();
}

window.loadClusters = async function () {
    const min = document.getElementById('minInsc').value;
    document.getElementById('clusterBtn').disabled = true;
    try {
        const res = await fetch(`${API_BASE}/stats/clusters?min_inscriptions=${min}`);
        if (!res.ok) throw new Error(res.status === 429 ? 'Rate limit exceeded.' : 'Server error: ' + res.status);
        const data = await res.json();
        renderClusters(data);
    } catch (e) { alert(e.message || 'Connection error'); console.error(e); }
    document.getElementById('clusterBtn').disabled = false;
};

function renderClusters(data) {
    const totalSites = data.clusters.reduce((s, c) => s + c.sites.length, 0);
    document.getElementById('clusterStats').style.display = 'flex';
    document.getElementById('clusterStats').innerHTML = `
        <div class="stat-badge"><div class="value">${data.n_clusters}</div><div class="label">Clusters</div></div>
        <div class="stat-badge"><div class="value">${totalSites}</div><div class="label">Sites</div></div>
    `;

    statsClusterMarkers.forEach(m => statsClusterMap.removeLayer(m));
    statsClusterMarkers = [];
    const bounds = [];

    data.clusters.forEach(cluster => {
        const color = CLUSTER_COLORS[(cluster.cluster_id - 1) % CLUSTER_COLORS.length];
        cluster.sites.forEach(site => {
            const coords = SITE_COORDS[site.site];
            if (!coords) return;
            const m = L.circleMarker(coords, {
                radius: Math.min(6 + Math.sqrt(site.inscription_count), 18),
                fillColor: color, color: '#1e1e28', weight: 2, opacity: 1, fillOpacity: 0.85,
            });
            m.bindPopup(`<div style="font-family:'JetBrains Mono',monospace; color:${color}; font-size:11px; font-weight:bold;">Cluster ${cluster.cluster_id}</div>
                <div style="font-family:'Inter',sans-serif; font-size:13px; margin:4px 0; font-weight:600;">${site.site}</div>
                <div style="font-size:11px; color:#9a9890;">${site.inscription_count} inscriptions</div>`);
            m.addTo(statsClusterMap);
            statsClusterMarkers.push(m);
            bounds.push(coords);
        });
    });

    if (bounds.length > 0) statsClusterMap.fitBounds(bounds, { padding: [30, 30] });

    document.getElementById('clusterLegend').innerHTML = data.clusters.map(c => {
        const color = CLUSTER_COLORS[(c.cluster_id - 1) % CLUSTER_COLORS.length];
        return `<div class="legend-item"><div class="legend-dot" style="background:${color};"></div>Cluster ${c.cluster_id}: ${c.sites.map(s => s.site).join(', ')}</div>`;
    }).join('');

    renderPCA(data);
}

function renderPCA(data) {
    if (pcaChartInstance) pcaChartInstance.destroy();
    const datasets = data.clusters.map(c => ({
        label: `Cluster ${c.cluster_id}`,
        data: c.sites.map(s => ({ x: s.pca_x, y: s.pca_y, site: s.site })),
        backgroundColor: CLUSTER_COLORS[(c.cluster_id - 1) % CLUSTER_COLORS.length] + 'cc',
        borderColor: CLUSTER_COLORS[(c.cluster_id - 1) % CLUSTER_COLORS.length],
        borderWidth: 2, pointRadius: 7, pointHoverRadius: 10,
    }));

    pcaChartInstance = new Chart(document.getElementById('pcaChart'), {
        type: 'scatter', data: { datasets },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: {
                legend: { labels: { color: '#9a9890', font: { family: 'Inter' } } },
                tooltip: { backgroundColor: '#1e1e28', borderColor: '#2a2a36', borderWidth: 1, callbacks: { label: ctx => ctx.raw.site } },
            },
            scales: {
                x: { title: { display: true, text: 'PC 1', color: '#6b6962' }, ticks: { color: '#9a9890' }, grid: { color: '#2a2a36' } },
                y: { title: { display: true, text: 'PC 2', color: '#6b6962' }, ticks: { color: '#9a9890' }, grid: { color: '#2a2a36' } },
            },
        },
    });
}

// ── 3. Date Estimator ───────────────────────────────────────────────
window.estimateDate = async function () {
    const text = document.getElementById('dateText').value.trim();
    if (!text) return;
    document.getElementById('dateBtn').disabled = true;
    try {
        const url = new URL(API_BASE + '/stats/date-estimate', location.origin);
        url.searchParams.set('text', text);
        const res = await fetch(url.toString());
        if (!res.ok) throw new Error(res.status === 429 ? 'Rate limit exceeded.' : 'Server error: ' + res.status);
        const data = await res.json();
        renderDateResult(data);
    } catch (e) { alert(e.message || 'Connection error'); console.error(e); }
    document.getElementById('dateBtn').disabled = false;
};

function renderDateResult(data) {
    const el = document.getElementById('dateResult');
    el.style.display = 'block';
    const conf = Math.round(data.confidence * 100);
    const barColor = conf >= 50 ? 'var(--success)' : conf >= 25 ? 'var(--warning)' : 'var(--danger)';
    el.innerHTML = `
        <div class="date-result">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
                <span class="period-badge period-${data.period}">${data.period}</span>
                <span style="font-family:var(--font-mono); font-size:1.1rem; color:var(--accent-light);">${data.date_display}</span>
            </div>
            <div style="margin-bottom:1rem;">
                <div style="font-size:0.75rem; color:var(--text-muted); margin-bottom:4px;">Confidence: ${conf}%</div>
                <div style="background:var(--bg-primary); border-radius:4px; height:6px; overflow:hidden;">
                    <div style="width:${conf}%; height:100%; background:${barColor}; border-radius:4px; transition:width 0.5s;"></div>
                </div>
            </div>
            <div class="features-grid">
                ${data.features.map(f => `<div class="feature-item"><div class="feature-dot ${f.present ? 'present' : 'absent'}"></div>${f.description}</div>`).join('')}
            </div>
        </div>`;
}
