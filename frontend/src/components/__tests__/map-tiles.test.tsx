import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../../test/test-utils";
import { HubsMap } from "../HubsMap";
import { CARTO_URL, ESRI_URL, OSM_URL, PRIMARY_TILE_SOURCE, nextTileSource } from "../MapTiles";
import { FALLBACK_HUBS } from "../../utils/geo";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("nextTileSource", () => {
  it("switches CARTO -> Esri on a CARTO tile error", () => {
    expect(nextTileSource("carto", "https://a.basemaps.cartocdn.com/light_all/5/24/12.png")).toBe("esri");
  });

  it("switches Esri -> OSM on an Esri tile error", () => {
    expect(
      nextTileSource("esri", "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/5/12/24")
    ).toBe("osm");
  });

  it("switches OSM -> unavailable on an OSM tile error", () => {
    expect(nextTileSource("osm", "https://a.tile.openstreetmap.org/5/24/12.png")).toBe("unavailable");
  });

  it("ignores stale errors from the previous source", () => {
    // A late CARTO error arriving after the switch must not jump ahead.
    expect(nextTileSource("esri", "https://a.basemaps.cartocdn.com/light_all/5/24/12.png")).toBe("esri");
    expect(nextTileSource("osm", "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/5/12/24")).toBe("osm");
    expect(nextTileSource("unavailable", "https://a.tile.openstreetmap.org/5/24/12.png")).toBe("unavailable");
  });

  it("ignores errors from unknown sources", () => {
    expect(nextTileSource("esri", "https://example.com/tile.png")).toBe("esri");
  });
});

describe("map tile URLs", () => {
  it("uses Esri as the primary tile source by default (OSM 403-blocks some networks; CARTO keyless is dead)", () => {
    expect(PRIMARY_TILE_SOURCE).toBe("esri");
    expect(ESRI_URL).toBe(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}"
    );
    expect(OSM_URL).toBe("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png");
    // No VITE_CARTO_KEY in the test env, so there is no CARTO URL at all.
    expect(CARTO_URL).toBeNull();
  });

  it("uses keyed CARTO light_all as primary when VITE_CARTO_KEY is set", async () => {
    vi.stubEnv("VITE_CARTO_KEY", "test-key-123");
    vi.resetModules();
    const mod = await import("../MapTiles");
    expect(mod.PRIMARY_TILE_SOURCE).toBe("carto");
    expect(mod.CARTO_URL).toBe(
      "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png?key=test-key-123"
    );
    expect(mod.ESRI_URL).toBe(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}"
    );
    expect(mod.OSM_URL).toBe("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png");
  });
});

describe("HubsMap tile fallback", () => {
  function tileImgs(container: HTMLElement): HTMLImageElement[] {
    return Array.from(container.querySelectorAll(".leaflet-tile-pane img"));
  }

  it("starts on Esri, falls back to OSM, then shows the unavailable message", async () => {
    const { container } = renderWithProviders(<HubsMap hubs={FALLBACK_HUBS.slice(0, 2)} />);

    // Leaflet renders tile <img> elements once the map is mounted.
    await waitFor(() => expect(tileImgs(container).length).toBeGreaterThan(0));
    expect(tileImgs(container)[0].src).toContain("arcgisonline.com");
    expect(screen.queryByText(/মানচিত্র লোড করা যাচ্ছে না/)).not.toBeInTheDocument();

    // Simulate the Esri tile failing to load: the chain falls back to OSM.
    fireEvent.error(tileImgs(container)[0]);
    await waitFor(() =>
      expect(tileImgs(container).some((img) => img.src.includes("tile.openstreetmap.org"))).toBe(true)
    );
    expect(screen.queryByText(/মানচিত্র লোড করা যাচ্ছে না/)).not.toBeInTheDocument();

    // Simulate the OSM tile failing too: all sources exhausted.
    const osmTile = tileImgs(container).find((img) => img.src.includes("tile.openstreetmap.org"))!;
    fireEvent.error(osmTile);
    await waitFor(() =>
      expect(screen.getByText("মানচিত্র লোড করা যাচ্ছে না। সংযোগ পরীক্ষা করে পরে আবার চেষ্টা করুন।")).toBeInTheDocument()
    );
  });
});
