# Folio Zero-JS Architecture Execution

- [x] Phase 1: Build Pipeline & Installation
  - [x] Install `lightningcss-cli` and `autoprefixer`.
  - [x] Configure `package.json` with `"build:css"` script.
  - [x] Create `public/cdn` destination hierarchy.
  - [x] Link `cdn/folio.min.css` in `layout.tsx`.

- [x] Phase 2: Core Grammar & Primitives
  - [x] Scaffold `styles/folio/core` (`_reset.css`, `_tokens.css`).
  - [x] Scaffold `styles/folio/editorial` (`_typography.css`, `_layout.css`).
  - [x] Target `/explorer`.
  - [x] Target `/search`.

- [ ] Phase 3: The Burn-Down
  - [x] Refactor `<Nav>` to semantic headless architecture.
  - [x] Refactor `<StickyFooter>` to `folio-apparatus-criticus`.
  - [x] Integrate Folio grammar into `<Search>` node.
  - [ ] Integrate Folio grammar into `<Concordance>` node.
  - [ ] Delete `components/folio/Layout.tsx`.

- [x] Phase 4: Folio HIG Polish & Tactile Primitives
  - [x] Update `_tokens.css` with spacing grid.
  - [x] Update `_interactive.css` for click/scroll HIG metrics.
  - [x] Create `Cursor.tsx` custom tracker.
  - [x] Create `Dropdown.tsx` custom primitive.
  - [x] Apply HIG textfield/dropdown to `/search`.
