import styles from "./page.module.css";

export default function Home() {
  return (
    <main className={styles.hero}>
      <div className={styles.heroContent}>
        <h1 className={styles.title}>
          Open<span>Etruscan</span>
        </h1>
        <p className={styles.subtitle}>
          Open-source Digital Humanities platform for the computational study of
          Etruscan epigraphy
        </p>

        <div className={styles.stats}>
          <div className={styles.stat}>
            <span className={styles.statNumber}>4,728</span>
            <span className={styles.statLabel}>Inscriptions</span>
          </div>
          <div className={styles.stat}>
            <span className={styles.statNumber}>45</span>
            <span className={styles.statLabel}>Find Sites</span>
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
            Explore Corpus →
          </a>
          <a href="/normalizer" className="btn btn-secondary">
            Normalize Text
          </a>
          <a
            href="https://github.com/Eddy1919/openEtruscan"
            className="btn btn-secondary"
            target="_blank"
            rel="noopener noreferrer"
          >
            GitHub ↗
          </a>
        </div>

        <div className={styles.features}>
          <div className="card">
            <h3>🗺️ Interactive Map</h3>
            <p>
              WebGL-powered exploration of 4,700+ georeferenced inscriptions
              with Pleiades and GeoNames gazetteer links
            </p>
          </div>
          <div className="card">
            <h3>🔤 Script Normalizer</h3>
            <p>
              Universal transcription converter supporting 5 Etruscan script
              representations: canonical, phonetic, Old Italic, and more
            </p>
          </div>
          <div className="card">
            <h3>🧠 Neural Classifier</h3>
            <p>
              Character-level CNN and Transformer models classify inscriptions
              by type — running entirely in your browser via ONNX
            </p>
          </div>
          <div className="card">
            <h3>📊 Linked Open Data</h3>
            <p>
              Full RDF/Turtle export with LAWD and Dublin Core ontologies, and a
              SPARQL endpoint for cross-corpus discovery
            </p>
          </div>
        </div>
      </div>
    </main>
  );
}
