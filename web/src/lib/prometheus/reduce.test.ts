import { describe, it, expect } from "vitest";
import { lastNotNull, scalarFromSeries, valuesByLabel } from "./reduce";
import type { Series } from "./types";

const series = (labels: Record<string, string>, vals: number[]): Series => ({
  labels,
  samples: vals.map((v, i) => ({ t: 1000 + i, v })),
});

describe("lastNotNull", () => {
  it("returns the most recent finite sample", () => {
    expect(lastNotNull(series({}, [1, 2, 3]))).toBe(3);
  });

  it("skips trailing NaNs — the relayed-datasource lag case", () => {
    expect(lastNotNull(series({}, [5, 6, NaN]))).toBe(6);
  });

  it("returns null for an empty series", () => {
    expect(lastNotNull(series({}, []))).toBeNull();
  });

  it("returns null when every sample is NaN", () => {
    expect(lastNotNull(series({}, [NaN, NaN]))).toBeNull();
  });
});

describe("scalarFromSeries", () => {
  it("sums each series' last-not-null value", () => {
    const s = [series({ model: "a" }, [1, 2]), series({ model: "b" }, [10, 20])];
    expect(scalarFromSeries(s)).toBe(22);
  });

  it("treats empty series as zero", () => {
    expect(scalarFromSeries([series({}, []), series({}, [4])])).toBe(4);
  });
});

describe("valuesByLabel", () => {
  it("extracts and sorts rows by value descending", () => {
    const s = [
      series({ model: "haiku" }, [1, 5]),
      series({ model: "opus" }, [1, 99]),
      series({ model: "sonnet" }, [1, 40]),
    ];
    expect(valuesByLabel(s, "model")).toEqual([
      { label: "opus", value: 99 },
      { label: "sonnet", value: 40 },
      { label: "haiku", value: 5 },
    ]);
  });

  it("drops series missing the label or with no real samples", () => {
    const s = [series({ other: "x" }, [1]), series({ model: "a" }, [NaN])];
    expect(valuesByLabel(s, "model")).toEqual([]);
  });
});
