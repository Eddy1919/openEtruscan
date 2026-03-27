import styles from "./page.module.css";

export default function Home() {
  return (
    <main className={styles.hero}>
      <div className={styles.heroContent}>
        <h1 className={styles.title}>
          <span style={{ color: "var(--text-primary)" }}>𐌏𐌐𐌄𐌍</span><span>Etruscan</span>
        </h1>
        <p className={styles.subtitle}>
          An open-source digital corpus and computational toolkit for the study
          of Etruscan epigraphy. MIT / CC0 licensed.
        </p>

        <div className={styles.stats}>
          <div className={styles.stat}>
            <span className={styles.statNumber}>4,728</span>
            <span className={styles.statLabel}>Inscriptions</span>
          </div>
          <div className={styles.stat}>
            <span className={styles.statNumber}>45</span>
            <span className={styles.statLabel}>Provenances</span>
          </div>
          <div className={styles.stat}>
            <span className={styles.statNumber}>41</span>
            <span className={styles.statLabel}>Pleiades Links</span>
          </div>
          <div className={styles.stat}>
            <span className={styles.statNumber}>5</span>
            <span className={styles.statLabel}>Script Systems</span>
          </div>
        </div>

        <div className={styles.actions}>
          <a href="/explorer" className="btn btn-primary">
            Explore the Corpus
          </a>
          <a href="/normalizer" className="btn btn-secondary">
            Script Normalizer
          </a>
          <a
            href="https://github.com/Eddy1919/openEtruscan"
            className="btn btn-secondary"
            target="_blank"
            rel="noopener noreferrer"
          >
            Source Code
          </a>
        </div>

        <div className={styles.features}>
          <div className="card">
            <h3>Georeferenced Corpus</h3>
            <p>
              Browse 4,700+ inscriptions on an interactive map. Each entry is
              aligned to Pleiades and GeoNames gazetteers for interoperability
              with other ancient-world datasets.
            </p>
          </div>
          <div className="card">
            <h3>Script Normalizer</h3>
            <p>
              Convert between five transcription systems: canonical, CIE,
              philological, Old Italic Unicode (U+10300), and IPA. Includes
              automatic source-system detection.
            </p>
          </div>
          <div className="card">
            <h3>Inscription Classifier</h3>
            <p>
              Character-level neural models (CNN, Transformer) classify
              inscriptions by epigraphic type. Inference runs client-side via
              ONNX Runtime. Models published on Hugging Face.
            </p>
          </div>
          <div className="card">
            <h3>Linked Open Data</h3>
            <p>
              The full corpus is exported as RDF/Turtle using LAWD and Dublin
              Core ontologies. A SPARQL endpoint enables cross-corpus queries
              within the Pelagios ecosystem.
            </p>
          </div>
        </div>
      </div>
    </main>
  );
}
