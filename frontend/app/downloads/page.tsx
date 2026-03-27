import Link from "next/link";
import type { Metadata } from "next";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Downloads | OpenEtruscan",
  description: "Download the OpenEtruscan corpus, RDF data, and ONNX classification models.",
};

const DOWNLOADS = [
  {
    title: "Corpus (JSON)",
    filename: "corpus.json",
    path: "/data/corpus.json",
    size: "~800 KB",
    description: "Complete corpus of 4,728 inscriptions in structured JSON. Includes canonical text, Old Italic Unicode, phonetic transcription, findspot coordinates, classification, and gazetteer links.",
    format: "JSON",
  },
  {
    title: "Corpus (RDF/Turtle)",
    filename: "corpus.ttl",
    url: "https://github.com/Eddy1919/openEtruscan/raw/main/data/rdf/corpus.ttl",
    size: "~1.6 MB",
    description: "Linked Open Data export using LAWD, Dublin Core, and GeoSPARQL ontologies. Each inscription modelled as a lawd:WrittenWork with spatial anchoring.",
    format: "Turtle",
  },
  {
    title: "CharCNN Model (ONNX)",
    filename: "cnn.onnx",
    path: "/models/cnn.onnx",
    size: "111 KB",
    description: "Character-level convolutional neural network for epigraphic classification. 7 classes. Optimised for fast inference (~5 ms).",
    format: "ONNX",
  },
  {
    title: "Transformer Model (ONNX)",
    filename: "transformer.onnx",
    path: "/models/transformer.onnx",
    size: "1.2 MB",
    description: "Character-level Transformer encoder for epigraphic classification. 7 classes. Higher accuracy on longer texts.",
    format: "ONNX",
  },
  {
    title: "Model Metadata (CNN)",
    filename: "cnn.json",
    path: "/models/cnn.json",
    size: "~1 KB",
    description: "Vocabulary, label definitions, and hyperparameters for the CharCNN model.",
    format: "JSON",
  },
  {
    title: "Model Metadata (Transformer)",
    filename: "transformer.json",
    path: "/models/transformer.json",
    size: "~1 KB",
    description: "Vocabulary, label definitions, and hyperparameters for the Transformer model.",
    format: "JSON",
  },
  {
    title: "Language Data",
    filename: "languages.json",
    path: "/data/languages.json",
    size: "~12 KB",
    description: "Alphabet tables, digraph rules, Unicode mappings, and IPA transcriptions for Etruscan and related Italic scripts (5 languages total).",
    format: "JSON",
  },
];

export default function DownloadsPage() {
  return (
    <div className="page-container" style={{ maxWidth: 900 }}>
      <h1 className={styles.heading}>Downloads</h1>
      <p className={styles.subtitle}>
        All data and models are freely available under permissive licences
        (CC0 for data, Apache 2.0 for models, MIT for code).
      </p>

      <div className={styles.grid}>
        {DOWNLOADS.map((d) => {
          const href = d.path || d.url || "#";
          const isExternal = !!d.url;
          return (
            <a
              key={d.filename}
              href={href}
              download={d.path ? d.filename : undefined}
              target={isExternal ? "_blank" : undefined}
              rel={isExternal ? "noopener noreferrer" : undefined}
              className={`card ${styles.downloadCard}`}
            >
              <div className={styles.cardHeader}>
                <span className={styles.cardTitle}>{d.title}</span>
                <span className={styles.formatBadge}>{d.format}</span>
              </div>
              <p className={styles.cardDesc}>{d.description}</p>
              <div className={styles.cardFooter}>
                <span className={styles.filename}>{d.filename}</span>
                <span className={styles.size}>{d.size}</span>
              </div>
            </a>
          );
        })}
      </div>

      <div className={styles.apiSection}>
        <h2 className={styles.sectionTitle}>Programmatic Access</h2>
        <div className="card">
          <p className={styles.apiDesc}>
            Use the <Link href="/api/normalize">Normalize API</Link> to
            convert Etruscan text programmatically:
          </p>
          <pre className={styles.codeBlock}>
{`curl -X POST https://open-etruscan.vercel.app/api/normalize \\
  -H "Content-Type: application/json" \\
  -d '{"text": "MI AVILES"}'`}
          </pre>
          <p className={styles.apiDesc} style={{ marginTop: "0.75rem" }}>
            The Python package is available via <code>pip install openetruscan</code>.
            Source code and additional tools are on{" "}
            <a href="https://github.com/Eddy1919/openEtruscan" target="_blank" rel="noopener noreferrer">
              GitHub
            </a>.
          </p>
        </div>
      </div>
    </div>
  );
}
