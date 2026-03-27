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
        The Etruscan language is one of the least-understood voices of the ancient Mediterranean. 
        In an era where artificial intelligence is trained on billions of words from modern, ubiquitous languages, fragmented and ancient tongues risk being left permanently behind in the dark. 
        We built OpenEtruscan to ensure they are not.
      </p>

      <section className={styles.section}>
        <h2>The Vision: Empowering the Margins</h2>
        <p>
          The digital revolution and the rapid rise of Artificial Intelligence represent a profound challenge for small, under-resourced fields of study. Modern machine learning models are inherently data-hungry; languages with limited, fragmented, or physically siloed corpora are largely invisible to them. If we do not actively digitize, computationally structure, and completely open the epigraphic records of ancient civilizations, their voices will fail to survive the transition into the AI age.
        </p>
        <p>
          OpenEtruscan is not merely a database for Etruscologists. It is a <strong>blueprint for empowering marginalized languages</strong>. We aim to prove that small fields can be equipped with the exact same advanced neural classification, semantic search, and massive statistical tools that are currently monopolized by the world&apos;s most spoken languages. 
        </p>
      </section>

      <section className={styles.section}>
        <h2>Why this project exists</h2>
        <p>
          The foundational corpora of Etruscan epigraphy—such as the <em>Corpus Inscriptionum Etruscarum</em> (CIE) and the <em>Etruskische Texte</em> (ET)—are masterworks of classical philology. However, they were born in the age of print. Today, access to this knowledge depends heavily on institutional subscriptions, physical library holdings, or static, scanned PDFs that resist any form of algorithmic analysis.
        </p>
        <p>
          OpenEtruscan dismantles these barriers. It provides a fully machine-readable, computationally accessible version of the Etruscan epigraphic record. Published entirely under permissive licences (MIT for code, CC0 for data), the platform guarantees that any scholar, student, or curious intellect worldwide can use, modify, and redistribute the material without restriction.
        </p>
      </section>

      <section className={styles.section}>
        <h2>Our Principles</h2>
        <ol className={styles.principles}>
           <li>
            <strong>Open by default.</strong> The preservation of human history should not be hidden behind institutional paywalls. All data, code, pipeline architectures, and neural models are public property. Our datasets are yours.
          </li>
          <li>
            <strong>AI for the Margins.</strong> Computational tools must respect the profound ambiguity of ancient fragments. We train specialized, lightweight neural networks that execute <em>client-side</em> in the browser. This democratizes machine learning, making it instantly accessible on any device, anywhere in the world.
          </li>
          <li>
            <strong>Radical Interdisciplinarity.</strong> A language cannot be resurrected in isolation. By integrating Natural Language Processing with archaeogenetics, geospatial analysis, and Linked Open Data, we move beyond text to reconstruct the physical and human realities behind the inscriptions.
          </li>
          <li>
            <strong>Interoperability over isolation.</strong> We align our identifiers with the semantic web (Pleiades, GeoNames) and host public SPARQL endpoints, ensuring the Etruscan corpus participates dynamically in the wider ecosystem of global knowledge.
          </li>
          <li>
            <strong>Provenance and attribution.</strong> Philology remains supreme. Every token carries its bibliographic source. Where machine models predict, human scholars verify. Scholarly consensus is strictly tracked, never overridden.
          </li>
        </ol>
      </section>

      <section className={styles.section}>
        <h2>An Open Invitation</h2>
        <p>
          Etruscology is a profoundly challenging field. The epigraphic record is fractured, the grammar only partially decoded, and the community of dedicated specialists is distributed across continents. We believe that radically open tools and datasets can lower the barrier to entry, connect researchers who would otherwise struggle in isolation, and breathe life into a body of evidence that demands wider global attention.
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
