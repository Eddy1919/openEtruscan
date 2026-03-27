import type { Metadata } from "next";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Manifesto | OpenEtruscan",
  description:
    "The principles, motivations, and scholarly commitments behind the OpenEtruscan platform.",
};

export default function ManifestoPage() {
  return (
    <div className="page-container" style={{ maxWidth: 760 }}>
      <h1 className={styles.heading}>Manifesto</h1>
      <p className={styles.epigraph}>
        The Etruscan language is one of the least-documented languages of the
        ancient Mediterranean, yet it left behind thousands of inscriptions
        scattered across museums, publications, and archaeological sites. We
        believe these inscriptions belong to everyone.
      </p>

      <section className={styles.section}>
        <h2>Why this project exists</h2>
        <p>
          Existing corpora of Etruscan epigraphy, notably the <em>Corpus
          Inscriptionum Etruscarum</em> (CIE), the <em>Etruskische Texte</em>
          (ET), and the <em>Thesaurus Linguae Etruscae</em> (TLE), are
          indispensable, but they were born in the age of print. Access
          depends on institutional subscriptions, physical library holdings,
          or scanned PDFs that resist machine analysis.
        </p>
        <p>
          OpenEtruscan is a response to this situation. It provides a fully
          open, computationally accessible version of the Etruscan epigraphic
          record, published under permissive licences (MIT for code, CC0 for
          data) so that any scholar, student, or enthusiast can use, modify,
          and redistribute the material without restriction.
        </p>
      </section>

      <section className={styles.section}>
        <h2>Principles</h2>
        <ol className={styles.principles}>
          <li>
            <strong>Open by default.</strong> All data, code, and models are
            published openly. If something is closed, it is because we have not
            yet been able to open it, not by design.
          </li>
          <li>
            <strong>Interoperability over isolation.</strong> We align our
            identifiers with established gazetteers (Pleiades, GeoNames,
            Trismegistos) and publish as Linked Open Data so that the corpus
            participates in the wider ecosystem of ancient-world information,
            rather than standing apart.
          </li>
          <li>
            <strong>Computational methods as a complement to philology.</strong>
            {" "}Neural classifiers, normalizers, and statistical analyses are
            tools, not replacements for close reading. Their value lies in
            surfacing patterns across a corpus too large for one scholar to
            hold in memory.
          </li>
          <li>
            <strong>Provenance and attribution.</strong> Every inscription
            carries its bibliographic source. When we disagree with a reading,
            we note the alternative. Scholarly consensus is tracked, not
            overridden.
          </li>
          <li>
            <strong>Low-barrier access.</strong> The entire platform runs in a
            web browser. Neural models execute client-side; no data leaves the
            user&apos;s machine. There are no accounts, no paywalls, and no
            tracking beyond anonymised performance telemetry.
          </li>
        </ol>
      </section>

      <section className={styles.section}>
        <h2>Scope</h2>
        <p>
          The current corpus contains 4,728 inscriptions in Etruscan and
          related Italic scripts (Faliscan, Lemnian, Oscan, Umbrian),
          georeferenced to 45 archaeological sites across Italy. We aim to
          extend coverage as new publications appear and as OCR extraction from
          the CIE fascicles matures.
        </p>
        <p>
          We welcome corrections, additions, and alternative readings.
          Contributions can be submitted via the project&apos;s{" "}
          <a
            href="https://github.com/Eddy1919/openEtruscan"
            target="_blank"
            rel="noopener noreferrer"
          >
            GitHub repository
          </a>
          .
        </p>
      </section>

      <section className={styles.section}>
        <h2>Scholarly context</h2>
        <p>
          OpenEtruscan follows the FAIR data principles (Findable,
          Accessible, Interoperable, Reusable). The Linked Open Data layer
          uses the <em>Linking Ancient World Data</em> (LAWD) ontology, Dublin
          Core, and GeoSPARQL.
        </p>
        <p>
          The classifier models are described in a forthcoming technical note.
          Training data, evaluation metrics, and model weights are available
          on{" "}
          <a
            href="https://huggingface.co/Eddy1919/openetruscan-classifier"
            target="_blank"
            rel="noopener noreferrer"
          >
            Hugging Face
          </a>
          .
        </p>
      </section>

      <section className={styles.section}>
        <h2>Invitation</h2>
        <p>
          Etruscology is a small field. The epigraphic record is fragmentary,
          the language only partially understood, and the community of
          specialists is distributed across continents. We believe that open
          tools and open data can lower the barrier to entry, connect
          researchers who would otherwise work in isolation, and preserve a
          body of evidence that deserves wider attention.
        </p>
        <p>
          This project is an invitation to participate.
        </p>
      </section>
    </div>
  );
}
