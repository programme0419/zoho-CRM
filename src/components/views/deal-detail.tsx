"use client"

import { useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { FieldList } from "@/components/records/field-list"
import { OwnerChip } from "@/components/records/owner-chip"
import { PageHeader } from "@/components/records/page-header"
import { StatusBadge } from "@/components/records/status-badge"
import { useCrm } from "@/lib/crm-store"
import { formatDate, money, percent } from "@/lib/format"
import { STAGE_ORDER, type DealStage } from "@/lib/types"

const BLUEPRINT = [
  { stage: "Qualification", rule: "Company, email, and annual revenue on the account." },
  { stage: "Needs Analysis", rule: "Completed discovery call or meeting on this deal." },
  { stage: "Value Proposition", rule: "Product mapped and next step dated." },
  { stage: "Proposal/Price Quote", rule: "Amount greater than zero." },
  { stage: "Negotiation/Review", rule: "Legal checklist workflow creates a 2-day task." },
  { stage: "Closed Won", rule: "PO Number required. Discount > 12% needs VP approval." },
]

export function DealDetail({ dealId }: { dealId: string }) {
  const crm = useCrm()
  const router = useRouter()
  const deal = crm.deals.find((item) => item.id === dealId)
  const [po, setPo] = useState(deal?.poNumber ?? "")
  const [lostReason, setLostReason] = useState(deal?.lostReason ?? "")

  if (!deal) {
    return (
      <div className="py-20 text-center">
        <p className="font-heading text-2xl">Deal not found</p>
        <Button className="mt-4" variant="outline" onClick={() => router.push("/deals")}>
          Back to pipeline
        </Button>
      </div>
    )
  }

  const account = crm.accountById(deal.accountId)
  const contact = crm.contactById(deal.contactId)
  const activities = crm.activities.filter((activity) => activity.relatedId === deal.id)
  const notes = crm.notes.filter((note) => note.recordId === deal.id)

  function saveExtras() {
    crm.dispatch({
      type: "patch-deal",
      dealId,
      patch: { poNumber: po || undefined, lostReason: lostReason || undefined },
    })
    toast.success("Deal fields saved. Blueprint will re-evaluate on the next stage move.")
  }

  function move(stage: DealStage) {
    const result = crm.moveDeal(dealId, stage)
    if (!result.ok) toast.error(result.message)
    else toast.success(result.message)
  }

  return (
    <div>
      <PageHeader
        eyebrow={`${deal.pipeline} pipeline`}
        title={deal.name}
        description={deal.nextStep}
        actions={
          <>
            <StatusBadge value={deal.stage} />
            <p className="text-lg font-semibold">{money(deal.amount)}</p>
          </>
        }
      />

      <div className="mb-4 overflow-x-auto">
        <div className="flex min-w-max gap-2">
          {STAGE_ORDER.map((stage, index) => {
            const current = STAGE_ORDER.indexOf(deal.stage)
            const done = index <= current && deal.stage !== "Closed Lost"
            return (
              <button
                key={stage}
                type="button"
                onClick={() => move(stage)}
                className={`rounded-full border px-3 py-1.5 text-xs transition ${
                  deal.stage === stage
                    ? "border-primary bg-primary text-primary-foreground"
                    : done
                      ? "border-primary/30 bg-primary/10"
                      : "border-border bg-card"
                }`}
              >
                {stage}
              </button>
            )
          })}
        </div>
        <p className="text-muted-foreground mt-2 text-xs">
          Click a stage to attempt a Blueprint transition. Invalid moves are blocked with the same
          rules that run in Zoho.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="border-b">
            <CardTitle>Deal fields</CardTitle>
          </CardHeader>
          <CardContent>
            <FieldList
              fields={[
                {
                  label: "Account",
                  value: account ? (
                    <Link href={`/accounts/${account.id}`} className="hover:underline">
                      {account.name}
                    </Link>
                  ) : (
                    "—"
                  ),
                },
                {
                  label: "Contact",
                  value: contact ? (
                    <Link href={`/contacts/${contact.id}`} className="hover:underline">
                      {contact.firstName} {contact.lastName}
                    </Link>
                  ) : (
                    "—"
                  ),
                },
                { label: "Amount", value: money(deal.amount) },
                { label: "Probability", value: percent(deal.probability) },
                { label: "Closing date", value: formatDate(deal.closingDate) },
                { label: "Product", value: deal.product },
                { label: "Lead source", value: deal.leadSource },
                { label: "Owner", value: <OwnerChip user={crm.userById(deal.ownerId)} /> },
              ]}
            />
            <div className="mt-6 grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="po">PO Number (custom field)</Label>
                <Input id="po" value={po} onChange={(e) => setPo(e.target.value)} placeholder="RG-88421" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="lost">Lost reason</Label>
                <Input
                  id="lost"
                  value={lostReason}
                  onChange={(e) => setLostReason(e.target.value)}
                  placeholder="Required to close-lost"
                />
              </div>
            </div>
            <Button className="mt-3" size="sm" onClick={saveExtras}>
              Save fields
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="border-b">
            <CardTitle>Blueprint</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {BLUEPRINT.map((item) => (
              <div key={item.stage}>
                <p className="text-sm font-medium">{item.stage}</p>
                <p className="text-muted-foreground text-xs">{item.rule}</p>
              </div>
            ))}
            <div className="space-y-1.5 pt-2">
              <Label>Jump to stage</Label>
              <Select onValueChange={(value) => move(value as DealStage)}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Choose stage" />
                </SelectTrigger>
                <SelectContent>
                  {STAGE_ORDER.map((stage) => (
                    <SelectItem key={stage} value={stage}>
                      {stage}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="border-b">
            <CardTitle>Activities</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {activities.length === 0 ? (
              <p className="text-muted-foreground text-sm">None logged.</p>
            ) : (
              activities.map((activity) => (
                <div key={activity.id} className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium">{activity.subject}</p>
                    <p className="text-muted-foreground text-xs">{activity.type}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusBadge value={activity.status} />
                    {activity.status !== "Completed" ? (
                      <Button
                        size="xs"
                        variant="outline"
                        onClick={() => {
                          crm.dispatch({ type: "complete-activity", activityId: activity.id })
                          toast.success("Activity completed — Blueprint can now see the discovery call.")
                        }}
                      >
                        Complete
                      </Button>
                    ) : null}
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="border-b">
            <CardTitle>Notes</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {notes.length === 0 ? (
              <p className="text-muted-foreground text-sm">No notes.</p>
            ) : (
              notes.map((note) => (
                <p key={note.id} className="rounded-xl bg-muted/60 p-3 text-sm">
                  {note.body}
                </p>
              ))
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
