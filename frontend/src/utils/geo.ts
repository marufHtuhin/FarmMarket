// Fallback hub + location data (used when the backend contract endpoints 404).
// Coordinates match backend/app/config.py (Bangladesh profile) and the legacy app.
export interface HubInfo {
  id: string;
  name: string;
  country: string;
  currency: string;
  lat: number;
  lon: number;
}

export const FALLBACK_HUBS: HubInfo[] = [
  { id: "dhaka", name: "Dhaka", country: "Bangladesh", currency: "BDT", lat: 23.8103, lon: 90.4125 },
  { id: "chattogram", name: "Chattogram", country: "Bangladesh", currency: "BDT", lat: 22.3569, lon: 91.7832 },
  { id: "rajshahi", name: "Rajshahi", country: "Bangladesh", currency: "BDT", lat: 24.3745, lon: 88.6042 },
  { id: "khulna", name: "Khulna", country: "Bangladesh", currency: "BDT", lat: 22.8456, lon: 89.5403 },
  { id: "sylhet", name: "Sylhet", country: "Bangladesh", currency: "BDT", lat: 24.8949, lon: 91.8687 },
];

export interface CountryInfo {
  code: string;
  name: string;
  currency: string;
  hubs: Array<{ id: string; name: string; lat: number; lon: number }>;
}

export const FALLBACK_COUNTRIES: CountryInfo[] = [
  {
    code: "BD",
    name: "Bangladesh",
    currency: "BDT",
    hubs: [
      { id: "dhaka", name: "Dhaka", lat: 23.8103, lon: 90.4125 },
      { id: "chattogram", name: "Chattogram", lat: 22.3569, lon: 91.7832 },
      { id: "rajshahi", name: "Rajshahi", lat: 24.3745, lon: 88.6042 },
      { id: "khulna", name: "Khulna", lat: 22.8456, lon: 89.5403 },
      { id: "sylhet", name: "Sylhet", lat: 24.8949, lon: 91.8687 },
    ],
  },
  { code: "KE", name: "Kenya", currency: "KES", hubs: [{ id: "nairobi", name: "Nairobi", lat: -1.2921, lon: 36.8219 }] },
  { code: "NG", name: "Nigeria", currency: "NGN", hubs: [{ id: "lagos", name: "Lagos", lat: 6.5244, lon: 3.3792 }] },
  { code: "GH", name: "Ghana", currency: "GHS", hubs: [{ id: "accra", name: "Accra", lat: 5.6037, lon: -0.187 }] },
  { code: "TZ", name: "Tanzania", currency: "TZS", hubs: [{ id: "dar_es_salaam", name: "Dar es Salaam", lat: -6.7924, lon: 39.2083 }] },
  { code: "UG", name: "Uganda", currency: "UGX", hubs: [{ id: "kampala", name: "Kampala", lat: 0.3476, lon: 32.5825 }] },
];

export interface BdLocation {
  name: string;
  lat: number;
  lon: number;
}

export const BD_LOCATIONS: BdLocation[] = [
  { name: "Dhaka", lat: 23.8103, lon: 90.4125 },
  { name: "Gazipur", lat: 23.9999, lon: 90.4203 },
  { name: "Savar", lat: 23.8583, lon: 90.2629 },
  { name: "Narayanganj", lat: 23.6238, lon: 90.5 },
  { name: "Tongi", lat: 23.8905, lon: 90.4013 },
  { name: "Keraniganj", lat: 23.7, lon: 90.45 },
  { name: "Chattogram", lat: 22.3569, lon: 91.7832 },
  { name: "Rajshahi", lat: 24.3745, lon: 88.6042 },
  { name: "Khulna", lat: 22.8456, lon: 89.5403 },
  { name: "Sylhet", lat: 24.8949, lon: 91.8687 },
  { name: "Mymensingh", lat: 24.7471, lon: 90.4203 },
  { name: "Cumilla", lat: 23.4682, lon: 91.1788 },
];

export const DEFAULT_DEPOT = { lat: 23.8103, lon: 90.4125 };
