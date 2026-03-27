import { notFound } from "next/navigation";
import Link from "next/link";
import type { Inscription } from "@/lib/corpus";
import { dateDisplay, pleiadesUrl, geonamesUrl, CLASS_COLORS } from "@/lib/corpus";
import styles from "./page.module.css";
import fs from "fs";
import path from "path";

import CitationExport from "@/components/CitationExport";

// Load corpus at build time
function getCorpus(): Inscription[] {
  const filePath = path.join(process.cwd(), "public", "data", "corpus.json");
  const raw = fs.readFileSync(filePath, "utf-8");
  return JSON.parse(raw);
}

export async function generateStaticParams() {
  const corpus = getCorpus();
  return corpus.map((i) => ({ id: encodeURIComponent(i.id) }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const decodedId = decodeURIComponent(id);
  const corpus = getCorpus();
  const insc = corpus.find((i) => i.id === decodedId);
  if (!insc) return { title: "Not Found" };
  return {
    title: `${insc.id} | OpenEtruscan`,
    description: `Etruscan inscription ${insc.id}: "${insc.canonical}" from ${insc.findspot || "unknown provenance"}`,
  };
}

export default async function InscriptionPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const decodedId = decodeURIComponent(id);
  const corpus = getCorpus();
  const insc = corpus.find((i) => i.id === decodedId);
  if (!insc) notFound();

  const classColor =
    CLASS_COLORS[insc.classification || "unknown"] || CLASS_COLORS.unknown;

  return (
    <div className="page-container">
      <div className={styles.breadcrumb}>
        <Link href="/explorer">← Explorer</Link>
      </div>

      <div className={styles.header}>
        <h1 className={styles.inscId}>{insc.id}</h1>
        {insc.classification && insc.classification !== "unknown" && (
          <span
            className="badge"
            style={{
              borderColor: classColor,
              color: classColor,
              border: `1px solid ${classColor}`,
              background: `${classColor}15`,
            }}
          >
            {insc.classification}
          </span>
        )}
      </div>

      {/* Main inscription text */}
      <div className={`card ${styles.textCard}`}>
        <h2>Text</h2>
        <div className={styles.textGrid}>
          <div>
            <label>Canonical</label>
            <p className="inscription-text" style={{ fontSize: "1.3rem" }}>
              {insc.canonical}
            </p>
          </div>
          {insc.phonetic && (
            <div>
              <label>Phonetic</label>
              <p className="inscription-text">{insc.phonetic}</p>
            </div>
          )}
          {insc.old_italic && (
            <div>
              <label>Old Italic</label>
              <p className="inscription-text">{insc.old_italic}</p>
            </div>
          )}
        </div>
      </div>

      {/* Provenance */}
      <div className={styles.metaGrid}>
        <div className="card">
          <h3>Provenance</h3>
          <dl className={styles.dl}>
            <dt>Find site</dt>
            <dd>{insc.findspot || "Unknown"}</dd>
            {insc.findspot_lat != null && (
              <>
                <dt>Coordinates</dt>
                <dd>
                  {insc.findspot_lat.toFixed(4)}°N,{" "}
                  {insc.findspot_lon?.toFixed(4)}°E
                </dd>
              </>
            )}
            <dt>Date</dt>
            <dd>{dateDisplay(insc)}</dd>
            {insc.medium && (
              <>
                <dt>Medium</dt>
                <dd>{insc.medium}</dd>
              </>
            )}
            {insc.object_type && (
              <>
                <dt>Object type</dt>
                <dd>{insc.object_type}</dd>
              </>
            )}
          </dl>
        </div>

        <div className="card">
          <h3>Linked Open Data</h3>
          <dl className={styles.dl}>
            {insc.pleiades_id && (
              <>
                <dt>Pleiades</dt>
                <dd>
                  <a
                    href={pleiadesUrl(insc.pleiades_id)}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    pleiades:{insc.pleiades_id} ↗
                  </a>
                </dd>
              </>
            )}
            {insc.geonames_id && (
              <>
                <dt>GeoNames</dt>
                <dd>
                  <a
                    href={geonamesUrl(insc.geonames_id)}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    geonames:{insc.geonames_id} ↗
                  </a>
                </dd>
              </>
            )}
            <dt>Source</dt>
            <dd>{insc.source || "-"}</dd>
          </dl>
        </div>
      </div>

      {insc.notes && (
        <div className="card">
          <h3>Notes</h3>
          <p style={{ color: "var(--text-secondary)", lineHeight: 1.6 }}>
            {insc.notes}
          </p>
        </div>
      )}

      <CitationExport
        id={insc.id}
        canonical={insc.canonical}
        findspot={insc.findspot}
        classification={insc.classification}
        dateApprox={insc.date_approx}
      />
    </div>
  );
}
