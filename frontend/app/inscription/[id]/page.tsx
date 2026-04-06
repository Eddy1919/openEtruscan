import { notFound } from "next/navigation";
import Link from "next/link";
import { dateDisplay, pleiadesUrl, geonamesUrl, trismegistosUrl, eagleUrl, CLASS_COLORS, fetchInscription } from "@/lib/corpus";
import { AldineCitationExport } from "@/components/aldine/CitationExport";
import { AldineManuscript } from "@/components/aldine/Manuscript";
import { Box, Stack, Row, Ornament } from "@/components/aldine/Layout";

export async function generateStaticParams() {
  return [];
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const decodedId = decodeURIComponent(id);
  const insc = await fetchInscription(decodedId);
  if (!insc) return { title: "Not Found" };
  return {
    title: `${insc.id} | OpenEtruscan`,
    description: `Etruscan inscription ${insc.id}: "${insc.canonical}" from ${insc.findspot || "unknown provenance"}`,
  };
}

export default async function InscriptionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const decodedId = decodeURIComponent(id);
  const insc = await fetchInscription(decodedId);
  if (!insc) notFound();

  const classColor = CLASS_COLORS[insc.classification || "unknown"] || CLASS_COLORS.unknown;

  return (
    <Box surface="canvas" className="aldine-grow aldine-flex aldine-col aldine-py-16">
       <AldineManuscript align="center">
          
          <Box className="aldine-mb-8 aldine-pt-4">
             <Link href="/search" className="aldine-text-[10px] uppercase font-bold aldine-tracking-[0.2em] aldine-ink-muted hover:aldine-accent transition-colors aldine-flex aldine-center aldine-gap-2">
               <span>←</span> Return to Index
             </Link>
          </Box>

          <Row justify="between" align="end" border="bottom" padding={8} className="aldine-flex-col md:aldine-flex-row aldine-gap-6 aldine-mb-16">
            <Stack gap={2}>
              <h1 className="aldine-text-5xl md:aldine-text-6xl aldine-font-display font-medium aldine-ink-base aldine-italic aldine-tracking-tight">
                {insc.id}
              </h1>
              <Row gap={3} align="center" className="aldine-mt-4 aldine-flex-wrap">
                {insc.classification && insc.classification !== "unknown" && (
                  <Row gap={2} align="center">
                     <div className="aldine-w-1 aldine-h-1 aldine-rounded-full" style={{ backgroundColor: classColor }} />
                     <span className="aldine-font-interface aldine-text-[10px] font-bold uppercase aldine-tracking-widest aldine-ink-base aldine-opacity-80">
                       {insc.classification}
                     </span>
                  </Row>
                )}
                {insc.provenance_status === "rejected" && (
                  <span className="aldine-border aldine-border-accent aldine-accent aldine-font-interface aldine-text-[9px] font-bold uppercase aldine-tracking-widest aldine-px-2 aldine-py-0.5">
                    Unverified Original
                  </span>
                )}
                {insc.is_codex && (
                  <span className="aldine-border aldine-border-bone aldine-ink-muted aldine-font-interface aldine-text-[9px] font-bold uppercase aldine-tracking-widest aldine-px-2 aldine-py-0.5 aldine-mt-0.5">
                    Codex
                  </span>
                )}
              </Row>
            </Stack>
            <div className="aldine-mb-2">
               <AldineCitationExport
                 id={insc.id}
                 canonical={insc.canonical}
                 findspot={insc.findspot}
                 classification={insc.classification}
                 dateApprox={insc.date_approx}
               />
            </div>
          </Row>

          {/* Typeface Block */}
          <Stack gap={12} className="aldine-mb-24 aldine-w-full">
            <Stack gap={2}>
              <Ornament.Label className="aldine-accent">Structural Canon</Ornament.Label>
              <p className="aldine-font-editorial aldine-text-3xl md:aldine-text-5xl aldine-ink-base aldine-leading-snug aldine-break-words">
                {insc.canonical}
              </p>
            </Stack>
            
            <Box className="aldine-grid aldine-grid-cols-1 md:aldine-grid-cols-2 aldine-gap-12 aldine-border-t aldine-pt-8">
              {insc.phonetic && (
                <Stack gap={2}>
                  <Ornament.Label className="aldine-ink-muted">Acoustic Manifestation / IPA</Ornament.Label>
                  <p className="aldine-font-editorial aldine-text-2xl aldine-ink-base aldine-opacity-80">{insc.phonetic}</p>
                </Stack>
              )}
              {insc.old_italic && (
                <Stack gap={2}>
                  <Ornament.Label className="aldine-ink-muted">Linear Inscription (U+10300)</Ornament.Label>
                  <p className="aldine-font-display aldine-italic aldine-text-3xl aldine-ink-base aldine-tracking-widest">
                    {insc.old_italic}
                  </p>
                </Stack>
              )}
            </Box>
          </Stack>

          {/* LOD & Provenance Grid */}
          <Box className="aldine-grid aldine-grid-cols-1 md:aldine-grid-cols-2 aldine-gap-16 aldine-mb-24 aldine-border-t aldine-pt-16">
            
            <Stack>
              <h3 className="aldine-text-xl aldine-font-display font-medium aldine-ink-base aldine-border-b aldine-pb-4 aldine-mb-4">
                Quantitative Provenance
              </h3>
              <Stack gap={4}>
                <Row justify="between" align="end" border="bottom" padding={2} className="aldine-border-bone">
                  <span className="aldine-text-[10px] uppercase aldine-tracking-widest font-bold aldine-ink-muted">Find Site</span>
                  <span className="aldine-font-editorial aldine-text-lg aldine-ink-base aldine-text-right">{insc.findspot || "Unprovenanced"}</span>
                </Row>
                {insc.findspot_lat != null && (
                  <Row justify="between" align="end" border="bottom" padding={2} className="aldine-border-bone">
                    <span className="aldine-text-[10px] uppercase aldine-tracking-widest font-bold aldine-ink-muted">Vector Logic</span>
                    <span className="aldine-font-mono aldine-text-sm aldine-ink-base aldine-text-right">
                      {insc.findspot_lat.toFixed(4)}°N, {insc.findspot_lon?.toFixed(4)}°E
                    </span>
                  </Row>
                )}
                <Row justify="between" align="end" border="bottom" padding={2} className="aldine-border-bone">
                  <span className="aldine-text-[10px] uppercase aldine-tracking-widest font-bold aldine-ink-muted">Temporal Axis</span>
                  <span className="aldine-font-editorial aldine-text-lg aldine-ink-base aldine-text-right">{dateDisplay(insc)}</span>
                </Row>
                {insc.medium && (
                  <Row justify="between" align="end" border="bottom" padding={2} className="aldine-border-bone">
                    <span className="aldine-text-[10px] uppercase aldine-tracking-widest font-bold aldine-ink-muted">Material Context</span>
                    <span className="aldine-font-editorial aldine-text-lg aldine-ink-base aldine-text-right aldine-capitalize">{insc.medium}</span>
                </Row>
                )}
                {insc.object_type && (
                  <Row justify="between" align="end" padding={2}>
                    <span className="aldine-text-[10px] uppercase aldine-tracking-widest font-bold aldine-ink-muted">Geometric Typology</span>
                    <span className="aldine-font-editorial aldine-text-lg aldine-ink-base aldine-text-right aldine-capitalize">{insc.object_type}</span>
                  </Row>
                )}
              </Stack>
            </Stack>

            <Stack>
              <h3 className="aldine-text-xl aldine-font-display font-medium aldine-ink-base aldine-border-b aldine-pb-4 aldine-mb-4">
                RDF Ontological Links
              </h3>
              <Stack gap={4}>
                {insc.pleiades_id && (
                  <Row justify="between" align="end" border="bottom" padding={2} className="aldine-border-bone">
                    <span className="aldine-text-[10px] uppercase aldine-tracking-widest font-bold aldine-ink-muted">Pleiades Gazetteer</span>
                    <a href={pleiadesUrl(insc.pleiades_id)} target="_blank" rel="noreferrer" className="aldine-font-editorial aldine-text-lg aldine-accent hover:aldine-underline">
                      {insc.pleiades_id}
                    </a>
                  </Row>
                )}
                {insc.geonames_id && (
                  <Row justify="between" align="end" border="bottom" padding={2} className="aldine-border-bone">
                    <span className="aldine-text-[10px] uppercase aldine-tracking-widest font-bold aldine-ink-muted">GeoNames Database</span>
                    <a href={geonamesUrl(insc.geonames_id)} target="_blank" rel="noreferrer" className="aldine-font-editorial aldine-text-lg aldine-accent hover:aldine-underline">
                      {insc.geonames_id}
                    </a>
                  </Row>
                )}
                {insc.trismegistos_id && (
                  <Row justify="between" align="end" border="bottom" padding={2} className="aldine-border-bone">
                    <span className="aldine-text-[10px] uppercase aldine-tracking-widest font-bold aldine-ink-muted">Trismegistos Archive</span>
                    <a href={trismegistosUrl(insc.trismegistos_id)} target="_blank" rel="noreferrer" className="aldine-font-editorial aldine-text-lg aldine-accent hover:aldine-underline">
                      TM {insc.trismegistos_id}
                    </a>
                  </Row>
                )}
                {insc.eagle_id && (
                  <Row justify="between" align="end" border="bottom" padding={2} className="aldine-border-bone">
                    <span className="aldine-text-[10px] uppercase aldine-tracking-widest font-bold aldine-ink-muted">EAGLE Network</span>
                    <a href={eagleUrl(insc.eagle_id)} target="_blank" rel="noreferrer" className="aldine-font-editorial aldine-text-lg aldine-accent hover:aldine-underline">
                      {insc.eagle_id}
                    </a>
                  </Row>
                )}
                <Row justify="between" align="end" padding={2}>
                  <span className="aldine-text-[10px] uppercase aldine-tracking-widest font-bold aldine-ink-muted">Extractive Source</span>
                  <span className="aldine-font-editorial aldine-text-base aldine-ink-base aldine-text-right">{insc.source || "-"}</span>
                </Row>
              </Stack>
            </Stack>

          </Box>

          {insc.notes && (
            <Box className="aldine-mb-24 aldine-pt-12 aldine-border-t">
              <Ornament.Label className="aldine-accent aldine-mb-4">
                Curatorial Annotations
              </Ornament.Label>
              <p className="aldine-font-editorial aldine-text-lg aldine-ink-muted aldine-leading-relaxed aldine-whitespace-pre-wrap">
                {insc.notes}
              </p>
            </Box>
          )}

       </AldineManuscript>
    </Box>
  );
}
