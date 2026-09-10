"use client"

import Link from "next/link"
import { ArrowUpRight, TrendingUp } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { PageHeader } from "@/components/records/page-header"
import { OwnerChip } from "@/components/records/owner-chip"
import { StatusBadge } from "@/components/records/status-badge"
import { useCrm } from "@/lib/crm-store"
import { money, moneyCompact, percent, relativeDay } from "@/lib/format"
import { pipelineMetrics } from "@/lib/metrics"
import { ORG } from "@/lib/seed"
import { OPEN_STAGES } from "@/lib/types"

const STAGE_COLORS: Record<string, string> = {
  Qualification: "var(--chart-4)",
  "Needs Analysis": "var(--chart-3)",
  "Value Proposition": "var(--chart-1)",
  "Proposal/Price Quote": "var(--chart-2)",
  "Negotiation/Review": "oklch(0.55 0.12 28)",
}

export function DashboardView() {
  const crm = useCrm()
  const metrics = pipelineMetrics(crm)
  const openStageMax = Math.max(
    ...OPEN_STAGES.map((stage) => metrics.byStage[stage]),
    1
  )

  return (
    <div>
      <PageHeader
        eyebrow={`${ORG.quarter} · ${ORG.name}`}
        title="Close what is already in motion."
        description="A Zoho CRM command center for Helios Industrial — live pipeline, blueprint-gated stages, and API v8 sync. This is the working org a client can click through."
      />

      <div className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi
          label="Open pipeline"
          value={moneyCompact(metrics.pipeline)}
          hint={`${metrics.openDeals.length} open deals`}
        />
        <Kpi
          label="Weighted forecast"
          value={moneyCompact(metrics.weighted)}
          hint="Probability × amount"
        />
        <Kpi
          label="Q3 won"
          value={moneyCompact(metrics.wonAmount)}
          hint={`${percent(metrics.quotaAttainment)} of ${moneyCompact(ORG.quota)} quota`}
        />
        <Kpi
          label="Win rate"
          value={percent(metrics.winRate)}
          hint={`${metrics.won.length} won · ${metrics.lost.length} lost`}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader className="border-b">
            <CardTitle>Pipeline by stage</CardTitle>
          </CardHeader>
          <CardContent className="pt-4">
            <div className="space-y-3">
              {OPEN_STAGES.map((stage) => {
                const amount = metrics.byStage[stage]
                const width = `${Math.max(6, (amount / openStageMax) * 100)}%`
                const count = crm.deals.filter((deal) => deal.stage === stage).length
                return (
                  <div key={stage}>
                    <div className="mb-1 flex items-center justify-between text-xs">
                      <span className="font-medium">{stage}</span>
                      <span className="text-muted-foreground">
                        {count} · {money(amount)}
                      </span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full transition-all"
                        style={{ width, background: STAGE_COLORS[stage] }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
            <div className="mt-5 flex items-center gap-2 rounded-xl bg-muted/70 px-3 py-3 text-sm">
              <TrendingUp className="text-primary size-4" />
              Coverage vs quota is {money(metrics.coverage)} ({percent((metrics.coverage / ORG.quota) * 100)}).
              Two negotiation deals close this month.
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="border-b">
            <CardTitle>Closing this month</CardTitle>
          </CardHeader>
          <CardContent className="pt-3">
            <ul className="space-y-3">
              {metrics.closingSoon.length === 0 ? (
                <li className="text-muted-foreground text-sm">No deals dated in September.</li>
              ) : (
                metrics.closingSoon.map((deal) => (
                  <li key={deal.id}>
                    <Link href={`/deals/${deal.id}`} className="group block">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-medium group-hover:underline">{deal.name}</p>
                          <p className="text-muted-foreground text-xs">
                            {relativeDay(deal.closingDate)} · {deal.probability}%
                          </p>
                        </div>
                        <p className="text-sm font-semibold">{moneyCompact(deal.amount)}</p>
                      </div>
                    </Link>
                  </li>
                ))
              )}
            </ul>
          </CardContent>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="border-b">
            <CardTitle>Team leaderboard</CardTitle>
          </CardHeader>
          <CardContent className="pt-2">
            <ul className="divide-y">
              {metrics.byOwner
                .filter((row) => row.user.quota > 0)
                .sort((a, b) => b.won + b.weighted - (a.won + a.weighted))
                .map((row) => (
                  <li key={row.user.id} className="flex items-center justify-between gap-3 py-3">
                    <OwnerChip user={row.user} />
                    <div className="text-right">
                      <p className="text-sm font-medium">{moneyCompact(row.won)} won</p>
                      <p className="text-muted-foreground text-xs">
                        {moneyCompact(row.pipeline)} open
                      </p>
                    </div>
                  </li>
                ))}
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="border-b">
            <CardTitle>Today’s motion</CardTitle>
          </CardHeader>
          <CardContent className="pt-3">
            <ul className="space-y-3">
              {crm.activities
                .filter((activity) => activity.status !== "Completed")
                .slice(0, 6)
                .map((activity) => (
                  <li key={activity.id} className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium">{activity.subject}</p>
                      <p className="text-muted-foreground text-xs">
                        {activity.type} · {activity.relatedName}
                      </p>
                    </div>
                    <StatusBadge value={activity.status} />
                  </li>
                ))}
            </ul>
            <Link
              href="/activities"
              className="text-primary mt-4 inline-flex items-center gap-1 text-sm font-medium"
            >
              Open activity list <ArrowUpRight className="size-3.5" />
            </Link>
          </CardContent>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Lead scoring</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="font-heading text-4xl">{metrics.scoring.hot} hot</p>
            <p className="text-muted-foreground mt-1 text-sm">
              {metrics.scoring.warm} warm · {metrics.scoring.cold} cold · avg {metrics.scoring.average}
            </p>
            <Link
              href="/scoring"
              className="text-primary mt-3 inline-flex items-center gap-1 text-sm font-medium"
            >
              Open scoring rules <ArrowUpRight className="size-3.5" />
            </Link>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Lead sources</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {Object.entries(metrics.sourceCounts).map(([source, count]) => (
              <div key={source} className="flex items-center justify-between text-sm">
                <span>{source}</span>
                <span className="font-medium">{count}</span>
              </div>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Zoho sync</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm">
              Last pull {crm.syncLog[0]?.endpoint} · {crm.syncLog[0]?.latencyMs}ms
            </p>
            <Link
              href="/integration"
              className="text-primary mt-3 inline-flex items-center gap-1 text-sm font-medium"
            >
              API map & webhooks <ArrowUpRight className="size-3.5" />
            </Link>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function Kpi({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <Card>
      <CardContent className="pt-1">
        <p className="text-muted-foreground text-[11px] tracking-wide uppercase">{label}</p>
        <p className="font-heading mt-2 text-3xl tracking-tight">{value}</p>
        <p className="text-muted-foreground mt-1 text-xs">{hint}</p>
      </CardContent>
    </Card>
  )
}
