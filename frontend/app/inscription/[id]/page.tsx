import { notFound } from "next/navigation";
import Link from "next/link";
import type { Inscription } from "@/lib/corpus";
import { dateDisplay, pleiadesUrl, geonamesUrl, trismegistosUrl, eagleUrl, CLASS_COLORS, loadCorpus } from "@/lib/corpus";
import styles from "./page.module.css";
import CitationExport from "@/components/CitationExport";

export async function generateStaticParams() {
  const corpus = await loadCorpus();
  return corpus.map((i) => ({ id: i.id }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const decodedId = decodeURIComponent(id);
  const corpus = await loadCorpus();
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
  const corpus = await loadCorpus();
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
        {insc.provenance_status === "rejected" && (
          <span
            className="badge"
            style={{
              borderColor: "#ef4444",
              color: "#ef4444",
              border: `1px solid #ef4444`,
              background: `#ef444415`,
            }}
          >
            unverified
          </span>
        )}
        {insc.is_codex && (
          <span
            className="badge"
            style={{
              borderColor: "#8b5cf6",
              color: "#8b5cf6",
              border: `1px solid #8b5cf6`,
              background: `#8b5cf615`,
            }}
          >
            codex
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
            {insc.trismegistos_id && (
              <>
                <dt>Trismegistos</dt>
                <dd>
                  <a
                    href={trismegistosUrl(insc.trismegistos_id)}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    TM {insc.trismegistos_id} ↗
                  </a>
                </dd>
              </>
            )}
            {insc.eagle_id && (
              <>
                <dt>EAGLE</dt>
                <dd>
                  <a
                    href={eagleUrl(insc.eagle_id)}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    eagle:{insc.eagle_id} ↗
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
