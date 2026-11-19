import axios from "axios";
import type { AxiosError, AxiosRequestConfig } from "axios";

// ---------------------------------------------------------------------------
// Types (shapes from backend/app/main.py + routers, and the shared contract)
// ---------------------------------------------------------------------------

export type Role = "farmer" | "buyer" | "transporter" | "admin";

export interface User {
  id: number;
  name: string;
  email: string;
  role: Role;
  district?: string;
  upazila?: string;
  phone?: string;
  business_name?: string;
  is_verified?: boolean;
  // Email verification (registration confirmation). Distinct from
  // is_verified, the admin-set seller badge.
  email_verified?: boolean;
  created_at?: string;
}

export interface AuthResponse {
  access_token: string;
  refresh_token?: string;
  token_type: string;
  user: User;
}

export interface ProductImage {
  id: number;
  url: string;
}

export interface Product {
  id: number;
  farmer_id?: number;
  farmer_name?: string;
  name: string;
  quantity: number;
  unit: string;
  price_per_unit: number;
  district: string;
  description?: string;
  image_url?: string;
  harvest_date?: string | null;
  available_until?: string | null;
  status?: string;
  created_at?: string;
  farmer?: { id: number; name: string; district?: string; is_verified?: boolean };
  images?: ProductImage[];
  farm?: Farm | null;
}

export interface ProductIn {
  name: string;
  quantity: number;
  unit: string;
  price_per_unit: number;
  district: string;
  harvest_date?: string | null;
  available_until?: string | null;
  description?: string;
  image_url?: string;
  farm_id?: number | null;
}

export interface Demand {
  id: number;
  buyer_id?: number;
  buyer_name?: string;
  product_name: string;
  required_quantity: number;
  unit: string;
  target_price: number;
  district: string;
  required_date?: string | null;
  notes?: string;
}

export interface Match {
  demand_id: number;
  buyer_name: string;
  product_id: number;
  product_name: string;
  farmer_id: number;
  farmer_name: string;
  quantity: number;
  required_quantity: number;
  unit: string;
  farmer_price: number;
  target_price: number;
  district: string;
  score: number;
  reasons: string[];
}

export interface PriceRecord {
  id: number;
  product_name: string;
  district: string;
  market_name?: string;
  price_per_unit: number;
  unit: string;
  source: string;
  recorded_at?: string | null;
  /** "real" or "demo", from the backend. Missing on old responses: treat as demo. */
  label?: "real" | "demo";
  /** True when a real price is older than 48h. Demo prices are never stale. */
  stale?: boolean;
}

/** Latest PriceObservation per hub x crop, from GET /api/v1/prices/latest. */
export interface LatestPrice {
  id: number;
  hub: string;
  crop: string;
  price: number;
  currency: string;
  unit: string;
  source: string;
  note?: string | null;
  observed_on?: string | null;
  ingested_at?: string | null;
  is_synthetic: boolean;
  label: "real" | "demo";
  stale: boolean;
  age_hours?: number | null;
}

export interface Order {
  id: number;
  product_id?: number;
  product_name: string;
  quantity: number;
  unit: string;
  unit_price: number;
  total_amount: number;
  status: string;
  created_at?: string;
  delivery_address?: string;
  // GET /orders/{id} returns the parties as nested objects (never flat
  // buyer_name/farmer_name/transporter_id fields); /orders/my returns
  // neither. See backend/app/main.py order_detail.
  buyer?: { id: number; name: string } | null;
  farmer?: { id: number; name: string; district?: string } | null;
  transporter?: { id: number; name: string } | null;
  offer_id?: number | null;
  delivery_status?: string | null;
}

export interface NotificationItem {
  id: number;
  title: string;
  message: string;
  is_read: boolean;
  created_at?: string;
}

// Farmer-buyer messaging. The backend never exposes phone numbers or email
// addresses here: `other` carries only id, name, role and district.
export interface ChatParticipant {
  id: number;
  name: string;
  role: Role;
  district?: string;
}

export interface ChatConversation {
  id: number;
  farmer_id: number;
  buyer_id: number;
  other: ChatParticipant;
  listing_id?: number | null;
  listing_name?: string | null;
  offer_id?: number | null;
  unread_count: number;
  last_message?: { body: string; sender_id: number; created_at?: string } | null;
  created_at?: string;
  updated_at?: string;
}

export interface ChatMessage {
  id: number;
  sender_id: number;
  sender_name?: string;
  body: string;
  created_at?: string;
  read_at?: string | null;
}

export interface DashboardData {
  role: string;
  total_products?: number;
  available_quantity?: number;
  active_orders?: number;
  total_sales?: number;
  total_orders?: number;
  open_demands?: number;
  total_spent?: number;
  recent_orders?: number;
}

export interface Farm {
  id: number;
  name: string;
  district: string;
  upazila?: string;
  area_acres?: number | null;
  country_code?: string;
}

export interface FarmIn {
  name: string;
  district: string;
  upazila?: string;
  area_acres?: number | null;
  country_code?: string;
}

export interface CropCatalogItem {
  id: string;
  name: string;
  local_names?: Record<string, string>;
  unit: string;
}

export interface Offer {
  id: number;
  product_id: number;
  product_name?: string;
  buyer_id?: number;
  buyer_name?: string;
  farmer_id?: number;
  quantity: number;
  offered_price: number;
  message?: string;
  status: string;
  created_at?: string;
}

export interface Vehicle {
  id: number;
  type?: string;
  vehicle_type?: string;
  capacity_kg: number;
  plate_number?: string;
  refrigerated?: boolean;
}

export interface VehicleIn {
  vehicle_type: string;
  capacity_kg: number;
  plate_number?: string;
  refrigerated?: boolean;
}

export interface Delivery {
  order_id: number;
  product_name?: string;
  quantity?: number;
  unit?: string;
  delivery_status: string;
  delivery_address?: string;
  district?: string;
  farmer_name?: string;
  buyer_name?: string;
  proof_note?: string | null;
}

export interface AdminActivity {
  kind: "user" | "order" | "product";
  title: string;
  detail: string;
  created_at?: string | null;
}

export interface AdminStats {
  total_users?: number;
  total_products?: number;
  total_orders?: number;
  total_revenue?: number;
  pending_orders?: number;
  users_by_role?: Record<string, number>;
  recent_activity?: AdminActivity[];
}

export interface AdminUser extends User {
  is_verified: boolean;
}

export interface AuditLog {
  id: number;
  action: string;
  actor_id?: number | null;
  actor_name?: string;
  details?: string | Record<string, unknown>;
  created_at?: string;
}

export interface DataSource {
  name: string;
  kind: string;
  endpoint?: string;
  countries?: string[];
  last_sync_at?: string | null;
  status?: string;
  notes?: string;
}

export interface ForecastHub {
  id: string;
  name: string;
  country: string;
  currency: string;
  lat: number;
  lon: number;
  observations?: Record<string, number>;
}

export interface ForecastResponse {
  model?: string;
  hub: { id: string; name: string; country: string; currency: string };
  crop: string;
  unit: string;
  horizon: number;
  frequency?: string;
  series: { points: number; start?: string; end?: string; sources?: string[]; synthetic_share?: number };
  history: Array<{ ds: string; y: number }>;
  forecast: Array<{ ds: string; yhat: number; lower: number; upper: number }>;
  signal: { direction: string; expected_change_pct: number };
  validation?: { smape_pct?: number; skill_vs_baseline?: number; interval_coverage?: number; reliable?: boolean };
  reliable: boolean;
  warnings?: string[];
}

export interface VisionResult {
  grade: string;
  ripeness?: string | null;
  disease?: string | null;
  confidence: number;
  price_multiplier?: number | null;
  suggested_price?: number | null;
  needs_manual_review?: boolean;
  reasons?: string[];
  warnings?: string[];
  image_sha256?: string;
  model_version?: string;
  price_applied?: boolean;
}

export interface AdvisorAdvice {
  mode: string;
  expected_fidelity?: string;
  requires_human_review?: boolean;
  truncated?: boolean;
  summary: string;
  actions: Array<{ action: string; timing?: string; reason?: string }>;
  risks: string[];
  uncertainty_note?: string;
  dialect_fidelity_note?: string;
}

export interface AssistantMessage {
  role: "user" | "assistant";
  content: string;
  sources?: Array<{ title: string; ref: string }>;
  mode?: string;
}

export interface AssistantConversation {
  id: string;
  title?: string;
  created_at?: string;
  messages?: AssistantMessage[];
}

export interface LogisticsStop {
  id: string;
  lat: number;
  lon: number;
  load_kg: number;
  service_min?: number;
  window_start_min?: number;
  window_end_min?: number;
  max_transit_min?: number;
}

export interface LogisticsPlanIn {
  depot: { lat: number; lon: number };
  stops: LogisticsStop[];
  vehicles: Array<{
    id: string;
    capacity_kg: number;
    refrigerated?: boolean;
    shelf_life_factor?: number;
  }>;
  mode?: "delivery" | "collection";
  road_provider?: "haversine" | "osrm";
  carbon_tradeoff?: number[];
}

export interface LogisticsPlan {
  totals: {
    vehicles_used: number;
    distance_km: number;
    minutes: number;
    co2_kg: number;
    late_min: number;
    spoilage_risk_min: number;
  };
  routes: Array<{
    vehicle_id: string;
    refrigerated?: boolean;
    load_kg: number;
    capacity_kg: number;
    distance_km: number;
    co2_kg: number;
    stops: Array<{ stop_id: string; arrive_min: number; late_min: number }>;
  }>;
  improvement_vs_baseline?: { objective_pct: number; co2_pct: number; minutes_pct: number };
  carbon_tradeoff?: Array<{ co2_per_kg_weight: number; minutes: number; co2_kg: number; distance_km: number }>;
  notes?: string[];
  road_provider?: string;
}

export interface BatchPublic {
  batch_code: string;
  crop: string;
  variety?: string;
  origin_district: string;
  harvested_at?: string | null;
  // cold_chain_check entries carry temp_c as the seal summary object
  // {min, max, avg} (same shape as cold_chain.temp_c); older payloads may
  // carry a plain number. BatchView handles both.
  timeline: Array<{ time: string; event: string; readings?: number; status?: string; temp_c?: number | { min: number; max: number; avg: number } | null }>;
  cold_chain: {
    n_readings: number;
    simulated_readings?: number;
    status?: string;
    temp_c?: { min: number; max: number; avg: number } | null;
    rh_pct?: { min: number; max: number } | null;
    temp_excursions?: number;
    minutes_out_of_temp_range?: number;
  };
  integrity: {
    chain_valid: boolean;
    blocks: number;
    head_hash: string;
    unsealed_readings?: number;
    externally_anchored?: boolean;
    note?: string;
  };
  // Exact URL the QR encodes (GET /twin/public/{code} -> verify_url), so the
  // UI can show what the QR points at without scanning it.
  verify_url?: string;
}

export interface BatchMine {
  batch_code: string;
  crop: string;
  quantity_kg: number;
  created_at?: string;
}

export interface WeatherDay {
  date: string;
  temp_max_c: number | null;
  temp_min_c: number | null;
  rain_mm: number | null;
  rain_probability_pct?: number | null;
  weather_code: number | null;
  condition: string;
}

export interface WeatherCurrent {
  time: string | null;
  temperature_c: number | null;
  humidity_pct: number | null;
  precipitation_mm: number | null;
  wind_speed_kmh: number | null;
  weather_code: number | null;
  condition: string;
}

export interface WeatherResponse {
  hub: string;
  hub_name: string;
  available: boolean;
  note?: string;
  source: string;
  fetched_at: string;
  timezone?: string | null;
  current?: WeatherCurrent;
  past?: WeatherDay[];
  forecast?: WeatherDay[];
  notes?: string[];
  /** True when the payload came from a direct browser call to Open-Meteo
      (utils/openmeteo.ts fallback), not from the backend. */
  direct?: boolean;
}

// ---------------------------------------------------------------------------
// Axios instance + token refresh
// ---------------------------------------------------------------------------

export const ACCESS_KEY = "fm_access_token";
export const REFRESH_KEY = "fm_refresh_token";
export const USER_KEY = "fm_user";

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY);
}
export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY);
}
export function storeTokens(access: string, refresh?: string | null) {
  localStorage.setItem(ACCESS_KEY, access);
  if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
  else localStorage.removeItem(REFRESH_KEY);
}
export function clearTokens() {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(USER_KEY);
}

// 30s default cap so no request can spin the UI forever: every call except
// the assistant's is far quicker, and a timeout surfaces as a visible error,
// never an endless spinner. Two exceptions, both deliberate:
//  - assistant chat + Gemini test override to 90s per request (see
//    assistantApi below): the backend Gemini bound is GEMINI_TIMEOUT_S
//    (default 20s, user-rais able — 60s was tried live on 2026-11-17), and
//    the frontend cap must never fire before the backend bound. 90s covers
//    a 60s Gemini timeout plus overhead; if GEMINI_TIMEOUT_S is ever raised
//    past ~75s, raise ASSISTANT_HTTP_TIMEOUT_MS to match.
//  - assistant streaming bypasses axios entirely (fetch, no timeout — see
//    streamAssistantChat): a stream stays open as long as tokens arrive,
//    and any fixed cap would cut it.
export const ASSISTANT_HTTP_TIMEOUT_MS = 90000;
const api = axios.create({ baseURL: "/api/v1", timeout: 30000 });

api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

let refreshing: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (!refreshing) {
    const rt = getRefreshToken();
    if (!rt) return null;
    refreshing = axios
      .post("/api/v1/auth/refresh", { refresh_token: rt })
      .then((res) => {
        const data = res.data as AuthResponse;
        storeTokens(data.access_token, data.refresh_token);
        return data.access_token;
      })
      .catch(() => {
        clearTokens();
        return null;
      })
      .finally(() => {
        refreshing = null;
      });
  }
  return refreshing;
}

api.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const original = error.config as AxiosRequestConfig & { _retried?: boolean };
    const url = original?.url || "";
    const isAuthCall = url.includes("/auth/login") || url.includes("/auth/refresh") || url.includes("/auth/register");
    if (error.response?.status === 401 && !isAuthCall && !original._retried) {
      original._retried = true;
      const newToken = await refreshAccessToken();
      if (newToken) {
        original.headers = original.headers || {};
        (original.headers as Record<string, string>).Authorization = `Bearer ${newToken}`;
        return api(original);
      }
      // No refresh token (or refresh failed): send the user back to login.
      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
        window.location.href = "/login?expired=1";
      }
    }
    return Promise.reject(error);
  }
);

export default api;

// ---------------------------------------------------------------------------
// Resource APIs
// ---------------------------------------------------------------------------

export const authApi = {
  login: (email: string, password: string) =>
    api.post<AuthResponse>("/auth/login", { email, password }).then((r) => r.data),
  register: (data: {
    name: string;
    email: string;
    phone?: string;
    password: string;
    role: string;
    district?: string;
    upazila?: string;
    business_name?: string;
  }) => api.post<AuthResponse>("/auth/register", data).then((r) => r.data),
  logout: (refreshToken?: string | null) =>
    api.post("/auth/logout", { refresh_token: refreshToken }).then((r) => r.data).catch(() => null),
  me: () => api.get<User>("/auth/me").then((r) => r.data),
  forgotPassword: (email: string) =>
    api.post<{ message: string; reset_token?: string }>("/auth/forgot-password", { email }).then((r) => r.data),
  resetPassword: (token: string, newPassword: string) =>
    api.post("/auth/reset-password", { token, new_password: newPassword }).then((r) => r.data),
  verifyEmail: (token: string) =>
    api.post<{ verified: boolean }>("/auth/verify-email", { token }).then((r) => r.data),
  resendVerification: () =>
    api.post<{ message: string }>("/auth/resend-verification", {}).then((r) => r.data),
};

export const metaApi = {
  countries: () =>
    api
      .get<Array<{ code: string; name: string; currency: string; hubs: Array<{ id: string; name: string; lat: number; lon: number }> }>>("/countries")
      .then((r) => r.data),
  crops: () => api.get<CropCatalogItem[]>("/crops").then((r) => r.data),
};

export const productsApi = {
  list: (params?: { search?: string; district?: string }) =>
    api.get<Product[]>("/products", { params }).then((r) => r.data),
  get: (id: number) => api.get<Product>(`/products/${id}`).then((r) => r.data),
  create: (data: ProductIn) => api.post<{ message: string; id: number }>("/products", data).then((r) => r.data),
  update: (id: number, data: ProductIn) => api.put(`/products/${id}`, data).then((r) => r.data),
  remove: (id: number) => api.delete(`/products/${id}`).then((r) => r.data),
  uploadImages: (id: number, files: File[], onProgress?: (pct: number) => void) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    return api
      .post(`/products/${id}/images`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (e) => {
          if (e.total && onProgress) onProgress(Math.round((e.loaded * 100) / e.total));
        },
      })
      .then((r) => r.data);
  },
};

export const farmsApi = {
  list: () => api.get<Farm[]>("/farms").then((r) => r.data),
  create: (data: FarmIn) => api.post<Farm>("/farms", data).then((r) => r.data),
  update: (id: number, data: FarmIn) => api.put<Farm>(`/farms/${id}`, data).then((r) => r.data),
  remove: (id: number) => api.delete(`/farms/${id}`).then((r) => r.data),
};

export const demandsApi = {
  list: () => api.get<Demand[]>("/demands").then((r) => r.data),
  create: (data: {
    product_name: string;
    required_quantity: number;
    unit: string;
    target_price: number;
    district: string;
    required_date?: string | null;
    notes?: string;
  }) => api.post("/demands", data).then((r) => r.data),
};

export const matchesApi = {
  list: () => api.get<Match[]>("/matches").then((r) => r.data),
};

export const pricesApi = {
  list: (params?: { product_name?: string; district?: string }) =>
    api.get<PriceRecord[]>("/prices", { params }).then((r) => r.data),
  /** Latest observation per hub x crop, with source, timestamps and labels. */
  latest: (params?: { hub?: string; crop?: string }) =>
    api
      .get<{ prices: LatestPrice[]; count: number; as_of: string }>("/prices/latest", { params })
      .then((r) => r.data),
  /** Full dated price series for one hub x crop (trend chart), oldest first. */
  history: (hub: string, crop: string) =>
    api
      .get<{ hub: string; crop: string; points: LatestPrice[]; count: number }>("/prices/history", {
        params: { hub, crop },
      })
      .then((r) => r.data),
  /** Admin-only: record one day's real price (source "manual"). */
  manualEntry: (data: { crop: string; hub: string; price: number; date: string; note?: string }) =>
    api.post<LatestPrice & { updated: boolean }>("/prices/manual", data).then((r) => r.data),
  /** Admin-only: most recently entered manual prices. */
  manualList: (limit = 20) =>
    api.get<{ items: LatestPrice[]; count: number }>("/prices/manual", { params: { limit } }).then((r) => r.data),
};

export const ordersApi = {
  listMine: () => api.get<Order[]>("/orders/my").then((r) => r.data),
  get: (id: number) => api.get<Order>(`/orders/${id}`).then((r) => r.data),
  create: (data: { product_id: number; quantity: number; delivery_address?: string }) =>
    api.post<{ message: string; order_id: number; total_amount: number }>("/orders", data).then((r) => r.data),
  setStatus: (id: number, status: string) =>
    api.patch(`/orders/${id}/status`, { status }).then((r) => r.data),
  assign: (id: number, transporterId: number) =>
    api.patch(`/orders/${id}/assign`, { transporter_id: transporterId }).then((r) => r.data),
};

export const offersApi = {
  create: (data: { product_id: number; quantity: number; offered_price: number; message?: string }) =>
    api.post<Offer>("/offers", data).then((r) => r.data),
  my: () => api.get<Offer[]>("/offers/my").then((r) => r.data),
  setStatus: (id: number, status: "accepted" | "rejected" | "cancelled") =>
    api.patch<Offer>(`/offers/${id}`, { status }).then((r) => r.data),
};

export const vehiclesApi = {
  list: () => api.get<Vehicle[]>("/vehicles").then((r) => r.data),
  create: (data: VehicleIn) => api.post<Vehicle>("/vehicles", data).then((r) => r.data),
  remove: (id: number) => api.delete(`/vehicles/${id}`).then((r) => r.data),
};

export const deliveriesApi = {
  list: () => api.get<Delivery[]>("/deliveries").then((r) => r.data),
  setStatus: (orderId: number, deliveryStatus: string, proofNote?: string) =>
    api
      .patch(`/deliveries/${orderId}`, { delivery_status: deliveryStatus, proof_note: proofNote })
      .then((r) => r.data),
};

/** Public transporter directory (no contact details) — used by the order
 *  assign picker for farmers and admins alike. */
export interface TransporterDirectoryEntry {
  id: number;
  name: string;
  business_name?: string | null;
  district?: string | null;
  is_verified?: boolean;
  vehicle_count?: number;
}

export const transportersApi = {
  list: () => api.get<TransporterDirectoryEntry[]>("/transporters").then((r) => r.data),
};

export const conversationsApi = {
  list: () => api.get<ChatConversation[]>("/conversations").then((r) => r.data),
  create: (data: { other_user_id: number; listing_id?: number | null; offer_id?: number | null }) =>
    api.post<ChatConversation>("/conversations", data).then((r) => r.data),
  unreadCount: () => api.get<{ unread: number }>("/conversations/unread-count").then((r) => r.data),
  getMessages: (id: number) => api.get<ChatMessage[]>(`/conversations/${id}/messages`).then((r) => r.data),
  sendMessage: (id: number, body: string) =>
    api.post<ChatMessage>(`/conversations/${id}/messages`, { body }).then((r) => r.data),
  markRead: (id: number) =>
    api.post<{ marked_read: number }>(`/conversations/${id}/read`, {}).then((r) => r.data),
};

export const notificationsApi = {
  list: () => api.get<NotificationItem[]>("/notifications").then((r) => r.data),
  markRead: (id: number) => api.patch(`/notifications/${id}/read`, {}).then((r) => r.data),
  markAllRead: () => api.post("/notifications/read-all", {}).then((r) => r.data),
};

export const dashboardApi = {
  get: () => api.get<DashboardData>("/dashboard").then((r) => r.data),
};

export const adminApi = {
  stats: () => api.get<AdminStats>("/admin/stats").then((r) => r.data),
  users: (params?: { search?: string; role?: string; page?: number; page_size?: number }) =>
    api.get<AdminUser[] | { items: AdminUser[]; total: number }>("/admin/users", { params }).then((r) => r.data),
  verifyUser: (id: number, isVerified: boolean) =>
    api.patch(`/admin/users/${id}/verify`, { is_verified: isVerified }).then((r) => r.data),
  auditLogs: () => api.get<AuditLog[]>("/admin/audit-logs").then((r) => r.data),
  dataSources: () => api.get<DataSource[]>("/admin/data-sources").then((r) => r.data),
};

export const forecastApi = {
  hubs: () =>
    api
      .get<{ profile: string; hubs: ForecastHub[]; crops: Array<{ id: string; name: string }> }>("/forecast/hubs")
      .then((r) => r.data),
  sklearn: (hub: string, crop: string, horizon = 8) =>
    api
      .get<ForecastResponse>("/forecast/sklearn", { params: { hub, crop, horizon } })
      .then((r) => r.data),
};

/** Hub weather from Open-Meteo (past 7 days + current + next 7 days). */
export const weatherApi = {
  get: (hub: string) =>
    api.get<WeatherResponse>(`/weather/${encodeURIComponent(hub)}`).then((r) => r.data),
};

export const visionApi = {
  status: () =>
    api
      .get<{ models: Record<string, unknown>; grade_table?: unknown; min_confidence?: number }>("/vision/status")
      .then((r) => r.data),
  assess: (
    image: File,
    crop: string,
    opts?: { referencePrice?: number; productId?: number; applyPrice?: boolean },
    onProgress?: (pct: number) => void
  ) => {
    const fd = new FormData();
    fd.append("image", image);
    fd.append("crop", crop);
    if (opts?.referencePrice) fd.append("reference_price", String(opts.referencePrice));
    if (opts?.productId) fd.append("product_id", String(opts.productId));
    if (opts?.applyPrice) fd.append("apply_price", "true");
    return api
      .post<VisionResult>("/vision/assess", fd, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (e) => {
          if (e.total && onProgress) onProgress(Math.round((e.loaded * 100) / e.total));
        },
      })
      .then((r) => r.data);
  },
};

export const advisorApi = {
  languages: () =>
    api
      .get<Array<{ code: string; name: string; expected_fidelity: string; note?: string }>>("/advisor/languages")
      .then((r) => r.data),
  advice: (data: { crop: string; hub_id?: string | null; language: string; report?: string; region?: string }) =>
    api.post<AdvisorAdvice>("/advisor/advice", data).then((r) => r.data),
};

export interface AssistantTestResult {
  ok: boolean;
  mode: "gemini" | "template";
  latency_ms: number;
  error: string | null;
}

export interface AssistantStreamDone {
  conversation_id: string;
  sources: Array<{ title: string; ref: string }>;
  mode: "gemini" | "template";
}

export const assistantApi = {
  // 90s per-request timeout (not the 30s axios default): the backend Gemini
  // bound is GEMINI_TIMEOUT_S (default 20s, user-rais able to 60s), and the
  // frontend must never time out first — that exact failure was seen live
  // on 2026-11-17 ("timeout of 30000ms exceeded" with GEMINI_TIMEOUT_S=60).
  chat: (data: { conversation_id?: string; message: string; language: string }) =>
    api
      .post<{
        reply: string;
        sources: Array<{ title: string; ref: string }>;
        conversation_id: string;
        mode: "gemini" | "template";
      }>("/assistant/chat", data, { timeout: ASSISTANT_HTTP_TIMEOUT_MS })
      .then((r) => r.data),
  // Admin-only live Gemini probe. 90s cap: the probe waits up to 60s on the
  // backend so it can tell "slow" from "blocked".
  test: () =>
    api
      .post<AssistantTestResult>("/assistant/test", {}, { timeout: ASSISTANT_HTTP_TIMEOUT_MS })
      .then((r) => r.data),
  // Photo question (disease detection): multipart upload, same 90s cap as
  // chat — Gemini vision answers take as long as text answers. The auth
  // interceptor attaches the token; do not hand-roll headers here.
  // conversation_id comes back as an int from this endpoint (string from
  // /assistant/chat), so callers must normalise with String(...).
  chatImage: (data: { image: File; message?: string; language: string; conversation_id?: string }) => {
    const fd = new FormData();
    fd.append("image", data.image);
    if (data.message) fd.append("message", data.message);
    fd.append("language", data.language);
    if (data.conversation_id) fd.append("conversation_id", data.conversation_id);
    return api
      .post<{
        reply: string;
        sources: Array<{ title: string; ref: string }>;
        conversation_id: string | number;
        mode: "gemini" | "template";
      }>("/assistant/chat-image", fd, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: ASSISTANT_HTTP_TIMEOUT_MS,
      })
      .then((r) => r.data);
  },
  conversations: () => api.get<AssistantConversation[]>("/assistant/conversations").then((r) => r.data),
  conversation: (id: string) => api.get<AssistantConversation>(`/assistant/conversations/${id}`).then((r) => r.data),
};

export interface SseEvent {
  type: string;
  data: string;
}

/** Parse complete SSE events out of a buffered chunk. Returns the events
 *  found plus the incomplete tail to carry into the next chunk. */
export function parseSseEvents(buffer: string): { events: SseEvent[]; rest: string } {
  const events: SseEvent[] = [];
  let rest = buffer;
  let idx = rest.indexOf("\n\n");
  while (idx !== -1) {
    const block = rest.slice(0, idx);
    rest = rest.slice(idx + 2);
    let type = "message";
    const dataLines: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) type = line.slice("event:".length).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice("data:".length).replace(/^ /, ""));
      // ":" comment lines and other fields are ignored
    }
    if (dataLines.length > 0) events.push({ type, data: dataLines.join("\n") });
    idx = rest.indexOf("\n\n");
  }
  return { events, rest };
}

/** Stream an assistant reply over fetch — NOT axios: the axios timeout
 *  (30s default, 90s for assistant calls) would cut a long stream, and
 *  axios cannot expose partial response bodies. Tokens arrive via onToken;
 *  resolves with the final `done` payload. Throws on HTTP errors, stream
 *  errors, or a missing done event so the caller can fall back to the
 *  non-stream chat endpoint. No timeout is applied here — the server
 *  bounds the stream instead (per-token read timeout + 180s total cap).
 *  Note: fetch does not run the axios 401-refresh interceptor, so an
 *  expired token surfaces as a stream failure and the axios fallback
 *  (which does refresh) picks it up. */
export async function streamAssistantChat(
  data: { conversation_id?: string; message: string; language: string },
  onToken: (text: string) => void,
  signal?: AbortSignal
): Promise<AssistantStreamDone> {
  const token = getAccessToken();
  const res = await fetch("/api/v1/assistant/chat/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(data),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`Stream failed (HTTP ${res.status})`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let done: AssistantStreamDone | null = null;
  for (;;) {
    const { value, done: readerDone } = await reader.read();
    if (value) buffer += decoder.decode(value, { stream: true });
    const { events, rest } = parseSseEvents(buffer);
    buffer = rest;
    for (const ev of events) {
      if (ev.type === "done") {
        done = JSON.parse(ev.data) as AssistantStreamDone;
      } else if (ev.type === "error") {
        let msg: string | undefined;
        try {
          msg = (JSON.parse(ev.data) as { error?: string }).error;
        } catch {
          msg = undefined;
        }
        throw new Error(msg || "Stream failed");
      } else {
        try {
          const chunk = JSON.parse(ev.data) as { text?: string };
          if (chunk.text) onToken(chunk.text);
        } catch {
          // ignore a malformed token chunk; the stream continues
        }
      }
    }
    if (done || readerDone) break;
  }
  if (!done) throw new Error("Stream ended without a result");
  return done;
}

export const logisticsApi = {
  plan: (data: LogisticsPlanIn) => api.post<LogisticsPlan>("/logistics/plan", data).then((r) => r.data),
  optimize: (data: LogisticsPlanIn) => api.post<LogisticsPlan>("/logistics/optimize", data).then((r) => r.data),
};

export const twinApi = {
  create: (data: {
    crop: string;
    origin_district: string;
    quantity_kg: number;
    variety?: string;
    harvested_at?: string | null;
    order_id?: number | null;
  }) => api.post<{ batch_code: string; public_url: string }>("/twin/batches", data).then((r) => r.data),
  mine: () => api.get<BatchMine[]>("/twin/batches/mine").then((r) => r.data),
  public: (code: string) => api.get<BatchPublic>(`/twin/public/${encodeURIComponent(code)}`).then((r) => r.data),
  verify: (code: string) =>
    api
      .get<{ valid: boolean; blocks: number; head_hash: string; unsealed_readings?: number; anchored_externally?: boolean }>(
        `/twin/batches/${encodeURIComponent(code)}/verify`
      )
      .then((r) => r.data),
  seal: (code: string) => api.post(`/twin/batches/${encodeURIComponent(code)}/seal`, {}).then((r) => r.data),
  qrUrl: (code: string) => `/api/v1/twin/batches/${encodeURIComponent(code)}/qr`,
};
