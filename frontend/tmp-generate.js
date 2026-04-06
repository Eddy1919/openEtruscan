const fs = require('fs');

let css = '';

// Generate Spacing (p, pt, pb, pl, pr, px, py, m, mt, mb, ml, mr, mx, my, gap)
const spacing = [0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 32, 40, 48, 56, 64];
spacing.forEach(s => {
  const rem = s / 4;
  css += `.f-p-${s} { padding: ${rem}rem; }\n`;
  css += `.f-px-${s} { padding-left: ${rem}rem; padding-right: ${rem}rem; }\n`;
  css += `.f-py-${s} { padding-top: ${rem}rem; padding-bottom: ${rem}rem; }\n`;
  css += `.f-pt-${s} { padding-top: ${rem}rem; }\n`;
  css += `.f-pb-${s} { padding-bottom: ${rem}rem; }\n`;
  css += `.f-pl-${s} { padding-left: ${rem}rem; }\n`;
  css += `.f-pr-${s} { padding-right: ${rem}rem; }\n`;
  
  css += `.f-m-${s} { margin: ${rem}rem; }\n`;
  css += `.f-mx-${s} { margin-left: ${rem}rem; margin-right: ${rem}rem; }\n`;
  css += `.f-my-${s} { margin-top: ${rem}rem; margin-bottom: ${rem}rem; }\n`;
  css += `.f-mt-${s} { margin-top: ${rem}rem; }\n`;
  css += `.f-mb-${s} { margin-bottom: ${rem}rem; }\n`;
  css += `.f-ml-${s} { margin-left: ${rem}rem; }\n`;
  css += `.f-mr-${s} { margin-right: ${rem}rem; }\n`;
  
  css += `.f-gap-${s} { gap: ${rem}rem; }\n`;
});

// Generate Grid Cols
for (let i = 1; i <= 12; i++) {
  css += `.f-grid-cols-${i} { grid-template-columns: repeat(${i}, minmax(0, 1fr)); }\n`;
  css += `.f-col-span-${i} { grid-column: span ${i} / span ${i}; }\n`;
}

// Generate text sizes
const texts = {
  'xs': '0.75rem',
  'sm': '0.875rem',
  'base': '1rem',
  'lg': '1.125rem',
  'xl': '1.25rem',
  '2xl': '1.5rem',
  '3xl': '1.875rem',
  '4xl': '2.25rem',
  '5xl': '3rem',
  '6xl': '3.75rem'
};
Object.entries(texts).forEach(([k, v]) => {
  css += `.f-text-${k} { font-size: ${v}; }\n`;
  css += `.md\\:f-text-${k} { font-size: ${v}; }\n`;
  css += `.lg\\:f-text-${k} { font-size: ${v}; }\n`;
});

// Other common utilities
css += `
.f-overflow-hidden { overflow: hidden; }
.f-overflow-auto { overflow: auto; }
.f-overflow-y-auto { overflow-y: auto; }
.f-overflow-x-auto { overflow-x: auto; }

.f-cursor-pointer { cursor: pointer; }
.f-cursor-default { cursor: default; }

.f-opacity-0 { opacity: 0; }
.f-opacity-10 { opacity: 0.1; }
.f-opacity-20 { opacity: 0.2; }
.f-opacity-30 { opacity: 0.3; }
.f-opacity-40 { opacity: 0.4; }
.f-opacity-50 { opacity: 0.5; }
.f-opacity-60 { opacity: 0.6; }
.f-opacity-70 { opacity: 0.7; }
.f-opacity-80 { opacity: 0.8; }
.f-opacity-90 { opacity: 0.9; }
.f-opacity-100 { opacity: 1; }

.f-transition-all { transition-property: all; transition-timing-function: cubic-bezier(0.4, 0, 0.2, 1); transition-duration: 150ms; }
.f-transition-colors { transition-property: color, background-color, border-color, text-decoration-color, fill, stroke; transition-timing-function: cubic-bezier(0.4, 0, 0.2, 1); transition-duration: 150ms; }
.f-duration-100 { transition-duration: 100ms; }
.f-duration-150 { transition-duration: 150ms; }
.f-duration-200 { transition-duration: 200ms; }
.f-duration-300 { transition-duration: 300ms; }
.f-duration-500 { transition-duration: 500ms; }
.f-duration-700 { transition-duration: 700ms; }
.f-duration-1000 { transition-duration: 1000ms; }

.f-rounded-none { border-radius: 0; }
.f-rounded-sm { border-radius: 0.125rem; }
.f-rounded { border-radius: 0.25rem; }
.f-rounded-md { border-radius: 0.375rem; }
.f-rounded-lg { border-radius: 0.5rem; }
.f-rounded-full { border-radius: 9999px; }

.f-shadow-sm { box-shadow: 0 1px 2px 0 rgb(0 0 0 / 0.05); }
.f-shadow { box-shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1); }
.f-shadow-md { box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1); }
.f-shadow-lg { box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1); }

.f-outline-none { outline: 2px solid transparent; outline-offset: 2px; }

.f-capitalize { text-transform: capitalize; }
.f-uppercase { text-transform: uppercase; }
.f-lowercase { text-transform: lowercase; }

.f-tracking-tight { letter-spacing: -0.025em; }
.f-tracking-normal { letter-spacing: 0em; }
.f-tracking-wide { letter-spacing: 0.025em; }
.f-tracking-wider { letter-spacing: 0.05em; }
.f-tracking-widest { letter-spacing: 0.1em; }

.f-flex-col { flex-direction: column; }
.f-flex-row { flex-direction: row; }

/* Responsive MD & LG variants */
@media (min-width: 768px) {
  .md\\:f-flex-col { flex-direction: column; }
  .md\\:f-flex-row { flex-direction: row; }
  .md\\:f-order-1 { order: 1; }
  .md\\:f-order-2 { order: 2; }
  .md\\:f-w-auto { width: auto; }
}

@media (min-width: 1024px) {
  .lg\\:f-col-span-1 { grid-column: span 1 / span 1; }
  .lg\\:f-col-span-2 { grid-column: span 2 / span 2; }
  .lg\\:f-col-span-3 { grid-column: span 3 / span 3; }
  .lg\\:f-col-span-4 { grid-column: span 4 / span 4; }
  .lg\\:f-grid-cols-4 { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  .lg\\:f-flex-row { flex-direction: row; }
}

.f-min-w-0 { min-width: 0; }
.f-min-w-full { min-width: 100%; }

.f-max-w-xs { max-width: 20rem; }
.f-max-w-sm { max-width: 24rem; }
.f-max-w-md { max-width: 28rem; }
.f-max-w-lg { max-width: 32rem; }
.f-max-w-xl { max-width: 36rem; }
.f-max-w-2xl { max-width: 42rem; }
.f-max-w-3xl { max-width: 48rem; }
.f-max-w-4xl { max-width: 56rem; }
.f-max-w-5xl { max-width: 64rem; }

.f-bg-transparent { background-color: transparent; }

.f-border-l { border-left-width: 1px; }
.f-border-r { border-right-width: 1px; }
.f-border-t { border-top-width: 1px; }
.f-border-b { border-bottom-width: 1px; }
.f-border { border-width: 1px; }
.f-border-solid { border-style: solid; }
.f-border-dashed { border-style: dashed; }
.f-border-none { border-style: none; }

.f-text-center { text-align: center; }
.f-text-left { text-align: left; }
.f-text-right { text-align: right; }

.f-items-start { align-items: flex-start; }
.f-items-center { align-items: center; }
.f-items-end { align-items: flex-end; }
.f-items-baseline { align-items: baseline; }

.f-justify-start { justify-content: flex-start; }
.f-justify-center { justify-content: center; }
.f-justify-end { justify-content: flex-end; }
.f-justify-between { justify-content: space-between; }
.f-justify-around { justify-content: space-around; }

.f-fixed { position: fixed; }
.f-absolute { position: absolute; }
.f-relative { position: relative; }
.f-sticky { position: sticky; }
.f-static { position: static; }

.f-block { display: block; }
.f-inline-block { display: inline-block; }
.f-inline { display: inline; }
.f-flex { display: flex; }
.f-inline-flex { display: inline-flex; }
.f-grid { display: grid; }
.f-hidden { display: none; }

.f-z-0 { z-index: 0; }
.f-z-10 { z-index: 10; }
.f-z-20 { z-index: 20; }
.f-z-30 { z-index: 30; }
.f-z-40 { z-index: 40; }
.f-z-50 { z-index: 50; }

.f-w-auto { width: auto; }
.f-w-full { width: 100%; }
.f-w-screen { width: 100vw; }
.f-w-1\\/2 { width: 50%; }
.f-w-1\\/3 { width: 33.333333%; }
.f-w-2\\/3 { width: 66.666667%; }

.f-h-auto { height: auto; }
.f-h-full { height: 100%; }
.f-h-screen { height: 100vh; }
.f-h-1\\/2 { height: 50%; }

.f-pointer-events-none { pointer-events: none; }
.f-pointer-events-auto { pointer-events: auto; }

.f-font-bold { font-weight: 700; }
.f-font-semibold { font-weight: 600; }
.f-font-medium { font-weight: 500; }
.f-font-normal { font-weight: 400; }
.f-font-light { font-weight: 300; }
`;

const orig = fs.readFileSync('c:/Users/edpan/openEtruscan/frontend/app/globals.css', 'utf-8');
const merged = orig + '\n/* FOLIO DESIGN SYSTEM GENERATED UTILITIES */\n' + css;
fs.writeFileSync('c:/Users/edpan/openEtruscan/frontend/app/globals.css', merged);
