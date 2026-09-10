import type { Activity, Lead, LeadStatus, Note } from "./types"

export type ScoringCategory = "Firmographic" | "Intent" | "Behavioral" | "Negative"

export type LeadTouchpoints = {
  websiteSessions: number
  usedChpCalculator: boolean
  emailOpens: number
  emailClicks: number
}

export const EMPTY_TOUCHPOINTS: LeadTouchpoints = {
  websiteSessions: 0,
  usedChpCalculator: false,
  emailOpens: 0,
  emailClicks: 0,
}

export const SCORE_THRESHOLDS = {
  hot: 70,
  warm: 40,
} as const

export type ScoringRule = {
  id: string
  name: string
  category: ScoringCategory
  points: number
  zohoCondition: string
  description: string
  match: (ctx: ScoreContext) => boolean
}

export type ScoreHit = {
  ruleId: string
  name: string
  category: ScoringCategory
  points: number
  zohoCondition: string
}

export type ScoreResult = {
  total: number
  rating: "Hot" | "Warm" | "Cold"
  hits: ScoreHit[]
  missed: ScoreHit[]
}

export type ScoreContext = {
  lead: Lead
  activities: Activity[]
  notes: Note[]
  now: Date
}

const BUYER_TITLE =
  /\b(cfo|ceo|coo|cto|vp|vice president|director|head of|gm|general manager)\b/i

const CONSUMER_DOMAINS = new Set([
  "gmail.com",
  "yahoo.com",
  "hotmail.com",
  "outlook.com",
  "live.com",
  "icloud.com",
])

const DACH = new Set(["Germany", "Switzerland", "Austria"])

function daysBetween(iso: string, now: Date) {
  return Math.floor((now.getTime() - new Date(iso).getTime()) / (1000 * 60 * 60 * 24))
}

function emailDomain(email: string) {
  return email.split("@")[1]?.toLowerCase() ?? ""
}

function isCorporateEmail(email: string) {
  const domain = emailDomain(email)
  return Boolean(domain) && !CONSUMER_DOMAINS.has(domain)
}

function completed(activities: Activity[], leadId: string, type: Activity["type"]) {
  return activities.some(
    (activity) =>
      activity.relatedId === leadId && activity.type === type && activity.status === "Completed"
  )
}

function hasCompletedActivity(activities: Activity[], leadId: string) {
  return activities.some(
    (activity) => activity.relatedId === leadId && activity.status === "Completed"
  )
}

export const SCORING_RULES: ScoringRule[] = [
  {
    id: "sc_industry_utilities",
    name: "ICP industry — utilities",
    category: "Firmographic",
    points: 15,
    zohoCondition: "Industry is Utilities",
    description: "Helios ICP. Transmission, generation, and grid operators.",
    match: ({ lead }) => lead.industry === "Utilities",
  },
  {
    id: "sc_industry_mfg",
    name: "ICP industry — manufacturing",
    category: "Firmographic",
    points: 8,
    zohoCondition: "Industry is Manufacturing",
    description: "Heat-recovery fit for furnaces, casters, and plants.",
    match: ({ lead }) => lead.industry === "Manufacturing",
  },
  {
    id: "sc_industry_mining",
    name: "ICP industry — mining",
    category: "Firmographic",
    points: 7,
    zohoCondition: "Industry is Mining",
    description: "Off-grid and plant microgrid demand.",
    match: ({ lead }) => lead.industry === "Mining",
  },
  {
    id: "sc_industry_logistics",
    name: "ICP industry — logistics",
    category: "Firmographic",
    points: 5,
    zohoCondition: "Industry is Logistics",
    description: "Shore-power, terminals, and cold-chain loads.",
    match: ({ lead }) => lead.industry === "Logistics",
  },
  {
    id: "sc_industry_healthcare",
    name: "Campus healthcare",
    category: "Firmographic",
    points: 6,
    zohoCondition: "Industry is Healthcare",
    description: "Backup CHP and HVAC heat recovery.",
    match: ({ lead }) => lead.industry === "Healthcare",
  },
  {
    id: "sc_revenue_500",
    name: "Enterprise revenue ≥ $500M",
    category: "Firmographic",
    points: 18,
    zohoCondition: "Annual_Revenue >= 500000000",
    description: "Enterprise pipeline. Assign to Marcus.",
    match: ({ lead }) => lead.annualRevenue >= 500_000_000,
  },
  {
    id: "sc_revenue_150",
    name: "Upper mid-market ≥ $150M",
    category: "Firmographic",
    points: 12,
    zohoCondition: "Annual_Revenue >= 150000000 and Annual_Revenue < 500000000",
    description: "Serious capex budget.",
    match: ({ lead }) => lead.annualRevenue >= 150_000_000 && lead.annualRevenue < 500_000_000,
  },
  {
    id: "sc_revenue_50",
    name: "Mid-market ≥ $50M",
    category: "Firmographic",
    points: 6,
    zohoCondition: "Annual_Revenue >= 50000000 and Annual_Revenue < 150000000",
    description: "Worth an SDR sequence.",
    match: ({ lead }) => lead.annualRevenue >= 50_000_000 && lead.annualRevenue < 150_000_000,
  },
  {
    id: "sc_buyer_title",
    name: "Economic buyer title",
    category: "Firmographic",
    points: 12,
    zohoCondition: "Title contains CFO / VP / Director / Head / COO / CTO / GM",
    description: "Can sponsor capex.",
    match: ({ lead }) => BUYER_TITLE.test(lead.title),
  },
  {
    id: "sc_corporate_email",
    name: "Corporate email",
    category: "Firmographic",
    points: 5,
    zohoCondition: "Email domain not in gmail, yahoo, outlook, hotmail",
    description: "Work address, not a consumer mailbox.",
    match: ({ lead }) => isCorporateEmail(lead.email),
  },
  {
    id: "sc_dach",
    name: "Priority territory — DACH",
    category: "Firmographic",
    points: 6,
    zohoCondition: "Country in Germany, Switzerland, Austria",
    description: "Helios delivery coverage and references.",
    match: ({ lead }) => DACH.has(lead.country),
  },
  {
    id: "sc_source_website",
    name: "Inbound website",
    category: "Intent",
    points: 8,
    zohoCondition: "Lead_Source is Website",
    description: "Raised a hand. Same-day SLA.",
    match: ({ lead }) => lead.source === "Website",
  },
  {
    id: "sc_source_referral",
    name: "Customer referral",
    category: "Intent",
    points: 14,
    zohoCondition: "Lead_Source is Referral",
    description: "Highest close rate historically.",
    match: ({ lead }) => lead.source === "Referral",
  },
  {
    id: "sc_source_partner",
    name: "Partner-sourced",
    category: "Intent",
    points: 10,
    zohoCondition: "Lead_Source is Partner",
    description: "Local installer attached.",
    match: ({ lead }) => lead.source === "Partner",
  },
  {
    id: "sc_source_trade",
    name: "Trade show capture",
    category: "Intent",
    points: 6,
    zohoCondition: "Lead_Source is Trade Show",
    description: "Met face to face. Still needs qualification.",
    match: ({ lead }) => lead.source === "Trade Show",
  },
  {
    id: "sc_source_inbound_call",
    name: "Inbound call",
    category: "Intent",
    points: 5,
    zohoCondition: "Lead_Source is Inbound Call",
    description: "Spoke to sales already.",
    match: ({ lead }) => lead.source === "Inbound Call",
  },
  {
    id: "sc_source_outbound",
    name: "Outbound sequence",
    category: "Intent",
    points: 3,
    zohoCondition: "Lead_Source is Outbound",
    description: "We reached them. Lower intent than inbound.",
    match: ({ lead }) => lead.source === "Outbound",
  },
  {
    id: "sc_calculator",
    name: "Used CHP calculator",
    category: "Intent",
    points: 16,
    zohoCondition: "CHP_Calculator_Used is true (custom)",
    description: "High-intent web touchpoint from helios.ind/utilities.",
    match: ({ lead }) => lead.touchpoints.usedChpCalculator,
  },
  {
    id: "sc_email_click",
    name: "Clicked a campaign email",
    category: "Intent",
    points: 7,
    zohoCondition: "Email_Clicks >= 1 (custom)",
    description: "Campaign click-through from Zoho Campaigns / WorkDrive assets.",
    match: ({ lead }) => lead.touchpoints.emailClicks >= 1,
  },
  {
    id: "sc_sessions",
    name: "3+ website sessions",
    category: "Intent",
    points: 8,
    zohoCondition: "Website_Sessions >= 3 (custom)",
    description: "Repeat research on the product site.",
    match: ({ lead }) => lead.touchpoints.websiteSessions >= 3,
  },
  {
    id: "sc_energy_role",
    name: "Energy / plant / facilities role",
    category: "Firmographic",
    points: 6,
    zohoCondition: "Title contains Energy, Plant, Facilities, Procurement, or Sustainability",
    description: "Day-to-day owner of the load Helios sells into.",
    match: ({ lead }) =>
      /\b(energy|plant|facilities|procurement|sustainability)\b/i.test(lead.title),
  },
  {
    id: "sc_call_done",
    name: "Completed discovery call",
    category: "Behavioral",
    points: 8,
    zohoCondition: "Related Calls where Status is Completed",
    description: "Activity related list on the lead.",
    match: ({ lead, activities }) => completed(activities, lead.id, "Call"),
  },
  {
    id: "sc_meeting_done",
    name: "Completed meeting",
    category: "Behavioral",
    points: 10,
    zohoCondition: "Related Events where Status is Completed",
    description: "On-site or workshop logged.",
    match: ({ lead, activities }) => completed(activities, lead.id, "Meeting"),
  },
  {
    id: "sc_note",
    name: "Has a sales note",
    category: "Behavioral",
    points: 3,
    zohoCondition: "Notes count > 0",
    description: "Someone in the team has context.",
    match: ({ lead, notes }) => notes.some((note) => note.recordId === lead.id),
  },
  {
    id: "sc_fresh",
    name: "Created in last 14 days",
    category: "Behavioral",
    points: 6,
    zohoCondition: "Created_Time in last 14 days",
    description: "Recency boost. Helios SLA is same-week follow-up.",
    match: ({ lead, now }) => daysBetween(lead.createdTime, now) <= 14,
  },
  {
    id: "sc_personal_email",
    name: "Consumer mailbox",
    category: "Negative",
    points: -10,
    zohoCondition: "Email domain in gmail, yahoo, outlook, hotmail",
    description: "Usually a tire-kicker or personal inquiry.",
    match: ({ lead }) => Boolean(lead.email) && !isCorporateEmail(lead.email),
  },
  {
    id: "sc_small",
    name: "Too small — revenue under $30M",
    category: "Negative",
    points: -12,
    zohoCondition: "Annual_Revenue > 0 and Annual_Revenue < 30000000",
    description: "Below Helios mid-market floor.",
    match: ({ lead }) => lead.annualRevenue > 0 && lead.annualRevenue < 30_000_000,
  },
  {
    id: "sc_unqualified",
    name: "Marked unqualified",
    category: "Negative",
    points: -30,
    zohoCondition: "Lead_Status is Unqualified",
    description: "Hard stop. Score should not look like a priority.",
    match: ({ lead }) => lead.status === "Unqualified",
  },
  {
    id: "sc_lost",
    name: "Lost lead",
    category: "Negative",
    points: -40,
    zohoCondition: "Lead_Status is Lost Lead",
    description: "Closed out. Do not recycle until next FY.",
    match: ({ lead }) => lead.status === "Lost Lead",
  },
  {
    id: "sc_stale",
    name: "Stale — 45 days, no completed activity",
    category: "Negative",
    points: -10,
    zohoCondition: "Created_Time older than 45 days and no completed related activity",
    description: "Decay. Re-engage or recycle.",
    match: ({ lead, activities, now }) =>
      daysBetween(lead.createdTime, now) > 45 && !hasCompletedActivity(activities, lead.id),
  },
]

export function ratingFromScore(total: number): "Hot" | "Warm" | "Cold" {
  if (total >= SCORE_THRESHOLDS.hot) return "Hot"
  if (total >= SCORE_THRESHOLDS.warm) return "Warm"
  return "Cold"
}

export function clampScore(total: number) {
  return Math.max(0, Math.min(100, total))
}

export function scoreLead(
  ctx: ScoreContext,
  disabledRuleIds: string[] = []
): ScoreResult {
  const disabled = new Set(disabledRuleIds)
  const hits: ScoreHit[] = []
  const missed: ScoreHit[] = []

  for (const rule of SCORING_RULES) {
    if (disabled.has(rule.id)) continue
    const row: ScoreHit = {
      ruleId: rule.id,
      name: rule.name,
      category: rule.category,
      points: rule.points,
      zohoCondition: rule.zohoCondition,
    }
    if (rule.match(ctx)) hits.push(row)
    else missed.push(row)
  }

  const raw = hits.reduce((sum, hit) => sum + hit.points, 0)
  const total = clampScore(raw)
  return {
    total,
    rating: ratingFromScore(total),
    hits,
    missed,
  }
}

export function nextLeadStatus(lead: Lead, score: number): LeadStatus {
  if (lead.converted) return lead.status
  if (lead.status === "Unqualified" || lead.status === "Lost Lead") return lead.status
  if (score >= SCORE_THRESHOLDS.hot) return "Hot"
  if (lead.status === "Hot" && score < SCORE_THRESHOLDS.hot) return "Qualified"
  return lead.status
}

export function scoreDistribution(totals: number[]) {
  return {
    hot: totals.filter((value) => value >= SCORE_THRESHOLDS.hot).length,
    warm: totals.filter(
      (value) => value >= SCORE_THRESHOLDS.warm && value < SCORE_THRESHOLDS.hot
    ).length,
    cold: totals.filter((value) => value < SCORE_THRESHOLDS.warm).length,
  }
}
