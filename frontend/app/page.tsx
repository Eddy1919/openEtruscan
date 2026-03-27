import styles from "./page.module.css";
import GlyphField from "@/components/GlyphField";

export default function Home() {
  return (
    <main>
      {/* Hero with particle background */}
      <section className={styles.hero}>
        <div className={styles.particleLayer}>
          <GlyphField />
        </div>
        <div className={styles.heroContent}>
          <h1 className={styles.title}>
            <span className={styles.titleOI}>𐌏𐌐𐌄𐌍</span>
            <span className={styles.titleLatin}>Etruscan</span>
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
            <a href="/search" className={`btn btn-primary ${styles.heroBtnPrimary}`}>
              Search the Corpus
            </a>
            <a href="/explorer" className={`btn btn-secondary ${styles.heroBtnSecondary}`}>
              Explore the Map
            </a>
            <a
              href="https://github.com/Eddy1919/openEtruscan"
              className={`btn btn-secondary ${styles.heroBtnSecondary}`}
              target="_blank"
              rel="noopener noreferrer"
            >
              Source Code
            </a>
          </div>
        </div>
      </section>

      {/* Feature cards */}
      <section className={styles.features}>
        <div className={styles.featureGrid}>
          <div className={`card ${styles.featureCard}`}>
            <div className={styles.featureIcon}>𐌏</div>
            <h3>Georeferenced Corpus</h3>
            <p>
              Browse 4,700+ inscriptions on an interactive map. Each entry is
              aligned to Pleiades and GeoNames gazetteers for interoperability
              with other ancient-world datasets.
            </p>
          </div>
          <div className={`card ${styles.featureCard}`}>
            <div className={styles.featureIcon}>𐌄</div>
            <h3>Script Normalizer</h3>
            <p>
              Convert between five transcription systems: canonical, CIE,
              philological, Old Italic Unicode (U+10300), and IPA. Includes
              automatic source-system detection.
            </p>
          </div>
          <div className={`card ${styles.featureCard}`}>
            <div className={styles.featureIcon}>𐌈</div>
            <h3>Neural Classifier</h3>
            <p>
              Character-level neural models (CNN, Transformer) classify
              inscriptions by epigraphic type. Inference runs client-side via
              ONNX Runtime.
            </p>
          </div>
          <div className={`card ${styles.featureCard}`}>
            <div className={styles.featureIcon}>𐌓</div>
            <h3>Linked Open Data</h3>
            <p>
              The full corpus is exported as RDF/Turtle using LAWD and Dublin
              Core ontologies. A SPARQL endpoint enables cross-corpus queries
              within the Linked Open Data ecosystem.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
