"use client";

import { useRef, useEffect, ReactNode, useState } from "react";
import Map, { Source, Layer, MapRef, MapProps } from "react-map-gl/mapbox";
import { AldineAttribution } from "./Attribution";
import "mapbox-gl/dist/mapbox-gl.css";
// Mapbox default CSS initially stripped as per Aldine architecture mandates, restored for rendering correctness

const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN || process.env.NEXT_PUBLIC_MAPBOX;

export const ETRUSCAN_BOUNDS: [[number, number], [number, number]] = [
  [7.5, 37.0],  // SW
  [15.0, 47.0]  // NE
];

const MASK_DATA: any = {
  type: "Feature",
  geometry: {
    type: "Polygon",
    coordinates: [
      [[-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85]],
      [[7.0, 37.5], [7.0, 46.5], [14.5, 46.5], [14.5, 37.5], [7.0, 37.5]]
    ]
  }
};

interface AldineMapProps extends MapProps {
  children?: ReactNode;
  showMask?: boolean;
}

export function AldineMap({ children, showMask = true, ...props }: AldineMapProps) {
  const mapRef = useRef<MapRef>(null);
  const [zoomLevel, setZoomLevel] = useState(props.initialViewState?.zoom || 6);

  useEffect(() => {
    if (mapRef.current) {
      const map = mapRef.current.getMap();
      map.setMaxBounds(ETRUSCAN_BOUNDS);
      map.setMinZoom(props.minZoom || 5.5);
    }
  }, [props.minZoom]);

  const handleZoom = (delta: number) => {
    if (mapRef.current) {
      const map = mapRef.current.getMap();
      const currentZoom = map.getZoom();
      map.flyTo({ zoom: currentZoom + delta, duration: 300 });
    }
  };

  return (
    <div className="aldine-relative aldine-w-full" style={{ height: "100%" }}>
      <Map
        ref={mapRef}
        mapboxAccessToken={MAPBOX_TOKEN}
        mapStyle="mapbox://styles/mapbox/light-v11"
        initialViewState={{
          longitude: 11.5,
          latitude: 42.5,
          zoom: 6,
          ...props.initialViewState
        }}
        maxBounds={ETRUSCAN_BOUNDS}
        attributionControl={false}
        {...props}
        style={{ width: "100%", height: "100%", ...props.style }}
      >
        {showMask && (
          <Source id="aldine-mask-source" type="geojson" data={MASK_DATA}>
            <Layer
              id="aldine-mask-layer"
              type="fill"
              paint={{
                "fill-color": "#fafaf9", // mapped to --aldine-canvas
                "fill-opacity": 1.0,
              }}
            />
          </Source>
        )}
        {children}
      </Map>

      {/* Typographic Zoom Controls locked to bottom corner */}
      <div className="aldine-absolute aldine-flex-col aldine-gap-2" style={{ bottom: '2rem', right: '2rem', zIndex: 10 }}>
        <button 
          className="aldine-nav-link aldine-font-epigraphic" 
          style={{ fontSize: '1.5rem', background: 'var(--aldine-canvas)', width: '2rem', height: '2rem', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid var(--aldine-hairline)' }}
          onClick={() => handleZoom(1)}
          arialdine-label="Zoom In"
        >
          +
        </button>
        <button 
          className="aldine-nav-link aldine-font-epigraphic" 
          style={{ fontSize: '1.5rem', background: 'var(--aldine-canvas)', width: '2rem', height: '2rem', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid var(--aldine-hairline)' }}
          onClick={() => handleZoom(-1)}
          arialdine-label="Zoom Out"
        >
          -
        </button>
      </div>

      {/* Stylized Aldine Attribution */}
      <AldineAttribution />
    </div>
  );
}




