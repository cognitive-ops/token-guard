import { describe, it, expect } from "vitest";
import { joinDeveloperCosts, summariseDeveloperCosts } from "./cost-model";

describe("joinDeveloperCosts", () => {
  const realCost = [
    { label: "a@scopic.com", value: 125 },
    { label: "b@scopic.com", value: 150 },
    { label: "c@scopic.com", value: 25 },
  ];
  const extraUsage = [{ label: "b@scopic.com", value: 50 }];

  it("joins on email and derives seat fee = real - extra", () => {
    const rows = joinDeveloperCosts(realCost, extraUsage);
    const b = rows.find((r) => r.email === "b@scopic.com")!;
    expect(b).toEqual({
      email: "b@scopic.com",
      realCost: 150,
      extraUsage: 50,
      seatFee: 100,
    });
  });

  it("defaults extra usage to 0 when a developer has none", () => {
    const a = joinDeveloperCosts(realCost, extraUsage).find(
      (r) => r.email === "a@scopic.com",
    )!;
    expect(a.extraUsage).toBe(0);
    expect(a.seatFee).toBe(125);
  });

  it("never reports a negative seat fee", () => {
    const rows = joinDeveloperCosts(
      [{ label: "x@scopic.com", value: 10 }],
      [{ label: "x@scopic.com", value: 40 }],
    );
    expect(rows[0]!.seatFee).toBe(0);
  });

  it("sorts by real cost descending", () => {
    const rows = joinDeveloperCosts(realCost, extraUsage);
    expect(rows.map((r) => r.email)).toEqual([
      "b@scopic.com",
      "a@scopic.com",
      "c@scopic.com",
    ]);
  });
});

describe("summariseDeveloperCosts", () => {
  it("totals real cost, seat fees, overage, and counts developers with overage", () => {
    const rows = joinDeveloperCosts(
      [
        { label: "a@scopic.com", value: 125 },
        { label: "b@scopic.com", value: 150 },
      ],
      [{ label: "b@scopic.com", value: 50 }],
    );
    expect(summariseDeveloperCosts(rows)).toEqual({
      totalReal: 275,
      totalSeatFees: 225,
      totalExtraUsage: 50,
      developersWithOverage: 1,
    });
  });
});
