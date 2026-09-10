import assert from "node:assert/strict"
import { test } from "node:test"
import {
  clampScore,
  EMPTY_TOUCHPOINTS,
  nextLeadStatus,
  ratingFromScore,
  scoreLead,
  SCORE_THRESHOLDS,
} from "./scoring.ts"
import type { Activity, Lead } from "./types.ts"

const NOW = new Date("2026-09-10T12:00:00.000Z")

function makeLead(overrides: Partial<Lead> = {}): Lead {
  return {
    id: "led_test",
    firstName: "Sabine",
    lastName: "Keller",
    company: "Alpine Grid Services",
    title: "Program Manager",
    email: "sabine.keller@alpinegrid.ch",
    phone: "",
    status: "Not Contacted",
    source: "Website",
    industry: "Utilities",
    annualRevenue: 220_000_000,
    rating: "Cold",
    ownerId: "usr_jonah",
    score: 0,
    city: "Zurich",
    country: "Switzerland",
    createdTime: "2026-08-28T07:14:00.000Z",
    converted: false,
    touchpoints: {
      websiteSessions: 5,
      usedChpCalculator: true,
      emailOpens: 4,
      emailClicks: 2,
    },
    ...overrides,
  }
}

function score(
  lead: Lead,
  extra: { activities?: Activity[]; disabled?: string[] } = {}
) {
  return scoreLead(
    {
      lead,
      activities: extra.activities ?? [],
      notes: [],
      now: NOW,
    },
    extra.disabled ?? []
  )
}

test("utilities inbound with calculator scores Hot", () => {
  const result = score(makeLead())
  assert.equal(result.rating, "Hot")
  assert.ok(result.total >= SCORE_THRESHOLDS.hot)
  assert.ok(result.hits.some((hit) => hit.ruleId === "sc_industry_utilities"))
  assert.ok(result.hits.some((hit) => hit.ruleId === "sc_calculator"))
  assert.ok(result.hits.some((hit) => hit.ruleId === "sc_dach"))
})

test("unqualified small lead is Cold and keeps Unqualified", () => {
  const lead = makeLead({
    status: "Unqualified",
    industry: "Materials",
    annualRevenue: 22_000_000,
    source: "Trade Show",
    title: "Site Director",
    country: "Sweden",
    email: "jonas.bergstrom@fjordpulp.se",
    touchpoints: EMPTY_TOUCHPOINTS,
    createdTime: "2026-08-03T14:33:00.000Z",
  })
  const result = score(lead)
  assert.equal(result.rating, "Cold")
  assert.ok(result.hits.some((hit) => hit.ruleId === "sc_unqualified"))
  assert.ok(result.hits.some((hit) => hit.ruleId === "sc_small"))
  assert.equal(nextLeadStatus(lead, result.total), "Unqualified")
})

test("lost-lead penalty keeps Lost Lead", () => {
  const lead = makeLead({
    status: "Lost Lead",
    industry: "Manufacturing",
    annualRevenue: 61_000_000,
    country: "Poland",
    createdTime: "2026-06-22T11:47:00.000Z",
    touchpoints: EMPTY_TOUCHPOINTS,
  })
  const result = score(lead)
  assert.ok(result.hits.some((hit) => hit.ruleId === "sc_lost"))
  assert.equal(nextLeadStatus(lead, result.total), "Lost Lead")
})

test("CHP calculator is worth 16 points", () => {
  const base = makeLead({
    touchpoints: EMPTY_TOUCHPOINTS,
    source: "Outbound",
    industry: "Materials",
    annualRevenue: 80_000_000,
    country: "Spain",
  })
  const without = score(base)
  const withCalc = score({
    ...base,
    touchpoints: { ...EMPTY_TOUCHPOINTS, usedChpCalculator: true },
  })
  assert.equal(withCalc.total - without.total, 16)
})

test("completed discovery call adds 8 behavioral points", () => {
  const lead = makeLead({ id: "led_mei", touchpoints: EMPTY_TOUCHPOINTS })
  const before = score(lead, { activities: [] })
  const after = score(lead, {
    activities: [
      {
        id: "act_test",
        subject: "Discovery",
        type: "Call",
        status: "Completed",
        dueDate: NOW.toISOString(),
        ownerId: "usr_jonah",
        relatedModule: "Leads",
        relatedId: "led_mei",
        relatedName: "Mei Tan",
        notes: "",
      },
    ],
  })
  assert.equal(after.total - before.total, 8)
})

test("disabling the utilities rule drops the total", () => {
  const full = score(makeLead())
  const cut = score(makeLead(), { disabled: ["sc_industry_utilities"] })
  assert.ok(cut.total < full.total)
  assert.ok(!cut.hits.some((hit) => hit.ruleId === "sc_industry_utilities"))
})

test("threshold helper and clamp", () => {
  assert.equal(ratingFromScore(70), "Hot")
  assert.equal(ratingFromScore(40), "Warm")
  assert.equal(ratingFromScore(39), "Cold")
  assert.equal(clampScore(-12), 0)
  assert.equal(clampScore(140), 100)
})

test("crossing 70 promotes an open lead to Hot", () => {
  const lead = makeLead({ status: "Contacted" })
  assert.equal(nextLeadStatus(lead, 72), "Hot")
  assert.equal(nextLeadStatus(lead, 50), "Contacted")
})
