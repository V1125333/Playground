import type { ProfileExperienceDate, StructuredLocation } from "../resume/types";

const US_STATE_NAMES: Record<string, string> = {
  al: "Alabama",
  ak: "Alaska",
  az: "Arizona",
  ar: "Arkansas",
  ca: "California",
  co: "Colorado",
  ct: "Connecticut",
  dc: "District of Columbia",
  fl: "Florida",
  ga: "Georgia",
  il: "Illinois",
  ma: "Massachusetts",
  mo: "Missouri",
  nj: "New Jersey",
  ny: "New York",
  pa: "Pennsylvania",
  tx: "Texas",
  va: "Virginia",
  wa: "Washington",
};

const INDIAN_STATES = new Set([
  "andhra pradesh",
  "telangana",
  "karnataka",
  "tamil nadu",
  "maharashtra",
  "kerala",
  "delhi",
  "gujarat",
  "west bengal",
]);

const MONTH_LABELS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export type LocationMigrationResult = {
  location: StructuredLocation;
  displayValue: string;
  requiresReview: boolean;
  legacyNotes?: string;
};

export function normalizeStructuredLocation(value: Partial<StructuredLocation> | null | undefined): StructuredLocation {
  return {
    city: clean(value?.city ?? ""),
    state: clean(value?.state ?? "") || null,
    country: clean(value?.country ?? ""),
  };
}

export function formatLocationDisplay(location: Partial<StructuredLocation> | null | undefined): string {
  const normalized = normalizeStructuredLocation(location);
  const countryKey = normalized.country.toLowerCase();
  const shouldHideCountry = countryKey === "united states" || countryKey === "usa" || countryKey === "us";
  return [normalized.city, normalized.state, shouldHideCountry ? "" : normalized.country].filter(Boolean).join(", ");
}

export function validateStructuredLocation(location: Partial<StructuredLocation> | null | undefined, label = "Location"): string[] {
  const normalized = normalizeStructuredLocation(location);
  const errors: string[] = [];
  if (!normalized.city) errors.push(`${label} city is required.`);
  if (!normalized.country) errors.push(`${label} country is required.`);
  const countryKey = normalized.country.toLowerCase();
  if (normalized.country && normalized.city && countryKey === normalized.city.toLowerCase()) {
    errors.push(`${label} country cannot be the same as city.`);
  }
  if (normalized.country && isUsStateAbbreviation(normalized.country)) {
    errors.push(`${label} country cannot be a US state abbreviation.`);
  }
  if (normalized.country && INDIAN_STATES.has(countryKey)) {
    errors.push(`${label} country cannot be an Indian state name.`);
  }
  return errors;
}

export function migrateLegacyLocation(value: string | Partial<StructuredLocation> | null | undefined): LocationMigrationResult {
  if (value && typeof value === "object") {
    const location = normalizeStructuredLocation(value);
    return {
      location,
      displayValue: formatLocationDisplay(location),
      requiresReview: validateStructuredLocation(location).length > 0,
    };
  }

  const raw = clean(value ?? "");
  if (!raw) {
    return { location: { city: "", state: null, country: "" }, displayValue: "", requiresReview: false };
  }

  const parts = raw.split(",").map((part) => clean(part)).filter(Boolean);
  if (parts.length >= 3) {
    const location = normalizeStructuredLocation({ city: parts[0], state: parts[1], country: parts.slice(2).join(", ") });
    return { location, displayValue: formatLocationDisplay(location), requiresReview: validateStructuredLocation(location).length > 0 };
  }
  if (parts.length === 2) {
    const [city, region] = parts;
    if (isUsStateAbbreviation(region)) {
      const location = { city, state: region.toUpperCase(), country: "United States" };
      return { location, displayValue: formatLocationDisplay(location), requiresReview: false };
    }
    if (INDIAN_STATES.has(region.toLowerCase())) {
      const location = { city, state: region, country: "India" };
      return { location, displayValue: formatLocationDisplay(location), requiresReview: false };
    }
    const location = { city, state: region, country: "" };
    return { location, displayValue: raw, requiresReview: true, legacyNotes: raw };
  }

  const location = { city: parts[0] ?? raw, state: null, country: "" };
  return { location, displayValue: raw, requiresReview: true, legacyNotes: raw };
}

export function parseProfileDate(value: string | ProfileExperienceDate | null | undefined): ProfileExperienceDate | null {
  if (!value) return null;
  if (typeof value === "object") {
    const year = Number(value.year) || 0;
    const month = Number(value.month) || 0;
    return year ? { year, month } : null;
  }
  const trimmed = clean(value);
  const match = trimmed.match(/^(\d{4})(?:-(\d{1,2}))?$/);
  if (!match) return null;
  return { year: Number(match[1]), month: match[2] ? Number(match[2]) : 0 };
}

export function formatProfileDate(value: ProfileExperienceDate | null | undefined): string {
  if (!value?.year) return "";
  const month = value.month >= 1 && value.month <= 12 ? MONTH_LABELS[value.month] : "";
  return [month, String(value.year)].filter(Boolean).join(" ");
}

export function profileDateInputValue(value: ProfileExperienceDate | null | undefined): string {
  if (!value?.year) return "";
  const month = value.month >= 1 && value.month <= 12 ? String(value.month).padStart(2, "0") : "01";
  return `${value.year}-${month}`;
}

export function datePrecedes(left: ProfileExperienceDate | null | undefined, right: ProfileExperienceDate | null | undefined): boolean {
  if (!left?.year || !right?.year) return false;
  const leftMonth = left.month || 1;
  const rightMonth = right.month || 1;
  return left.year < right.year || (left.year === right.year && leftMonth < rightMonth);
}

export function splitLines(value: string): string[] {
  return value.split(/\r?\n/).map((item) => clean(item).replace(/^\d+[.)]\s*/, "")).filter(Boolean);
}

export function clean(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function isUsStateAbbreviation(value: string): boolean {
  return Object.prototype.hasOwnProperty.call(US_STATE_NAMES, value.toLowerCase());
}

