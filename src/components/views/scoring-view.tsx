"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Switch } from "@/components/ui/switch"
import { PageHeader } from "@/components/records/page-header"
import { ScoreMeter } from "@/components/records/score-meter"
import { StatusBadge } from "@/components/records/status-badge"
import { useCrm } from "@/lib/crm-store"
import { SCORING_RULES, SCORE_THRESHOLDS, scoreDistribution } from "@/lib/scoring"
import Link from "next/link"

const categories = ["Firmographic", "Intent", "Behavioral", "Negative"] as const

export function ScoringView() {
  const crm = useCrm()
  const dist = scoreDistribution(crm.leads.filter((lead) => !lead.converted).map((lead) => lead.score))
  const ranked = [...crm.leads]
    .filter((lead) => !lead.converted)
    .sort((a, b) => b.score - a.score)

  return (
    <div>
      <PageHeader
        eyebrow="Scoring rules · Leads module"
        title="Score the fit, not the noise."
        description="Zoho-style positive and negative rules on firmographics, intent touchpoints, and activity. Toggle a rule — every lead recalculates, and Rating / Lead_Status follow the thresholds."
      />

      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <Card>
          <CardContent>
            <p className="text-muted-foreground text-[11px] tracking-wide uppercase">Hot ≥ {SCORE_THRESHOLDS.hot}</p>
            <p className="font-heading mt-1 text-3xl">{dist.hot}</p>
            <p className="text-muted-foreground text-sm">Priority queue for AEs</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <p className="text-muted-foreground text-[11px] tracking-wide uppercase">Warm ≥ {SCORE_THRESHOLDS.warm}</p>
            <p className="font-heading mt-1 text-3xl">{dist.warm}</p>
            <p className="text-muted-foreground text-sm">SDR working set</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <p className="text-muted-foreground text-[11px] tracking-wide uppercase">Cold</p>
            <p className="font-heading mt-1 text-3xl">{dist.cold}</p>
            <p className="text-muted-foreground text-sm">Nurture or recycle</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-5">
        <div className="space-y-4 xl:col-span-3">
          {categories.map((category) => {
            const rules = SCORING_RULES.filter((rule) => rule.category === category)
            return (
              <Card key={category}>
                <CardHeader className="border-b">
                  <CardTitle>{category} rules</CardTitle>
                </CardHeader>
                <CardContent className="divide-y p-0">
                  {rules.map((rule) => {
                    const active = !crm.disabledScoringRuleIds.includes(rule.id)
                    const firing = crm.leads.filter((lead) => {
                      const result = crm.scoreFor(lead.id)
                      return result?.hits.some((hit) => hit.ruleId === rule.id)
                    }).length
                    return (
                      <div key={rule.id} className="flex items-start gap-3 px-4 py-3">
                        <Switch
                          checked={active}
                          onCheckedChange={() => crm.toggleScoringRule(rule.id)}
                          aria-label={`Toggle ${rule.name}`}
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-baseline justify-between gap-2">
                            <p className="text-sm font-medium">{rule.name}</p>
                            <p
                              className={
                                rule.points >= 0
                                  ? "text-sm font-semibold text-[oklch(0.38_0.08_155)]"
                                  : "text-sm font-semibold text-[oklch(0.48_0.14_28)]"
                              }
                            >
                              {rule.points > 0 ? "+" : ""}
                              {rule.points}
                            </p>
                          </div>
                          <p className="text-muted-foreground mt-0.5 font-mono text-[11px]">
                            {rule.zohoCondition}
                          </p>
                          <p className="text-muted-foreground mt-1 text-xs">{rule.description}</p>
                          <p className="text-muted-foreground mt-1 text-[11px]">
                            Firing on {firing} lead{firing === 1 ? "" : "s"}
                          </p>
                        </div>
                      </div>
                    )
                  })}
                </CardContent>
              </Card>
            )
          })}
        </div>

        <Card className="xl:col-span-2">
          <CardHeader className="border-b">
            <CardTitle>Live leaderboard</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 pt-3">
            {ranked.map((lead) => (
              <Link
                key={lead.id}
                href={`/leads/${lead.id}`}
                className="flex items-center justify-between gap-3 rounded-xl px-1 py-1 hover:bg-muted/60"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {lead.firstName} {lead.lastName}
                  </p>
                  <p className="text-muted-foreground truncate text-xs">{lead.company}</p>
                </div>
                <div className="flex items-center gap-3">
                  <StatusBadge value={lead.rating} />
                  <ScoreMeter score={lead.score} size="sm" />
                </div>
              </Link>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card className="mt-4">
        <CardHeader className="border-b">
          <CardTitle>Threshold workflow (Deluge)</CardTitle>
        </CardHeader>
        <CardContent>
          <pre className="overflow-x-auto rounded-xl bg-[oklch(0.22_0.02_50)] p-4 font-mono text-[12px] leading-6 text-[oklch(0.93_0.02_90)]">
{`lead = zoho.crm.getRecordById("Leads", leadId);
score = lead.get("Lead_Score");
if(score >= ${SCORE_THRESHOLDS.hot})
{
  lead.put("Rating", "Hot");
  lead.put("Lead_Status", "Hot");
  zoho.crm.updateRecord("Leads", leadId, lead);
  notify = {"Email": "elena.voss@helios.ind", "Subject": "Hot lead " + lead.get("Full_Name")};
}
else if(score >= ${SCORE_THRESHOLDS.warm})
{
  lead.put("Rating", "Warm");
  zoho.crm.updateRecord("Leads", leadId, lead);
}
else
{
  lead.put("Rating", "Cold");
  zoho.crm.updateRecord("Leads", leadId, lead);
}`}
          </pre>
        </CardContent>
      </Card>
    </div>
  )
}
