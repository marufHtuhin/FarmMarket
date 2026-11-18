import { useCallback, useState } from "react";
import type L from "leaflet";
import { useLang } from "../i18n/LanguageContext";

// Primary tile source: Esri World Street Map — keyless, served from Esri's
// commercial CDN, and verified live with content inspection (17 Nov 2026:
// a real 30KB JPEG map tile, not an error image).
//
// Why not OSM's own tile server as primary? tile.openstreetmap.org blocks
// whole networks that trip its Tile Usage Policy, and on 17 Nov 2026 the
// user's network (via a VS Code dev-tunnel) got HTTP 403 "Access blocked"
// tiles on every zoom — while the same tiles served fine from another
// network. OSM blocking is IP/network-based, so no code change on our side
// can prevent it; OSM stays in the chain only as a fallback.
//
// CARTO's keyless basemaps are DEAD as of Nov 2026: cartocdn.com now
// answers keyless requests with HTTP 200 watermark tiles reading
// "API KEY REQUIRED", which Leaflet treats as a successful tile, so no
// tileerror ever fires and no fallback can rescue the map. CARTO light_all
// is therefore used ONLY when a key is configured at build time via
// VITE_CARTO_KEY (keyed URL form below).
//
// Fallback chain (a 403/404 tile error fires tileerror, unlike CARTO's
// 200 watermark): keyed CARTO -> Esri -> OSM -> "map unavailable" overlay.
const CARTO_KEY = (
  import.meta.env.VITE_CARTO_KEY as string | undefined
)?.trim();
export const CARTO_URL = CARTO_KEY
  ? `https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png?key=${encodeURIComponent(CARTO_KEY)}`
  : null;
export const CARTO_ATTR =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>';
// NOTE: Esri's tile scheme is /tile/{z}/{y}/{x} (row before column).
export const ESRI_URL =
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}";
export const ESRI_ATTR =
  'Sources: <a href="https://www.esri.com">Esri</a>, HERE, Garmin, <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, and the GIS user community';
export const OSM_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
export const OSM_ATTR =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

export type TileSource = "carto" | "esri" | "osm" | "unavailable";

/** Primary source at load: keyed CARTO when a key is configured, else Esri. */
export const PRIMARY_TILE_SOURCE: TileSource = CARTO_KEY ? "carto" : "esri";

/**
 * Pure fallback step: a failed CARTO tile switches to Esri, a failed Esri
 * tile switches to OSM, a failed OSM tile marks the map unavailable. The
 * failing tile's own src decides which source failed, so stale error events
 * from the previous source can't skip a step.
 */
export function nextTileSource(current: TileSource, tileSrc: string): TileSource {
  if (tileSrc.includes("cartocdn")) {
    return current === "carto" ? "esri" : current;
  }
  if (tileSrc.includes("arcgisonline")) {
    return current === "esri" ? "osm" : current;
  }
  if (tileSrc.includes("openstreetmap")) {
    return current === "osm" ? "unavailable" : current;
  }
  return current;
}

const TILE_URLS: Record<Exclude<TileSource, "unavailable">, string> = {
  carto: CARTO_URL ?? ESRI_URL,
  esri: ESRI_URL,
  osm: OSM_URL,
};

const TILE_ATTRS: Record<Exclude<TileSource, "unavailable">, string> = {
  carto: CARTO_ATTR,
  esri: ESRI_ATTR,
  osm: OSM_ATTR,
};

export function useTileSource() {
  const [source, setSource] = useState<TileSource>(PRIMARY_TILE_SOURCE);

  const onTileError = useCallback((e: L.TileErrorEvent) => {
    const src = e.tile?.src ?? "";
    setSource((current) => nextTileSource(current, src));
  }, []);

  return {
    // "carto" is only reachable when a key is configured, so CARTO_URL is
    // non-null whenever this branch is taken; TILE_URLS falls back to Esri
    // defensively either way. "unavailable" keeps the last URL so Leaflet
    // has a layer to render under the overlay.
    url: source === "unavailable" ? OSM_URL : TILE_URLS[source],
    attribution: source === "unavailable" ? OSM_ATTR : TILE_ATTRS[source],
    unavailable: source === "unavailable",
    onTileError,
  };
}

/** Graceful overlay shown over the map when all tile sources have failed. */
export function MapUnavailableNotice() {
  const { t } = useLang();
  return (
    <div className="pointer-events-none absolute inset-0 z-[500] flex items-center justify-center bg-cream/85 p-6 text-center">
      <p className="max-w-xs text-sm font-semibold text-forest">{t("mapUnavailable")}</p>
    </div>
  );
}
