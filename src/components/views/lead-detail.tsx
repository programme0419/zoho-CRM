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
                { label: "Lead score", value: String(lead.score) },
                { label: "Annual revenue", value: lead.annualRevenue ? money(lead.annualRevenue) : "—" },
                { label: "Owner", value: <OwnerChip user={crm.userById(lead.ownerId)} /> },
              ]}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="border-b">
            <CardTitle>Conversion</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {lead.converted ? (
              <p>
                Already converted. Account, contact, and deal were written in one Zoho convert
                transaction.
              </p>
            ) : (
              <p>
                Convert writes Account, Contact, and Deal via POST /crm/v8/Leads/{"{id}"}/actions/convert
                and fires the “Lead conversion writes Account 360” workflow.
              </p>
            )}
            <p className="text-muted-foreground">Scoring rule applied on create. Current score {lead.score}.</p>
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
                    <StatusBadge value={activity.status} />
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
