"use client"

import { useMemo, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { CreateLeadDialog } from "@/components/records/create-lead-dialog"
import { EmptyState } from "@/components/records/empty-state"
import { OwnerChip } from "@/components/records/owner-chip"
import { PageHeader } from "@/components/records/page-header"
import { StatusBadge } from "@/components/records/status-badge"
import { useCrm } from "@/lib/crm-store"
import { formatDate, moneyCompact } from "@/lib/format"

export function LeadsView() {
  const { leads, userById } = useCrm()
  const router = useRouter()
  const [query, setQuery] = useState("")
  const [open, setOpen] = useState(false)

  const rows = useMemo(() => {
    const q = query.toLowerCase()
    return leads.filter((lead) =>
      `${lead.firstName} ${lead.lastName} ${lead.company} ${lead.email} ${lead.status}`
        .toLowerCase()
        .includes(q)
    )
  }, [leads, query])

  return (
    <div>
      <PageHeader
        eyebrow="Leads module"
        title="Inbound before it becomes pipeline."
        description="Zoho Leads with scoring, sources, and one-click conversion to Account + Contact + Deal."
        actions={
          <Button onClick={() => setOpen(true)}>
            <Plus data-icon="inline-start" />
            New lead
          </Button>
        }
      />

      <div className="mb-4">
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter by name, company, status…"
          className="max-w-md bg-card"
        />
      </div>

      {rows.length === 0 ? (
        <EmptyState
          title="No leads match"
          description="Clear the filter or capture a new inbound lead from the web form."
          action={<Button onClick={() => setOpen(true)}>Capture lead</Button>}
        />
      ) : (
        <div className="overflow-hidden rounded-2xl border border-border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Lead</TableHead>
                <TableHead>Company</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Score</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Revenue</TableHead>
                <TableHead>Owner</TableHead>
                <TableHead>Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((lead) => (
                <TableRow
                  key={lead.id}
                  className="cursor-pointer"
                  onClick={() => router.push(`/leads/${lead.id}`)}
                >
                  <TableCell>
                    <Link href={`/leads/${lead.id}`} className="font-medium hover:underline">
                      {lead.firstName} {lead.lastName}
                    </Link>
                    <p className="text-muted-foreground text-xs">{lead.email}</p>
                  </TableCell>
                  <TableCell>
                    {lead.company}
                    {lead.converted ? (
                      <span className="text-muted-foreground ml-2 text-xs">Converted</span>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    <StatusBadge value={lead.status} />
                  </TableCell>
                  <TableCell className="font-medium">{lead.score}</TableCell>
                  <TableCell>{lead.source}</TableCell>
                  <TableCell>{lead.annualRevenue ? moneyCompact(lead.annualRevenue) : "—"}</TableCell>
                  <TableCell>
                    <OwnerChip user={userById(lead.ownerId)} />
                  </TableCell>
                  <TableCell className="text-muted-foreground">{formatDate(lead.createdTime)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <CreateLeadDialog open={open} onOpenChange={setOpen} />
    </div>
  )
}
