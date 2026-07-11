import { describe, it, expect } from "vitest";
import {
  parseRangeDays,
  chooseStep,
  rangeForDays,
  asPromDuration,
} from "./time-range";

describe("parseRangeDays", () => {
  it("parses a valid preset", () => {
    expect(parseRangeDays("7d", 30)).toBe(7);
  });

  it("falls back for unknown presets, garbage, or missing param", () => {
    expect(parseRangeDays("99d", 30)).toBe(30);
    expect(parseRangeDays("abc", 30)).toBe(30);
    expect(parseRangeDays(undefined, 30)).toBe(30);
  });

  it("takes the first value when given an array", () => {
    expect(parseRangeDays(["14d", "7d"], 30)).toBe(14);
  });
});

describe("chooseStep", () => {
  it("never returns less than the 60s floor", () => {
    expect(chooseStep(600)).toBe(60);
  });

  it("scales the step up for wider windows", () => {
    const week = chooseStep(7 * 86400);
    const month = chooseStep(30 * 86400);
    expect(month).toBeGreaterThan(week);
    expect(month % 60).toBe(0);
  });
});

describe("rangeForDays", () => {
  it("builds a window ending at now with a positive step", () => {
    const r = rangeForDays(30, 1_000_000);
    expect(r.end).toBe(1_000_000);
    expect(r.start).toBe(1_000_000 - 30 * 86400);
    expect(r.windowSeconds).toBe(30 * 86400);
    expect(r.step).toBeGreaterThan(0);
  });
});

describe("asPromDuration", () => {
  it("formats seconds as a day-duration literal", () => {
    expect(asPromDuration(30 * 86400)).toBe("30d");
    expect(asPromDuration(7 * 86400)).toBe("7d");
  });
});
