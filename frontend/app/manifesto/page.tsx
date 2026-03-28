import type { Metadata } from "next";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Manifesto | OpenEtruscan",
  description:
    "The visionary principles and scholarly commitments behind the OpenEtruscan platform.",
};

export default function ManifestoPage() {
  return (
    <div className="page-container" style={{ maxWidth: 760 }}>
      <h1 className={styles.heading}>Manifesto</h1>
      <p className={styles.epigraph}>
        The Etruscan language is one of the least-understood voices in the ancient Mediterranean. 
        As artificial intelligence continues to train on billions of words from modern, widespread languages, fragmented ancient tongues risk being left in the dark. 
        We built OpenEtruscan to ensure they survive.
      </p>

      <section className={styles.section}>
        <h2>The Vision: Empowering the Margins</h2>
        <p>
          The digital revolution and the rise of Artificial Intelligence present a profound challenge for under-resourced fields of study. Modern machine learning models are inherently data-hungry. Languages with limited or fragmented data are largely invisible to them. If we do not actively digitize, structure, and completely open the epigraphic records of ancient civilizations, their voices will fail to survive the transition into the AI age.
        </p>
        <p>
          OpenEtruscan is more than a database for Etruscologists. It is a <strong>blueprint for empowering marginalized languages</strong>. We aim to prove that small fields can use the exact same advanced neural classification, semantic search, and statistical tools currently monopolized by the world&apos;s most spoken languages.
        </p>
      </section>

      <section className={styles.section}>
        <h2>Why this project exists</h2>
        <p>
          The foundational texts of Etruscan epigraphy, such as the <em>Corpus Inscriptionum Etruscarum</em> (CIE) and the <em>Etruskische Texte</em> (ET), are masterworks of classical philology. However, they were born in the age of print. Today, access to this knowledge relies heavily on institutional subscriptions, physical libraries, or scanned PDFs that resist any form of algorithmic analysis.
        </p>
        <p>
          OpenEtruscan dismantles these barriers. It provides a fully machine-readable, computationally accessible version of the Etruscan epigraphic record. Published entirely under permissive licenses (MIT for code, CC0 for data), the platform guarantees that anyone worldwide can freely use, modify, and redistribute this material.
        </p>
      </section>

      <section className={styles.section}>
        <h2>Our Principles</h2>
        <ol className={styles.principles}>
           <li>
            <strong>Open by default.</strong> The preservation of human history should not be hidden behind institutional paywalls. All data, code, pipeline architectures, and neural models are public property.
          </li>
          <li>
            <strong>AI for the Margins.</strong> Computational tools must respect the profound ambiguity of ancient fragments. We train specialized, lightweight neural networks that execute directly in your browser. This democratizes machine learning so it is accessible on any device.
          </li>
          <li>
            <strong>Radical Interdisciplinarity.</strong> A language cannot be resurrected in isolation. By integrating Natural Language Processing with archaeogenetics, geospatial analysis, and Linked Open Data, we go beyond text to reconstruct the physical and human realities behind the inscriptions.
          </li>
          <li>
            <strong>Interoperability over isolation.</strong> We align our identifiers with the semantic web (like Pleiades and GeoNames) and host public SPARQL endpoints. This ensures the Etruscan corpus participates dynamically in the wider ecosystem of global knowledge.
          </li>
          <li>
            <strong>Provenance and attribution.</strong> Philology remains supreme. Every token carries its bibliographic source. Where machine models predict, human scholars verify. Scholarly consensus is strictly tracked and never overridden.
          </li>
        </ol>
      </section>

      <section className={styles.section}>
        <h2>An Open Invitation</h2>
        <p>
          Etruscology is a profoundly challenging field. The epigraphic record is fractured, the grammar is only partially decoded, and dedicated specialists are distributed across continents. We believe that radically open tools and datasets can lower the barrier to entry. We hope to connect researchers who might otherwise struggle in isolation, breathing new life into a body of evidence that demands wider global attention.
        </p>
        <p>
          By demonstrating that cutting-edge AI, data engineering, and classical philology can be seamlessly integrated for a language with fewer than 10,000 surviving texts, we hope OpenEtruscan inspires a wave of similar revivals for under-resourced languages across the globe.
        </p>
        <p style={{ marginTop: "1.5rem", fontWeight: "bold", color: "var(--accent)" }}>
          This project belongs to everyone. Join us.
        </p>
      </section>
    </div>
  );
}
