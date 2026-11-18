// Condition slugs come from the backend (WMO weather codes mapped in
// backend/app/services/datasources/openmeteo.py). This maps each slug to
// its i18n dictionary key so the label renders in Bangla or English.

const CONDITION_KEYS: Record<string, string> = {
  clear: "wxClear",
  partly_cloudy: "wxPartlyCloudy",
  overcast: "wxOvercast",
  fog: "wxFog",
  drizzle: "wxDrizzle",
  rain: "wxRainCond",
  snow: "wxSnow",
  thunderstorm: "wxThunder",
};

export function conditionLabelKey(condition: string | null | undefined): string {
  if (!condition) return "wxUnknown";
  return CONDITION_KEYS[condition] ?? "wxUnknown";
}

// Small emoji glyph per condition — a quick visual cue for farmers scanning
// the day list. Text labels always accompany the glyph (never glyph-only).
const CONDITION_GLYPHS: Record<string, string> = {
  clear: "☀️",
  partly_cloudy: "⛅",
  overcast: "☁️",
  fog: "🌫️",
  drizzle: "🌦️",
  rain: "🌧️",
  snow: "❄️",
  thunderstorm: "⛈️",
};

export function conditionGlyph(condition: string | null | undefined): string {
  if (!condition) return "❓";
  return CONDITION_GLYPHS[condition] ?? "❓";
}
