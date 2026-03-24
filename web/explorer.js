/* =====================================================================
   explorer.js — Merged Corpus Explorer (static map + API search)
   Combines map.html (static corpus) + search.html (API search) into
   one unified tab with sidebar + full-map layout.
   ===================================================================== */

// ── Pill Tab System ─────────────────────────────────────────────────
(function initPillTabs() {
    const tabs = document.querySelectorAll('.pill-tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
            tab.classList.add('active');
            const panel = document.getElementById('panel-' + tab.dataset.panel);
            panel.classList.add('active');

            // Lazy-init explorer map
            if (tab.dataset.panel === 'explorer' && !explorerMap) initExplorerMap();
            // Lazy-init stats
            if (tab.dataset.panel === 'stats' && !statsInitialized) initStats();

            // Leaflet needs invalidateSize after display:none → display:flex
            setTimeout(() => {
                if (explorerMap) explorerMap.invalidateSize();
            }, 100);
        });
    });
})();

// ── XSS Escape Utility ──────────────────────────────────────────────
const _ESC_MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
function esc(s) { return s ? String(s).replace(/[&<>"']/g, c => _ESC_MAP[c]) : '—'; }

// ── Explorer State ──────────────────────────────────────────────────
let explorerMap = null;
let staticMarkers = [];
let searchMarkers = [];
let currentCircle = null;
let currentLines = null;
const API_BASE = '/api';

// ── Initialize Explorer Map ─────────────────────────────────────────
function initExplorerMap() {
    explorerMap = L.map('explorerMap', { zoomControl: false }).setView([42.5, 12.0], 7);
    L.control.zoom({ position: 'topleft' }).addTo(explorerMap);

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
        subdomains: 'abcd',
        maxZoom: 19,
    }).addTo(explorerMap);

    // Load static corpus data
    loadStaticCorpus();

    // Check API
    checkExplorerApi();

    // Map click → radius search
    explorerMap.on('click', doRadiusSearch);

    // Form submit → text search
    document.getElementById('explorerSearchForm').addEventListener('submit', doTextSearch);
}

// ── Static Corpus (from corpus_data.js) ─────────────────────────────
function loadStaticCorpus() {
    if (typeof CORPUS_GEOJSON === 'undefined') return;
    const features = CORPUS_GEOJSON.features;

    // Group by findspot
    const groups = {};
    for (const f of features) {
        const key = f.properties.findspot || 'Unknown';
        if (!groups[key]) groups[key] = { coords: f.geometry.coordinates, inscriptions: [] };
        groups[key].inscriptions.push(f.properties);
    }

    const totalCities = Object.keys(groups).length;
    const totalInscriptions = features.length;
    document.getElementById('mapStatSites').textContent = totalCities.toLocaleString();
    document.getElementById('mapStatTotal').textContent = totalInscriptions.toLocaleString();

    // Add cluster-style markers
    for (const [findspot, group] of Object.entries(groups)) {
        const [lon, lat] = group.coords;
        const count = group.inscriptions.length;
        const size = Math.min(40, 14 + Math.sqrt(count) * 4);

        const marker = L.marker([lat, lon], {
            icon: L.divIcon({
                html: `<div style="
                    width:${size}px; height:${size}px;
                    background:radial-gradient(circle,#d4855f 0%,#8b4f35 100%);
                    border:2px solid #c4704b; border-radius:50%;
                    box-shadow:0 0 12px rgba(196,112,75,0.4);
                    display:flex; align-items:center; justify-content:center;
                    font-family:'JetBrains Mono',monospace; font-size:${Math.max(9, size * 0.35)}px;
                    font-weight:600; color:#e8e6e3;
                ">${count > 1 ? count : ''}</div>`,
                className: '',
                iconSize: [size, size],
                iconAnchor: [size / 2, size / 2],
            }),
        });

        // Build popup
        const samples = group.inscriptions.slice(0, 5);
        let popup = `<div class="popup-findspot"><strong>${esc(findspot)}</strong></div>
            <div style="color:#9a9890; font-size:0.75rem; margin-bottom:6px;">${count} inscription${count > 1 ? 's' : ''}</div>`;
        for (const insc of samples) {
            const txt = esc(insc.canonical || insc.id);
            const display = txt.length > 40 ? txt.substring(0, 40) + '…' : txt;
            popup += `<div class="popup-insc"><div class="popup-id">${esc(insc.id)}</div><div class="popup-text">${display}</div>${insc.date ? `<div class="popup-date">${esc(insc.date)}</div>` : ''}</div>`;
        }
        if (count > 5) popup += `<div style="color:#6b6962; font-size:0.7rem; text-align:center; margin-top:6px;">+ ${count - 5} more</div>`;

        marker.bindPopup(popup, { maxWidth: 320, maxHeight: 300 });
        marker.addTo(explorerMap);
        staticMarkers.push(marker);
    }
}

// ── API Check ───────────────────────────────────────────────────────
async function checkExplorerApi() {
    const el = document.getElementById('explorerApiStatus');
    const pill = document.getElementById('apiPill');
    try {
        const res = await fetch(API_BASE + '/stats');
        if (res.ok) {
            const d = await res.json();
            el.textContent = `Connected · ${d.total_inscriptions} inscriptions in database`;
            el.className = 'explorer-status connected';
            pill.textContent = `✓ ${d.total_inscriptions} inscriptions`;
            pill.className = 'api-pill connected';
        }
    } catch {
        el.textContent = 'API offline — showing static corpus only';
        el.className = 'explorer-status error';
        pill.textContent = '✗ API offline';
        pill.className = 'api-pill error';
    }
}

// ── Clear Search Markers (keep static) ──────────────────────────────
function clearSearchState() {
    searchMarkers.forEach(m => explorerMap.removeLayer(m));
    searchMarkers = [];
    if (currentCircle) { explorerMap.removeLayer(currentCircle); currentCircle = null; }
    if (currentLines) { explorerMap.removeLayer(currentLines); currentLines = null; }
}

// ── Render Search Results ───────────────────────────────────────────
function renderExplorerResults(data) {
    document.getElementById('explorerCount').textContent = `${data.count} results (Total: ${data.total})`;
    clearSearchState();

    const list = document.getElementById('explorerList');
    if (data.results.length === 0) {
        list.innerHTML = '<div style="text-align:center; color:#6b6962; padding:2rem;">No inscriptions found.</div>';
        return;
    }

    let html = '';
    const bounds = [];
    data.results.forEach(insc => {
        const safeGens = esc(insc.gens);
        const badge = insc.gens ? `<span class="clan-badge" onclick="event.stopPropagation(); searchClan('${esc(insc.gens)}')">${safeGens} Family</span>` : '';
        html += `<div class="result-card" onclick="panToExplorer(${Number(insc.findspot_lat) || 42.5}, ${Number(insc.findspot_lon) || 12.0})">
            <div class="result-id"><span>${esc(insc.id)}</span><span style="color:#6b6962">${esc(insc.classification)}</span></div>
            <div class="result-text">${esc(insc.canonical)} ${badge}</div>
            <div class="result-italic">${esc(insc.old_italic)}</div>
            <div class="result-meta"><div>📍 ${esc(insc.findspot) || 'Unknown'}</div><div>⏳ ${esc(insc.date_display) || 'Unknown'}</div></div>
        </div>`;

        if (insc.findspot_lat && insc.findspot_lon) {
            const m = L.circleMarker([insc.findspot_lat, insc.findspot_lon], {
                radius: 6, fillColor: '#c4704b', color: '#1e1e28', weight: 1, opacity: 1, fillOpacity: 0.8,
            });
            m.bindPopup(`<div style="font-family:'JetBrains Mono',monospace; color:#c4704b; font-size:10px; font-weight:bold;">${esc(insc.id)}</div>
                <div style="font-family:'JetBrains Mono',monospace; font-size:14px; margin:5px 0;">${esc(insc.canonical)}</div>
                <div style="font-size:11px; color:#9a9890;">${esc(insc.findspot)}</div>`);
            m.addTo(explorerMap);
            searchMarkers.push(m);
            bounds.push([insc.findspot_lat, insc.findspot_lon]);
        }
    });
    list.innerHTML = html;
    if (bounds.length > 0 && !currentCircle) explorerMap.fitBounds(L.latLngBounds(bounds), { padding: [50, 50], maxZoom: 10 });
}

// ── Text Search ─────────────────────────────────────────────────────
async function doTextSearch(e) {
    e.preventDefault();
    clearSearchState();
    const list = document.getElementById('explorerList');
    list.innerHTML = '<div style="text-align:center; padding:2rem;">Searching…</div>';

    const q = document.getElementById('explorerQ').value;
    const findspot = document.getElementById('explorerFindspot').value;
    const url = new URL(API_BASE + '/search', location.origin);
    if (q) url.searchParams.append('text', q);
    if (findspot) url.searchParams.append('findspot', findspot);

    const start = performance.now();
    try {
        const res = await fetch(url.toString());
        const data = await res.json();
        document.getElementById('explorerTime').textContent = Math.round(performance.now() - start) + 'ms';
        renderExplorerResults(data);
    } catch {
        list.innerHTML = '<div style="color:#f87171; padding:1rem;">API Error: Cannot connect to server.</div>';
    }
}

// ── Radius Search (map click) ───────────────────────────────────────
async function doRadiusSearch(e) {
    const lat = e.latlng.lat, lon = e.latlng.lng;
    const radiusKm = parseFloat(document.getElementById('explorerRadius').value) || 50;
    document.getElementById('explorerQ').value = '';
    document.getElementById('explorerFindspot').value = '';

    clearSearchState();
    currentCircle = L.circle([lat, lon], {
        radius: radiusKm * 1000, color: '#d4855f', fillColor: '#c4704b', fillOpacity: 0.1, weight: 2, dashArray: '4 4',
    }).addTo(explorerMap);
    explorerMap.panTo([lat, lon]);

    const list = document.getElementById('explorerList');
    list.innerHTML = '<div style="text-align:center; padding:2rem;">Running PostGIS Radius Query…</div>';

    const start = performance.now();
    try {
        const url = new URL(API_BASE + '/radius', location.origin);
        url.searchParams.append('lat', lat);
        url.searchParams.append('lon', lon);
        url.searchParams.append('radius_km', radiusKm);
        const res = await fetch(url.toString());
        const data = await res.json();
        document.getElementById('explorerTime').textContent = Math.round(performance.now() - start) + 'ms';
        renderExplorerResults(data);
    } catch {
        list.innerHTML = '<div style="color:#f87171; padding:1rem;">API Error: Cannot connect to server.</div>';
    }
}

// ── Clan Network Search ─────────────────────────────────────────────
window.searchClan = async function (gens) {
    clearSearchState();
    document.getElementById('explorerQ').value = '';
    document.getElementById('explorerFindspot').value = '';
    const list = document.getElementById('explorerList');
    list.innerHTML = `<div style="text-align:center; padding:2rem;">Mapping ${esc(gens)} Family Network…</div>`;

    const start = performance.now();
    try {
        const res = await fetch(API_BASE + '/clan/' + encodeURIComponent(gens));
        const data = await res.json();
        document.getElementById('explorerTime').textContent = Math.round(performance.now() - start) + 'ms';
        renderExplorerResults(data);

        const coords = data.results.filter(i => i.findspot_lat && i.findspot_lon).map(i => [i.findspot_lat, i.findspot_lon]);
        if (coords.length > 1) {
            currentLines = L.polyline(coords, { color: '#d4855f', weight: 2, dashArray: '4 8', opacity: 0.8 }).addTo(explorerMap);
            explorerMap.fitBounds(currentLines.getBounds(), { padding: [50, 50] });
        } else if (coords.length === 1) {
            explorerMap.flyTo(coords[0], 10);
        }
    } catch {
        list.innerHTML = '<div style="color:#f87171; padding:1rem;">API Error: Cannot fetch clan data.</div>';
    }
};

// ── Helpers ──────────────────────────────────────────────────────────
window.panToExplorer = function (lat, lon) {
    if (explorerMap) explorerMap.flyTo([lat, lon], 12);
};
