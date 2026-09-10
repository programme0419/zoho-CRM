"use client"

import { useState } from "react"
import Link from "next/link"
import { toast } from "sonner"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { OwnerChip } from "@/components/records/owner-chip"
import { PageHeader } from "@/components/records/page-header"
import { StatusBadge } from "@/components/records/status-badge"
import { useCrm } from "@/lib/crm-store"
import { money, moneyCompact, relativeDay } from "@/lib/format"
import { OPEN_STAGES, STAGE_ORDER, type DealStage } from "@/lib/types"

export function DealsView() {
  const crm = useCrm()
  const [tab, setTab] = useState("board")

  function onDrop(dealId: string, stage: DealStage) {
    const result = crm.moveDeal(dealId, stage)
    if (!result.ok) toast.error(result.message)
    else toast.success(result.message)
  }

  return (
    <div>
      <PageHeader
        eyebrow="Deals module"
        title="The quarter, in columns."
        description="Enterprise pipeline with Zoho Blueprint gates. Drag a card — discovery calls, PO numbers, and lost reasons are enforced."
      />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="board">Kanban</TabsTrigger>
          <TabsTrigger value="list">List</TabsTrigger>
        </TabsList>
        <TabsContent value="board" className="mt-4">
          <div className="flex gap-3 overflow-x-auto pb-4">
            {OPEN_STAGES.map((stage) => {
              const column = crm.deals.filter((deal) => deal.stage === stage)
              const total = column.reduce((sum, deal) => sum + deal.amount, 0)
              return (
                <div
                  key={stage}
                  className="w-72 shrink-0 rounded-2xl border border-border bg-card/80 p-3"
                  onDragOver={(event) => event.preventDefault()}
                  onDrop={(event) => {
                    const dealId = event.dataTransfer.getData("text/deal-id")
                    if (dealId) onDrop(dealId, stage)
                  }}
                >
                  <div className="mb-3 flex items-baseline justify-between gap-2 px-1">
                    <p className="text-sm font-medium">{stage}</p>
                    <p className="text-muted-foreground text-xs">
                      {column.length} · {moneyCompact(total)}
                    </p>
                  </div>
                  <div className="space-y-2">
                    {column.map((deal) => (
                      <Link
                        key={deal.id}
                        href={`/deals/${deal.id}`}
                        draggable
                        onDragStart={(event) => {
                          event.dataTransfer.setData("text/deal-id", deal.id)
                          event.dataTransfer.effectAllowed = "move"
                        }}
                        className="block rounded-xl border border-border bg-background p-3 shadow-sm hover:border-primary/30"
                      >
                        <p className="text-sm font-medium text-pretty">{deal.name}</p>
                        <p className="text-muted-foreground mt-1 text-xs">
                          {crm.accountById(deal.accountId)?.name}
                        </p>
                        <div className="mt-3 flex items-center justify-between">
                          <p className="text-sm font-semibold">{money(deal.amount)}</p>
                          <p className="text-muted-foreground text-[11px]">
                            {relativeDay(deal.closingDate)}
                          </p>
                        </div>
                      </Link>
                    ))}
                  </div>
                </div>
              )
            })}
            <div className="w-64 shrink-0 space-y-3">
              {(["Closed Won", "Closed Lost"] as DealStage[]).map((stage) => {
                const column = crm.deals.filter((deal) => deal.stage === stage)
                return (
                  <div
                    key={stage}
                    className="rounded-2xl border border-dashed border-border p-3"
                    onDragOver={(event) => event.preventDefault()}
                    onDrop={(event) => {
                      const dealId = event.dataTransfer.getData("text/deal-id")
                      if (dealId) onDrop(dealId, stage)
                    }}
                  >
                    <p className="mb-2 text-sm font-medium">{stage}</p>
                    {column.slice(0, 3).map((deal) => (
                      <Link
                        key={deal.id}
                        href={`/deals/${deal.id}`}
                        className="mb-2 block text-xs hover:underline"
                      >
                        {deal.name}
                      </Link>
                    ))}
                  </div>
                )
              })}
            </div>
          </div>
        </TabsContent>
        <TabsContent value="list" className="mt-4">
          <div className="overflow-hidden rounded-2xl border border-border bg-card">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Deal</TableHead>
                  <TableHead>Stage</TableHead>
                  <TableHead>Amount</TableHead>
                  <TableHead>Close</TableHead>
                  <TableHead>Pipeline</TableHead>
                  <TableHead>Owner</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {[...crm.deals]
                  .sort(
                    (a, b) => STAGE_ORDER.indexOf(a.stage) - STAGE_ORDER.indexOf(b.stage)
                  )
                  .map((deal) => (
                    <TableRow key={deal.id}>
                      <TableCell>
                        <Link href={`/deals/${deal.id}`} className="font-medium hover:underline">
                          {deal.name}
                        </Link>
                        <p className="text-muted-foreground text-xs">
                          {crm.accountById(deal.accountId)?.name}
                        </p>
                      </TableCell>
                      <TableCell>
                        <StatusBadge value={deal.stage} />
                      </TableCell>
                      <TableCell>{money(deal.amount)}</TableCell>
                      <TableCell>{relativeDay(deal.closingDate)}</TableCell>
                      <TableCell>
                        <StatusBadge value={deal.pipeline} />
                      </TableCell>
                      <TableCell>
                        <OwnerChip user={crm.userById(deal.ownerId)} />
                      </TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
