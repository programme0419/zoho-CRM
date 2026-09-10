"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { PageHeader } from "@/components/records/page-header"
import { StatusBadge } from "@/components/records/status-badge"
import { useCrm } from "@/lib/crm-store"
import { formatDateTime } from "@/lib/format"

export function AutomationsView() {
  const { workflows } = useCrm()

  return (
    <div>
      <PageHeader
        eyebrow="Workflows · Blueprint · Assignment"
        title="The CRM should do the busywork."
        description="These rules are the implementation a Zoho admin would ship: scoring, legal checklists, convert handoff, stale proposals, and discount approval."
      />

      <div className="grid gap-4 lg:grid-cols-2">
        {workflows.map((rule) => (
          <Card key={rule.id}>
            <CardHeader className="border-b">
              <div className="flex items-start justify-between gap-3">
                <CardTitle className="text-base">{rule.name}</CardTitle>
                <StatusBadge value={rule.status} />
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-muted-foreground text-xs tracking-wide uppercase">
                {rule.module} · {rule.trigger}
              </p>
              <pre className="overflow-x-auto rounded-xl bg-muted/70 p-3 font-mono text-[11px] leading-relaxed">
                {rule.condition}
              </pre>
              <ul className="space-y-1 text-sm">
                {rule.actions.map((action) => (
                  <li key={action}>→ {action}</li>
                ))}
              </ul>
              <p className="text-muted-foreground text-xs">
                Last run {formatDateTime(rule.lastRun)} · {rule.runs} executions
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card className="mt-4">
        <CardHeader className="border-b">
          <CardTitle>Sample Deluge (Closed Won handoff)</CardTitle>
        </CardHeader>
        <CardContent>
          <pre className="overflow-x-auto rounded-xl bg-[oklch(0.22_0.02_50)] p-4 font-mono text-[12px] leading-6 text-[oklch(0.93_0.02_90)]">
{`deal = zoho.crm.getRecordById("Deals", dealId);
if(deal.get("Stage") == "Closed Won" && deal.get("PO_Number") != null)
{
  task = Map();
  task.put("Subject", "Customer kickoff — " + deal.get("Deal_Name"));
  task.put("Due_Date", zoho.currentdate.addDay(3));
  task.put("Owner", "usr_theo");
  task.put("What_Id", dealId);
  zoho.crm.createRecord("Tasks", task);
  invokeurl
  [
    url: "https://erp.helios.ind/orders"
    type: POST
    parameters: deal.toString()
  ];
}`}
          </pre>
        </CardContent>
      </Card>
    </div>
  )
}
