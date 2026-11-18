import L from "leaflet";
import { MapContainer, TileLayer, Marker, Popup } from "react-leaflet";
import type { HubInfo } from "../utils/geo";
import { MapUnavailableNotice, useTileSource } from "./MapTiles";

export function hubPinIcon(): L.DivIcon {
  return L.divIcon({
    className: "",
    html: `<div class="hub-pin"><span>●</span></div>`,
    iconSize: [30, 30],
    iconAnchor: [15, 30],
    popupAnchor: [0, -28],
  });
}

export function numberedPinIcon(n: number | string, color = "#1E7A4C"): L.DivIcon {
  return L.divIcon({
    className: "",
    html: `<div class="route-num" style="background:${color}">${n}</div>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  });
}

export function HubsMap({
  hubs,
  popupText,
  height = 320,
}: {
  hubs: HubInfo[];
  popupText?: (hub: HubInfo) => string;
  height?: number;
}) {
  const tiles = useTileSource();
  const center: [number, number] = hubs.length
    ? [hubs.reduce((s, h) => s + h.lat, 0) / hubs.length, hubs.reduce((s, h) => s + h.lon, 0) / hubs.length]
    : [23.9, 90.4];
  return (
    <div className="relative overflow-hidden rounded-3xl border border-line" style={{ height }}>
      <MapContainer center={center} zoom={7} style={{ height: "100%", width: "100%" }} scrollWheelZoom={false}>
        <TileLayer url={tiles.url} attribution={tiles.attribution} eventHandlers={{ tileerror: tiles.onTileError }} />
        {hubs.map((h) => (
          <Marker key={h.id} position={[h.lat, h.lon]} icon={hubPinIcon()}>
            <Popup>
              <b>{h.name}</b>
              <br />
              {popupText ? popupText(h) : h.country}
            </Popup>
          </Marker>
        ))}
      </MapContainer>
      {tiles.unavailable && <MapUnavailableNotice />}
    </div>
  );
}
