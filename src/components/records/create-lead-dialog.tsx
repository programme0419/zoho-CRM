"use client"

import { useMemo, useState } from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { ScoreBreakdown } from "@/components/records/score-breakdown"
import { useCrm } from "@/lib/crm-store"
import { EMPTY_TOUCHPOINTS, scoreLead } from "@/lib/scoring"
import type { Lead, LeadSource } from "@/lib/types"

const INDUSTRIES = [
  "Utilities",
  "Manufacturing",
  "Mining",
  "Healthcare",
  "Logistics",
  "Materials",
  "Unknown",
]

export function CreateLeadDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { addLead, activities, notes, disabledScoringRuleIds } = useCrm()
  const [firstName, setFirstName] = useState("")
  const [lastName, setLastName] = useState("")
  const [company, setCompany] = useState("")
  const [email, setEmail] = useState("")
  const [title, setTitle] = useState("")
  const [industry, setIndustry] = useState("Utilities")
  const [revenue, setRevenue] = useState("220000000")
  const [source, setSource] = useState<LeadSource>("Website")

  const preview = useMemo(() => {
    const draft: Lead = {
      id: "draft",
      firstName,
      lastName,
      company,
      title: title || "New inquiry",
      email,
      phone: "",
      status: "Not Contacted",
      source,
      industry,
      annualRevenue: Number(revenue) || 0,
      rating: "Cold",
      ownerId: "usr_elena",
      score: 0,
      city: "",
      country: "",
      createdTime: new Date().toISOString(),
      converted: false,
      touchpoints: {
        ...EMPTY_TOUCHPOINTS,
        websiteSessions: source === "Website" ? 1 : 0,
      },
    }
    return scoreLead({ lead: draft, activities, notes, now: new Date() }, disabledScoringRuleIds)
  }, [
    firstName,
    lastName,
    company,
    title,
    email,
    industry,
    revenue,
    source,
    activities,
    notes,
    disabledScoringRuleIds,
  ])

  function reset() {
    setFirstName("")
    setLastName("")
    setCompany("")
    setEmail("")
    setTitle("")
    setIndustry("Utilities")
    setRevenue("220000000")
    setSource("Website")
  }

  function submit() {
    if (!lastName.trim() || !company.trim()) {
      toast.error("Last name and company are required — same as Zoho CRM.")
      return
    }
    const scored = addLead({
      firstName,
      lastName,
      company,
      email,
      source,
      title,
      industry,
      annualRevenue: Number(revenue) || 0,
    })
    toast.success(`Lead created. Scoring engine set Lead_Score to ${scored.total} (${scored.rating}).`)
    reset()
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>New lead</DialogTitle>
          <DialogDescription>
            Scoring runs on create — same as a Zoho workflow with trigger workflow.
          </DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="first">First name</Label>
            <Input id="first" value={firstName} onChange={(e) => setFirstName(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="last">Last name</Label>
            <Input id="last" value={lastName} onChange={(e) => setLastName(e.target.value)} />
          </div>
          <div className="col-span-2 space-y-1.5">
            <Label htmlFor="company">Company</Label>
            <Input id="company" value={company} onChange={(e) => setCompany(e.target.value)} />
          </div>
          <div className="col-span-2 space-y-1.5">
            <Label htmlFor="title">Title</Label>
            <Input
              id="title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="VP Energy, Plant Director…"
            />
          </div>
          <div className="col-span-2 space-y-1.5">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label>Industry</Label>
            <Select value={industry} onValueChange={setIndustry}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {INDUSTRIES.map((item) => (
                  <SelectItem key={item} value={item}>
                    {item}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="rev">Annual revenue (USD)</Label>
            <Input
              id="rev"
              inputMode="numeric"
              value={revenue}
              onChange={(e) => setRevenue(e.target.value)}
            />
          </div>
          <div className="col-span-2 space-y-1.5">
            <Label>Lead source</Label>
            <Select value={source} onValueChange={(value) => setSource(value as LeadSource)}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {["Website", "Trade Show", "Referral", "Outbound", "Partner", "Inbound Call"].map(
                  (item) => (
                    <SelectItem key={item} value={item}>
                      {item}
                    </SelectItem>
                  )
                )}
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="rounded-xl border border-border bg-muted/40 p-3">
          <ScoreBreakdown result={preview} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={submit}>Create lead</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
