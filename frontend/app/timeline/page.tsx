import { fetchGeoInscriptions } from "@/lib/corpus";
import { ClientTimelineMap } from "@/components/aldine/ClientTimelineMap";

export const metadata = {
  title: "OpenEtruscan | Chronology",
  description: "Temporal distribution and chronological sequence of the Etruscan corpus.",
};

export default async function TimelinePage() {
  const res = await fetchGeoInscriptions({ limit: 4000 });
  const items = res?.results || [];

  return <ClientTimelineMap initialItems={items as any} />;
}
