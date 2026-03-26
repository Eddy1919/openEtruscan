"use client";

import { useCallback, useMemo } from "react";
import Map from "react-map-gl/maplibre";
import { DeckGL } from "@deck.gl/react";
import { ScatterplotLayer } from "@deck.gl/layers";
import type { Inscription } from "@/lib/corpus";
import { CLASS_COLORS } from "@/lib/corpus";

const INITIAL_VIEW = {
  longitude: 11.8,
  latitude: 42.8,
  zoom: 6.5,
  pitch: 0,
  bearing: 0,
};

const MAP_STYLE =
  "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

function hexToRgb(hex: string): [number, number, number] {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return [r, g, b];
}

interface MapViewProps {
  inscriptions: Inscription[];
  selected: Inscription | null;
  onInscriptionClick: (info: { object?: Inscription }) => void;
}

export default function MapView({
  inscriptions,
  selected,
  onInscriptionClick,
}: MapViewProps) {
  const getColor = useCallback(
    (d: Inscription): [number, number, number, number] => {
      const cls = d.classification || "unknown";
      const rgb = hexToRgb(CLASS_COLORS[cls] || CLASS_COLORS.unknown);
      const isSelected = selected?.id === d.id;
      return [...rgb, isSelected ? 255 : 180];
    },
    [selected]
  );

  const getRadius = useCallback(
    (d: Inscription) => (selected?.id === d.id ? 12 : 6),
    [selected]
  );

  const layers = useMemo(
    () => [
      new ScatterplotLayer<Inscription>({
        id: "inscriptions",
        data: inscriptions,
        getPosition: (d) => [d.findspot_lon!, d.findspot_lat!],
        getFillColor: getColor,
        getRadius: getRadius,
        radiusUnits: "pixels",
        radiusMinPixels: 3,
        radiusMaxPixels: 20,
        pickable: true,
        onClick: onInscriptionClick,
        updateTriggers: {
          getFillColor: [selected?.id],
          getRadius: [selected?.id],
        },
      }),
    ],
    [inscriptions, selected, getColor, getRadius, onInscriptionClick]
  );

  return (
    <DeckGL
      initialViewState={INITIAL_VIEW}
      controller={true}
      layers={layers}
      getTooltip={({ object }: { object?: Inscription }) =>
        object
          ? {
              html: `<div style="font-family:Inter,sans-serif;font-size:13px;max-width:260px">
                <strong style="color:#c4704b">${object.id}</strong><br/>
                <span style="font-family:monospace;color:#d4855f">${object.canonical}</span><br/>
                <span style="color:#9a9890">📍 ${object.findspot || "unknown"}</span>
              </div>`,
              style: {
                background: "#1e1e28",
                color: "#e8e6e3",
                border: "1px solid #2a2a36",
                borderRadius: "8px",
                padding: "10px 14px",
              },
            }
          : null
      }
    >
      <Map mapStyle={MAP_STYLE} />
    </DeckGL>
  );
}
