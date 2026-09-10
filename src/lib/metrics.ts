import { OPEN_STAGES, type CrmState, type DealStage } from "./types"

export function pipelineMetrics(state: CrmState) {
  const openDeals = state.deals.filter((deal) => OPEN_STAGES.includes(deal.stage))
  const won = state.deals.filter((deal) => deal.stage === "Closed Won")
  const lost = state.deals.filter((deal) => deal.stage === "Closed Lost")
  const pipeline = openDeals.reduce((sum, deal) => sum + deal.amount, 0)
  const weighted = openDeals.reduce(
    (sum, deal) => sum + deal.amount * (deal.probability / 100),
    0
  )
  const wonAmount = won.reduce((sum, deal) => sum + deal.amount, 0)
  const lostAmount = lost.reduce((sum, deal) => sum + deal.amount, 0)
  const decided = won.length + lost.length
  const winRate = decided === 0 ? 0 : (won.length / decided) * 100
  const openLeads = state.leads.filter((lead) => !lead.converted && lead.status !== "Lost Lead" && lead.status !== "Unqualified")
  const coverage = wonAmount + weighted
  const quotaAttainment = (wonAmount / 4_200_000) * 100

  const byStage: Record<DealStage, number> = {
    Qualification: 0,
    "Needs Analysis": 0,
    "Value Proposition": 0,
    "Proposal/Price Quote": 0,
    "Negotiation/Review": 0,
    "Closed Won": 0,
    "Closed Lost": 0,
  }
  for (const deal of state.deals) {
    byStage[deal.stage] += deal.amount
  }

  const closingSoon = openDeals
    .filter((deal) => new Date(deal.closingDate) <= new Date("2026-09-30"))
    .sort((a, b) => new Date(a.closingDate).getTime() - new Date(b.closingDate).getTime())

  const byOwner = state.users.map((user) => {
    const owned = state.deals.filter((deal) => deal.ownerId === user.id)
    const open = owned.filter((deal) => OPEN_STAGES.includes(deal.stage))
    const userWon = owned.filter((deal) => deal.stage === "Closed Won")
    return {
      user,
      pipeline: open.reduce((sum, deal) => sum + deal.amount, 0),
      won: userWon.reduce((sum, deal) => sum + deal.amount, 0),
      weighted: open.reduce((sum, deal) => sum + deal.amount * (deal.probability / 100), 0),
    }
  })

  const sourceCounts = state.leads.reduce<Record<string, number>>((acc, lead) => {
    acc[lead.source] = (acc[lead.source] ?? 0) + 1
    return acc
  }, {})

  const scores = state.leads.filter((lead) => !lead.converted).map((lead) => lead.score)
  const scoring = {
    hot: scores.filter((value) => value >= 70).length,
    warm: scores.filter((value) => value >= 40 && value < 70).length,
    cold: scores.filter((value) => value < 40).length,
    average:
      scores.length === 0
        ? 0
        : Math.round(scores.reduce((sum, value) => sum + value, 0) / scores.length),
  }

  return {
    openDeals,
    won,
    lost,
    pipeline,
    weighted,
    wonAmount,
    lostAmount,
    winRate,
    openLeads,
    coverage,
    quotaAttainment,
    byStage,
    closingSoon,
    byOwner,
    sourceCounts,
    scoring,
  }
}
