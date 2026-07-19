import { describe, expect, it } from "vitest";
import {
  datePrecedes,
  formatLocationDisplay,
  formatProfileDate,
  migrateLegacyLocation,
  parseProfileDate,
  splitLines,
  validateStructuredLocation,
} from "./profileData";

describe("profileData", () => {
  it("formats United States locations without repeating the country", () => {
    expect(formatLocationDisplay({ city: "Hartford", state: "CT", country: "United States" })).toBe("Hartford, CT");
    expect(formatLocationDisplay({ city: "Chicago", state: "IL", country: "USA" })).toBe("Chicago, IL");
  });

  it("formats non-US locations with city, state, and country", () => {
    expect(formatLocationDisplay({ city: "Visakhapatnam", state: "Andhra Pradesh", country: "India" })).toBe(
      "Visakhapatnam, Andhra Pradesh, India",
    );
  });

  it("migrates known US state abbreviations to United States", () => {
    expect(migrateLegacyLocation("Hartford, CT")).toMatchObject({
      location: { city: "Hartford", state: "CT", country: "United States" },
      displayValue: "Hartford, CT",
      requiresReview: false,
    });
    expect(migrateLegacyLocation("Chicago, IL")).toMatchObject({
      location: { city: "Chicago", state: "IL", country: "United States" },
      displayValue: "Chicago, IL",
      requiresReview: false,
    });
  });

  it("migrates known Indian states to India", () => {
    expect(migrateLegacyLocation("Hyderabad, Telangana")).toMatchObject({
      location: { city: "Hyderabad", state: "Telangana", country: "India" },
      displayValue: "Hyderabad, Telangana, India",
      requiresReview: false,
    });
    expect(migrateLegacyLocation("Visakhapatnam, Andhra Pradesh")).toMatchObject({
      location: { city: "Visakhapatnam", state: "Andhra Pradesh", country: "India" },
      displayValue: "Visakhapatnam, Andhra Pradesh, India",
      requiresReview: false,
    });
  });

  it("flags ambiguous legacy locations instead of guessing a country", () => {
    expect(migrateLegacyLocation("Hyderabad")).toMatchObject({
      location: { city: "Hyderabad", state: null, country: "" },
      requiresReview: true,
      legacyNotes: "Hyderabad",
    });
    expect(migrateLegacyLocation("Paris, Ontario")).toMatchObject({
      location: { city: "Paris", state: "Ontario", country: "" },
      requiresReview: true,
      legacyNotes: "Paris, Ontario",
    });
  });

  it("keeps structured locations idempotent", () => {
    const first = migrateLegacyLocation("Hartford, CT");
    const second = migrateLegacyLocation(first.location);

    expect(second).toMatchObject({
      location: first.location,
      displayValue: first.displayValue,
      requiresReview: false,
    });
  });

  it("rejects invalid country values", () => {
    expect(validateStructuredLocation({ city: "Hartford", state: "CT", country: "CT" })).toContain(
      "Location country cannot be a US state abbreviation.",
    );
    expect(validateStructuredLocation({ city: "Hyderabad", state: null, country: "Hyderabad" })).toContain(
      "Location country cannot be the same as city.",
    );
    expect(validateStructuredLocation({ city: "Visakhapatnam", state: null, country: "Andhra Pradesh" })).toContain(
      "Location country cannot be an Indian state name.",
    );
  });

  it("derives date display and compares structured dates", () => {
    expect(parseProfileDate("2025-01")).toEqual({ month: 1, year: 2025 });
    expect(formatProfileDate({ month: 1, year: 2025 })).toBe("Jan 2025");
    expect(datePrecedes({ month: 12, year: 2024 }, { month: 1, year: 2025 })).toBe(true);
  });

  it("normalizes numbered legacy lines without marking them as metrics", () => {
    expect(splitLines("1. Developed API updates\n2) Reviewed SQL changes")).toEqual([
      "Developed API updates",
      "Reviewed SQL changes",
    ]);
  });
});
