"use client"

import { useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { FieldList } from "@/components/records/field-list"
import { OwnerChip } from "@/components/records/owner-chip"
import { PageHeader } from "@/components/records/page-header"
import { ScoreBreakdown } from "@/components/records/score-breakdown"
import { StatusBadge } from "@/components/records/status-badge"
import { useCrm } from "@/lib/crm-store"
import { formatDateTime, id, money, nowIso } from "@/lib/format"

export function LeadDetail({ leadId }: { leadId: string }) {
  const crm = useCrm()
  const router = useRouter()
  const lead = crm.leads.find((item) => item.id === leadId)
  const [convertOpen, setConvertOpen] = useState(false)
  const [dealName, setDealName] = useState("")
  const [note, setNote] = useState("")

  if (!lead) {
    return (
      <div className="py-20 text-center">
        <p className="font-heading text-2xl">Lead not found</p>
        <Button className="mt-4" variant="outline" onClick={() => router.push("/leads")}>
          Back to leads
        </Button>
      </div>
    )
  }

  const notes = crm.notes.filter((item) => item.recordId === lead.id)
  const activities = crm.activities.filter((item) => item.relatedId === lead.id)
  const breakdown = crm.scoreFor(lead.id)

  function convert() {
    const result = crm.convertLead(lead!.id, dealName)
    if (!result.ok) {
      toast.error(result.message)
      return
    }
    toast.success(result.message)
    setConvertOpen(false)
    router.push(result.dealId ? `/deals/${result.dealId}` : "/deals")
  }

  function addNote() {
    if (!note.trim() || !lead) return
    crm.dispatch({
      type: "add-note",
      note: {
        id: id("note"),
        module: "Leads",
        recordId: leadId,
        authorId: crm.currentUserId,
        body: note,
        createdTime: nowIso(),
      },
    })
    setNote("")
    toast.success("Note saved on the lead.")
  }

  return (
    <div>
      <PageHeader
        eyebrow="Leads · Zoho CRM"
        title={`${lead.firstName} ${lead.lastName}`}
        description={`${lead.title} at ${lead.company} · ${lead.city}${lead.city ? ", " : ""}${lead.country}`}
        actions={
          <>
            <StatusBadge value={lead.status} />
            <StatusBadge value={lead.rating} />
            {!lead.converted ? (
              <Button onClick={() => setConvertOpen(true)}>Convert lead</Button>
            ) : (
              <Button variant="outline" asChild>
                <Link href={`/deals/${lead.convertedDealId}`}>Open deal</Link>
              </Button>
            )}
          </>
        }
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="border-b">
            <CardTitle>Lead fields</CardTitle>
          </CardHeader>
          <CardContent>
            <FieldList
              fields={[
                { label: "Email", value: lead.email },
                { label: "Phone", value: lead.phone },
                { label: "Company", value: lead.company },
                { label: "Industry", value: lead.industry },
                { label: "Lead source", value: lead.source },
                { label: "Annual revenue", value: lead.annualRevenue ? money(lead.annualRevenue) : "—" },
                { label: "Owner", value: <OwnerChip user={crm.userById(lead.ownerId)} /> },
              ]}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="border-b">
            <CardTitle>Lead score</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {breakdown ? <ScoreBreakdown result={breakdown} /> : null}
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  crm.dispatch({
                    type: "patch-lead",
                    leadId,
                    patch: {
                      touchpoints: {
                        ...lead.touchpoints,
                        websiteSessions: lead.touchpoints.websiteSessions + 1,
                      },
                    },
                  })
                  toast.success("Website session logged. Scoring engine re-ran.")
                }}
              >
                + Website session
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={lead.touchpoints.usedChpCalculator}
                onClick={() => {
                  crm.dispatch({
                    type: "patch-lead",
                    leadId,
                    patch: {
                      touchpoints: { ...lead.touchpoints, usedChpCalculator: true },
                    },
                  })
                  toast.success("CHP calculator touchpoint set. +16 if the rule is active.")
                }}
              >
                Used CHP calculator
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  crm.dispatch({
                    type: "patch-lead",
                    leadId,
                    patch: {
                      touchpoints: {
                        ...lead.touchpoints,
                        emailClicks: lead.touchpoints.emailClicks + 1,
                        emailOpens: lead.touchpoints.emailOpens + 1,
                      },
                    },
                  })
                  toast.success("Campaign click logged.")
                }}
              >
                + Email click
              </Button>
            </div>
            <p className="text-muted-foreground text-xs">
              {lead.touchpoints.websiteSessions} sessions ·{" "}
              {lead.touchpoints.usedChpCalculator ? "calculator used" : "no calculator"} ·{" "}
              {lead.touchpoints.emailClicks} email clicks
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="border-b">
            <CardTitle>Notes</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Add a note…" />
            <Button size="sm" onClick={addNote}>
              Save note
            </Button>
            {notes.length === 0 ? (
              <p className="text-muted-foreground text-sm">No notes yet.</p>
            ) : (
              notes.map((item) => (
                <div key={item.id} className="rounded-xl bg-muted/60 p-3 text-sm">
                  <p>{item.body}</p>
                  <p className="text-muted-foreground mt-2 text-xs">
                    {crm.userById(item.authorId)?.name} · {formatDateTime(item.createdTime)}
                  </p>
                </div>
              ))
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="border-b">
            <CardTitle>Related activities</CardTitle>
          </CardHeader>
          <CardContent>
            {activities.length === 0 ? (
              <p className="text-muted-foreground text-sm">No related tasks, calls, or meetings.</p>
            ) : (
              <ul className="space-y-3">
                {activities.map((activity) => (
                  <li key={activity.id} className="flex items-center justify-between gap-3">
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
                            toast.success("Activity completed. Behavioral scoring re-ran.")
                          }}
                        >
                          Complete
                        </Button>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <Dialog open={convertOpen} onOpenChange={setConvertOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Convert {lead.firstName}</DialogTitle>
            <DialogDescription>
              Creates Account “{lead.company}”, a Contact, and a Deal in Qualification.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="deal">Deal name</Label>
            <Input
              id="deal"
              value={dealName}
              onChange={(e) => setDealName(e.target.value)}
              placeholder={`${lead.company} — discovery`}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConvertOpen(false)}>
              Cancel
            </Button>
            <Button onClick={convert}>Convert</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
