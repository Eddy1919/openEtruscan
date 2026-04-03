"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import Map, { Source, Layer, Popup, useControl } from "react-map-gl/mapbox";
import type { MapRef, MapMouseEvent } from "react-map-gl/mapbox";
import type { CircleLayer } from "mapbox-gl";
import MapboxDraw from "@mapbox/mapbox-gl-draw";
import "@mapbox/mapbox-gl-draw/dist/mapbox-gl-draw.css";
import "mapbox-gl/dist/mapbox-gl.css";
import type { Inscription } from "@/lib/corpus";
import { searchRadius, API_URL } from "@/lib/corpus";

const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;

// Custom hook to integrate MapboxDraw into react-map-gl
function DrawControl(props: any) {
  useControl(
    () => new MapboxDraw(props),
    ({ map }) => {
      map.on("draw.create", props.onCreate);
      map.on("draw.update", props.onUpdate);
      map.on("draw.delete", props.onDelete);
    },
    ({ map }) => {
      map.off("draw.create", props.onCreate);
      map.off("draw.update", props.onUpdate);
      map.off("draw.delete", props.onDelete);
    },
    {
      position: props.position
    }
  );
  return null;
}

interface MapViewProps {
  selected: Inscription | null;
  onInscriptionClick: (info: { object?: Inscription }) => void;
  filterText: string;
  filterSite: string;
  filterClass: string;
}

export default function MapView({
  selected,
  onInscriptionClick,
  filterText,
  filterSite,
  filterClass,
}: MapViewProps) {
  const mapRef = useRef<MapRef>(null);

  // Dynamic filter array
  const filterExp: any[] = ["all", ["has", "id"]];
  if (filterSite) filterExp.push(["==", ["get", "findspot"], filterSite]);
  if (filterClass) filterExp.push(["==", ["get", "classification"], filterClass]);
  // Since we don't have text search capability in native tile features, we keep it simple or implement exact match on canonical if desired.
  // A rough approximation if text exists:
  if (filterText) filterExp.push(["in", filterText.toLowerCase(), ["downcase", ["get", "canonical"]]]);

  const layerStyle: CircleLayer = {
    id: "inscriptions-layer",
    type: "circle",
    source: "inscriptions",
    "source-layer": "inscriptions",
    paint: {
      "circle-radius": [
        "case",
        ["boolean", ["feature-state", "hover"], false],
        12,
        6,
      ],
      "circle-color": [
        "match",
        ["get", "classification"],
        "funerary", "#c4704b",
        "votive", "#6395f2",
        "dedicatory", "#4ade80",
        "legal", "#c084fc",
        "commercial", "#fbbf24",
        "boundary", "#f472b6",
        "ownership", "#38bdf8",
        "#6b6962", // Default
      ],
      "circle-stroke-width": [
        "case",
        ["boolean", ["feature-state", "hover"], false],
        3,
        1,
      ],
      "circle-stroke-color": "#fff",
      "circle-opacity": 0.8,
    },
    filter: filterExp,
  };

  const [hoverInfo, setHoverInfo] = useState<any | null>(null);
  const hoveredFeatureId = useRef<string | number | null>(null);

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
    (event: MapMouseEvent) => {
      const feature = event.features?.[0];
      if (feature && feature.properties) {
        onInscriptionClick({ object: feature.properties as Inscription });
      } else {
        onInscriptionClick({});
      }
    },
    [onInscriptionClick]
  );

  const onMouseEnter = useCallback((e: MapMouseEvent) => {
    const feature = e.features?.[0];
    if (feature && feature.id !== undefined && mapRef.current) {
      document.body.style.cursor = "pointer";
      
      if (hoveredFeatureId.current !== null) {
        mapRef.current.setFeatureState(
          { source: "inscriptions", sourceLayer: "inscriptions", id: hoveredFeatureId.current },
          { hover: false }
        );
      }
      
      hoveredFeatureId.current = feature.id;
      mapRef.current.setFeatureState(
        { source: "inscriptions", sourceLayer: "inscriptions", id: feature.id },
        { hover: true }
      );

      setHoverInfo({
        longitude: e.lngLat.lng,
        latitude: e.lngLat.lat,
        feature: feature.properties,
      });
    }
  }, []);

  const onMouseLeave = useCallback(() => {
    document.body.style.cursor = "";
    if (hoveredFeatureId.current !== null && mapRef.current) {
      mapRef.current.setFeatureState(
        { source: "inscriptions", sourceLayer: "inscriptions", id: hoveredFeatureId.current },
        { hover: false }
      );
    }
    hoveredFeatureId.current = null;
    setHoverInfo(null);
  }, []);

  // Mapbox Draw events
  const onDrawCreate = useCallback(async (e: any) => {
    const feature = e.features[0];
    if (feature.geometry.type === 'Polygon') {
      // Calculate radius in kilometers based on the bounding box approximation or center it
      // A proper mapping would extract the center point and radius
      // Here we just grab the first coordinate vertex as center and calculate distance to the opposite side
      const coords = feature.geometry.coordinates[0];
      const lng = coords[0][0];
      const lat = coords[0][1];
      
      try {
        // Trigger radius query 50km around the first point for demo
        const response = await searchRadius(lat, lng, 50.0);
        console.log("Spatial radius search executing via PostGIS ST_DWithin:", response);
      } catch (err) {
        console.error(err);
      }
    }
  }, []);

  const onDrawUpdate = useCallback((e: any) => {
    onDrawCreate(e);
  }, [onDrawCreate]);

  const onDrawDelete = useCallback(() => {
    console.log("Draw deleted.");
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
      <DrawControl
        position="top-left"
        displayControlsDefault={false}
        controls={{
          polygon: true,
          trash: true
        }}
        defaultMode="draw_polygon"
        onCreate={onDrawCreate}
        onUpdate={onDrawUpdate}
        onDelete={onDrawDelete}
      />
      
      <Source 
        id="inscriptions" 
        type="vector" 
        tiles={[`${API_URL}/tiles/{z}/{x}/{y}.pbf`]} 
        promoteId="id"
      >
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
