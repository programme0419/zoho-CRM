"use client"

import { useState } from "react"
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
import { useCrm } from "@/lib/crm-store"
import type { LeadSource } from "@/lib/types"

export function CreateLeadDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { addLead } = useCrm()
  const [firstName, setFirstName] = useState("")
  const [lastName, setLastName] = useState("")
  const [company, setCompany] = useState("")
  const [email, setEmail] = useState("")
  const [source, setSource] = useState<LeadSource>("Website")

  function reset() {
    setFirstName("")
    setLastName("")
    setCompany("")
    setEmail("")
    setSource("Website")
  }

  function submit() {
    if (!lastName.trim() || !company.trim()) {
      toast.error("Last name and company are required — same as Zoho CRM.")
      return
    }
    addLead({ firstName, lastName, company, email, source })
    toast.success("Lead created. Workflow “Hot inbound utilities” will evaluate on sync.")
    reset()
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>New lead</DialogTitle>
          <DialogDescription>
            Maps to POST /crm/v8/Leads with trigger workflow and blueprint.
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
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
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
