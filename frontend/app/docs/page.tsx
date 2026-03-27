import Link from "next/link";
import type { Metadata } from "next";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Documentation | OpenEtruscan",
  description:
    "Technical documentation for the OpenEtruscan digital corpus platform: API, data formats, models, and LOD infrastructure.",
};

const RESOURCES = [
  {
    title: "Source Code",
    url: "https://github.com/Eddy1919/openEtruscan",
    description:
      "Full monorepo: Python backend, Next.js frontend, data pipeline scripts, and model training code.",
  },
  {
    title: "Classification Models",
    url: "https://huggingface.co/Eddy1919/openetruscan-classifier",
    description:
      "Pre-trained CharCNN and Transformer models for Etruscan inscription classification. ONNX format, client-side inference.",
  },
  {
    title: "RDF Corpus (Turtle)",
    url: "https://github.com/Eddy1919/openEtruscan/blob/main/data/rdf/corpus.ttl",
    description:
      "Complete corpus exported as RDF/Turtle using LAWD, Dublin Core, and GeoSPARQL ontologies (1.6 MB, 4,728 inscriptions).",
  },
  {
    title: "SPARQL Endpoint",
    url: "https://api.openetruscan.com/sparql",
    description:
      "Apache Jena Fuseki 5.1 endpoint for querying the RDF corpus (34,477 triples). Supports SPARQL 1.1 and federated queries.",
  },

  {
    title: "PyPI Package",
    url: "https://pypi.org/project/openetruscan/",
    description:
      "Python library for programmatic access to the corpus: normalization, classification, and data export utilities.",
  },
];

export default function DocsPage() {
  return (
    <div className="page-container" style={{ maxWidth: 900 }}>
      <h1 className={styles.heading}>Documentation</h1>

      {/* Resources */}
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Resources</h2>
        <div className={styles.resourceGrid}>
          {RESOURCES.map((r) => (
            <a
              key={r.title}
              href={r.url}
              target="_blank"
              rel="noopener noreferrer"
              className={`card ${styles.resourceCard}`}
            >
              <h3 className={styles.resourceTitle}>{r.title}</h3>
              <p className={styles.resourceDesc}>{r.description}</p>
            </a>
          ))}
        </div>
      </section>

      {/* Data Schema */}
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Corpus Schema</h2>
        <div className="card">
          <p className={styles.schemaPreamble}>
            Each inscription record contains the following fields. The corpus is
            distributed as a static JSON file (<code>corpus.json</code>) and as
            RDF/Turtle (<code>corpus.ttl</code>).
          </p>
          <table className={styles.schemaTable}>
            <thead>
              <tr>
                <th>Field</th>
                <th>Type</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["id", "string", "Unique identifier (e.g. Cr 2.20, ETP_001)"],
                ["canonical", "string", "Standardized philological transcription"],
                ["old_italic", "string?", "Old Italic Unicode (U+10300 block)"],
                ["phonetic", "string?", "IPA pronunciation"],
                ["findspot", "string?", "Modern provenance name"],
                ["findspot_lat", "number?", "Latitude (WGS 84)"],
                ["findspot_lon", "number?", "Longitude (WGS 84)"],
                ["date_approx", "number?", "Approximate date (negative = BCE)"],
                ["date_uncertainty", "number?", "Date uncertainty (± years)"],
                ["classification", "string?", "Epigraphic type (funerary, votive, ownership, …)"],
                ["medium", "string?", "Inscription medium (stone, bronze, ceramic)"],
                ["object_type", "string?", "Object typology"],
                ["source", "string?", "Bibliographic source reference"],
                ["pleiades_id", "string?", "Pleiades gazetteer ID"],
                ["geonames_id", "string?", "GeoNames gazetteer ID"],
              ].map(([field, type, desc]) => (
                <tr key={field}>
                  <td><code>{field}</code></td>
                  <td><code>{type}</code></td>
                  <td>{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Normalizer reference */}
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Script Systems</h2>
        <div className="card">
          <p className={styles.schemaPreamble}>
            The <Link href="/normalizer">normalizer</Link> converts between five
            transcription systems used in Etruscan philology. Source-system
            detection is automatic.
          </p>
          <table className={styles.schemaTable}>
            <thead>
              <tr>
                <th>System</th>
                <th>Example</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["CIE Standard", "MI AVILES", "Uppercase, unaccented. Used in the Corpus Inscriptionum Etruscarum."],
                ["Philological", "mi avile·s", "Lowercase with diacritics (θ, φ, χ, ś). Standard in modern Etruscology."],
                ["Old Italic", "𐌌𐌉 𐌀𐌅𐌉𐌋𐌄𐌔", "Unicode U+10300 block. Faithful to original script direction."],
                ["IPA", "/mi aviles/", "International Phonetic Alphabet rendering."],
                ["Web-safe", "mi aviles", "ASCII-only approximation for contexts lacking Unicode support."],
              ].map(([sys, ex, desc]) => (
                <tr key={sys}>
                  <td>{sys}</td>
                  <td><code>{ex}</code></td>
                  <td>{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Classifier architecture */}
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Classifier Architecture</h2>
        <div className="card">
          <p className={styles.schemaPreamble}>
            Two neural architectures are available for epigraphic classification.
            Both operate at the character level (no tokenizer required) and
            classify inscriptions into 7 epigraphic types. Models are exported as
            ONNX and run client-side via WebAssembly.
          </p>
          <table className={styles.schemaTable}>
            <thead>
              <tr>
                <th>Model</th>
                <th>Parameters</th>
                <th>Size</th>
                <th>Architecture</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>CharCNN</td>
                <td>~28K</td>
                <td>111 KB</td>
                <td>1D convolution → max-pool → dense. Fast inference (~5 ms).</td>
              </tr>
              <tr>
                <td>Transformer</td>
                <td>~300K</td>
                <td>1.2 MB</td>
                <td>Character embedding → 2-layer Transformer encoder → classifier head. Higher accuracy on long texts.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* Linked Open Data */}
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Linked Open Data</h2>
        <div className="card">
          <p className={styles.schemaPreamble}>
            The corpus is published as Linked Open Data following W3C standards.
            Each inscription is modelled as a <code>lawd:WrittenWork</code> with
            spatial anchoring via <code>geo:SpatialThing</code> (GeoSPARQL).
          </p>
          <ul className={styles.lodList}>
            <li><strong>Ontologies:</strong> LAWD, Dublin Core, GeoSPARQL, SKOS</li>
            <li><strong>Gazetteers:</strong> 41 findspots aligned to Pleiades, 17 to GeoNames</li>
            <li><strong>Format:</strong> RDF/Turtle (<code>corpus.ttl</code>, 1.6 MB)</li>
            <li><strong>Endpoint:</strong> Apache Jena Fuseki 5.1 (SPARQL 1.1, 34,477 triples)</li>

          </ul>
        </div>
      </section>

      {/* Licence */}
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Licence</h2>
        <div className="card">
          <ul className={styles.lodList}>
            <li><strong>Code:</strong> MIT License</li>
            <li><strong>Data:</strong> CC0 1.0 Universal (Public Domain)</li>
            <li><strong>Models:</strong> Apache 2.0</li>
          </ul>
        </div>
      </section>
    </div>
  );
}
