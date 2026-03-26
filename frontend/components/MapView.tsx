"use client";

import { useEffect, useRef } from "react";
import { MapContainer, TileLayer, CircleMarker, Tooltip, useMap } from "react-leaflet";
import type { Inscription } from "@/lib/corpus";
import { CLASS_COLORS } from "@/lib/corpus";
import "leaflet/dist/leaflet.css";

interface MapViewProps {
  inscriptions: Inscription[];
  selected: Inscription | null;
  onInscriptionClick: (info: { object?: Inscription }) => void;
}

function FlyToSelected({ selected }: { selected: Inscription | null }) {
  const map = useMap();
  useEffect(() => {
    if (selected?.findspot_lat && selected?.findspot_lon) {
      map.flyTo([selected.findspot_lat, selected.findspot_lon], 10, {
        duration: 0.8,
      });
    }
  }, [selected, map]);
  return null;
}

export default function MapView({
  inscriptions,
  selected,
  onInscriptionClick,
}: MapViewProps) {
  return (
    <MapContainer
      center={[42.8, 11.8]}
      zoom={6}
      style={{ width: "100%", height: "100%" }}
      zoomControl={true}
    >
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'
      />
      <FlyToSelected selected={selected} />
      {inscriptions.map((insc) => {
        const cls = insc.classification || "unknown";
        const color = CLASS_COLORS[cls] || CLASS_COLORS.unknown;
        const isSelected = selected?.id === insc.id;
        return (
          <CircleMarker
            key={insc.id}
            center={[insc.findspot_lat!, insc.findspot_lon!]}
            radius={isSelected ? 10 : 5}
            pathOptions={{
              fillColor: color,
              fillOpacity: isSelected ? 1 : 0.7,
              color: isSelected ? "#fff" : color,
              weight: isSelected ? 2 : 1,
            }}
            eventHandlers={{
              click: () => onInscriptionClick({ object: insc }),
            }}
          >
            <Tooltip
              direction="top"
              offset={[0, -8]}
              opacity={0.95}
            >
              <div
                style={{
                  fontFamily: "Inter, sans-serif",
                  fontSize: 13,
                  maxWidth: 260,
                }}
              >
                <strong style={{ color: "#c4704b" }}>{insc.id}</strong>
                <br />
                <span style={{ fontFamily: "monospace", color: "#d4855f" }}>
                  {insc.canonical}
                </span>
                <br />
                <span style={{ color: "#9a9890" }}>
                  📍 {insc.findspot || "unknown"}
                </span>
              </div>
            </Tooltip>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}
