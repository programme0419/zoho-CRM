"use client"

import { toast } from "sonner"
import { Button } from "@/components/ui/button"
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
import { relativeDay } from "@/lib/format"

export function ActivitiesView() {
  const crm = useCrm()

  return (
    <div>
      <PageHeader
        eyebrow="Tasks, calls, meetings"
        title="What the team owes the week."
        description="Zoho Activities related-listed against leads, accounts, and deals. Completing a discovery call unlocks the Needs Analysis blueprint gate."
      />
      <div className="overflow-hidden rounded-2xl border border-border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Subject</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Related to</TableHead>
              <TableHead>Due</TableHead>
              <TableHead>Owner</TableHead>
              <TableHead>Status</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {crm.activities.map((activity) => (
              <TableRow key={activity.id}>
                <TableCell>
                  <p className="font-medium">{activity.subject}</p>
                  <p className="text-muted-foreground max-w-sm truncate text-xs">{activity.notes}</p>
                </TableCell>
                <TableCell>{activity.type}</TableCell>
                <TableCell>
                  {activity.relatedModule} · {activity.relatedName}
                </TableCell>
                <TableCell>{relativeDay(activity.dueDate)}</TableCell>
                <TableCell>
                  <OwnerChip user={crm.userById(activity.ownerId)} />
                </TableCell>
                <TableCell>
                  <StatusBadge value={activity.status} />
                </TableCell>
                <TableCell>
                  {activity.status !== "Completed" ? (
                    <Button
                      size="xs"
                      variant="outline"
                      onClick={() => {
                        crm.dispatch({ type: "complete-activity", activityId: activity.id })
                        toast.success("Marked complete.")
                      }}
                    >
                      Complete
                    </Button>
                  ) : null}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
