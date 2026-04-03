"use client";

import { useMemo, useState, useRef, useCallback, useEffect } from "react";
import Map, { Source, Layer, Popup } from "react-map-gl/mapbox";
import type { MapRef, CircleLayer, MapLayerMouseEvent } from "react-map-gl/mapbox";
import type { Inscription } from "@/lib/corpus";
import { CLASS_COLORS } from "@/lib/corpus";
import "mapbox-gl/dist/mapbox-gl.css";

const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;

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
  const mapRef = useRef<MapRef>(null);

  // Convert inscriptions array to GeoJSON
  const geoJsonData = useMemo(() => {
    return {
      type: "FeatureCollection" as const,
      features: inscriptions
        .filter((insc) => insc.findspot_lat != null && insc.findspot_lon != null)
        .map((insc) => ({
          type: "Feature" as const,
          geometry: {
            type: "Point" as const,
            coordinates: [insc.findspot_lon!, insc.findspot_lat!],
          },
          properties: {
            ...insc,
            color: CLASS_COLORS[insc.classification || "unknown"] || CLASS_COLORS.unknown,
            isSelected: selected?.id === insc.id,
          },
        })),
    };
  }, [inscriptions, selected]);

  const layerStyle: CircleLayer = {
    id: "inscriptions-layer",
    type: "circle",
    paint: {
      "circle-radius": [
        "case",
        ["boolean", ["get", "isSelected"], false],
        10,
        5,
      ],
      "circle-color": ["get", "color"],
      "circle-stroke-width": [
        "case",
        ["boolean", ["get", "isSelected"], false],
        2,
        1,
      ],
      "circle-stroke-color": [
        "case",
        ["boolean", ["get", "isSelected"], false],
        "#fff",
        ["get", "color"],
      ],
      "circle-opacity": [
        "case",
        ["boolean", ["get", "isSelected"], false],
        1,
        0.7,
      ],
    },
  };

  // Popup state for hover/clicks
  const [hoverInfo, setHoverInfo] = useState<{
    longitude: number;
    latitude: number;
    feature: any;
  } | null>(null);

  useEffect(() => {
    if (selected?.findspot_lat && selected?.findspot_lon) {
      mapRef.current?.flyTo({
        center: [selected.findspot_lon, selected.findspot_lat],
        duration: 800,
        zoom: 10,
      });
    }
  }, [selected]);

  const onClick = useCallback(
    (event: MapLayerMouseEvent) => {
      const feature = event.features?.[0];
      if (feature && feature.properties) {
        onInscriptionClick({ object: feature.properties as Inscription });
      } else {
        onInscriptionClick({});
      }
    },
    [onInscriptionClick]
  );

  const onMouseEnter = useCallback((e: MapLayerMouseEvent) => {
    const feature = e.features?.[0];
    if (feature && feature.properties) {
      document.body.style.cursor = "pointer";
      setHoverInfo({
        longitude: e.lngLat.lng,
        latitude: e.lngLat.lat,
        feature: feature.properties,
      });
    }
  }, []);

  const onMouseLeave = useCallback(() => {
    document.body.style.cursor = "";
    setHoverInfo(null);
  }, []);

  return (
    <Map
      ref={mapRef}
      initialViewState={{
        longitude: 11.8,
        latitude: 42.8,
        zoom: 6,
      }}
      mapStyle="mapbox://styles/mapbox/dark-v11"
      mapboxAccessToken={MAPBOX_TOKEN}
      interactiveLayerIds={["inscriptions-layer"]}
      onClick={onClick}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      style={{ width: "100%", height: "100%" }}
    >
      <Source id="inscriptions" type="geojson" data={geoJsonData}>
        <Layer {...layerStyle} />
      </Source>

      {hoverInfo && (
        <Popup
          longitude={hoverInfo.longitude}
          latitude={hoverInfo.latitude}
          offset={[0, -10]}
          closeButton={false}
          closeOnClick={false}
          anchor="bottom"
          style={{
            zIndex: 1000
          }}
        >
          <div style={{ padding: '4px' }}>
            <strong style={{ color: "#c4704b" }}>
              {hoverInfo.feature.id}
            </strong>
            <br />
            <span style={{ fontFamily: "monospace", color: "#d4855f" }}>
              {hoverInfo.feature.canonical}
            </span>
            <br />
            <span style={{ color: "#9a9890" }}>
              📍 {hoverInfo.feature.findspot || "unknown"}
            </span>
          </div>
        </Popup>
      )}
    </Map>
  );
}
