import { MapContainer, TileLayer, Marker, Popup, Polyline } from "react-leaflet";
import { numberedPinIcon } from "./HubsMap";
import { MapUnavailableNotice, useTileSource } from "./MapTiles";

const ROUTE_COLORS = ["#1E7A4C", "#F2A33C", "#2563eb", "#9333ea", "#dc2626"];

export interface RouteStopPoint {
  id: string;
  lat: number;
  lon: number;
  order: number;
  vehicleId: string;
  arriveMin?: number;
}

export function RouteMap({
  depot,
  routes,
  height = 340,
}: {
  depot: { lat: number; lon: number };
  routes: Array<{ vehicleId: string; points: Array<[number, number]>; stops: RouteStopPoint[] }>;
  height?: number;
}) {
  const tiles = useTileSource();
  const allPts: Array<[number, number]> = [[depot.lat, depot.lon]];
  routes.forEach((r) => r.points.forEach((p) => allPts.push(p)));
  const center: [number, number] = [
    allPts.reduce((s, p) => s + p[0], 0) / allPts.length,
    allPts.reduce((s, p) => s + p[1], 0) / allPts.length,
  ];
  return (
    <div className="relative overflow-hidden rounded-3xl border border-line" style={{ height }}>
      <MapContainer center={center} zoom={11} style={{ height: "100%", width: "100%" }} scrollWheelZoom={false}>
        <TileLayer url={tiles.url} attribution={tiles.attribution} eventHandlers={{ tileerror: tiles.onTileError }} />
        {routes.map((r, i) => (
          <Polyline key={r.vehicleId} positions={r.points} color={ROUTE_COLORS[i % ROUTE_COLORS.length]} weight={4} />
        ))}
        <Marker position={[depot.lat, depot.lon]} icon={numberedPinIcon("⌂", "#F2A33C")}>
          <Popup>
            <b>Depot</b>
          </Popup>
        </Marker>
        {routes.flatMap((r, i) =>
          r.stops.map((s) => (
            <Marker
              key={`${r.vehicleId}-${s.id}`}
              position={[s.lat, s.lon]}
              icon={numberedPinIcon(s.order, ROUTE_COLORS[i % ROUTE_COLORS.length])}
            >
              <Popup>
                <b>{s.id}</b>
                <br />
                {s.vehicleId}
                {s.arriveMin !== undefined && (
                  <>
                    <br />
                    Arrive: {s.arriveMin} min
                  </>
                )}
              </Popup>
            </Marker>
          ))
        )}
      </MapContainer>
      {tiles.unavailable && <MapUnavailableNotice />}
    </div>
  );
}
