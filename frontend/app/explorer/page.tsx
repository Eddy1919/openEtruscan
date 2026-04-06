import { fetchGeoInscriptions, fetchStatsSummary } from "@/lib/corpus";
import { ClientExplorerMap } from "@/components/aldine/ClientExplorerMap";

export const metadata = {
  title: "OpenEtruscan | Spatial Atlas",
  description: "Topographical distribution and GIS mapping of the Etruscan corpus.",
};

export default async function ExplorerPage() {
  const [geoRes, stats] = await Promise.all([
    fetchGeoInscriptions({ limit: 2000 }),
    fetchStatsSummary()
  ]);

  return <ClientExplorerMap initialInscriptions={geoRes.results} stats={stats} />;
}
