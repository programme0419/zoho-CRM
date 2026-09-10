import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { ActivityStatus, DealStage, LeadStatus } from "@/lib/types"

const tone: Record<string, string> = {
  Hot: "border-transparent bg-[oklch(0.93_0.05_28)] text-[oklch(0.42_0.14_28)]",
  Warm: "border-transparent bg-[oklch(0.94_0.05_75)] text-[oklch(0.45_0.1_55)]",
  Cold: "border-transparent bg-muted text-muted-foreground",
  Qualified: "border-transparent bg-[oklch(0.93_0.04_162)] text-[oklch(0.35_0.08_162)]",
  "Not Contacted": "border-border bg-card text-muted-foreground",
  Contacted: "border-transparent bg-[oklch(0.93_0.03_240)] text-[oklch(0.38_0.08_240)]",
  Unqualified: "border-transparent bg-muted text-muted-foreground",
  "Lost Lead": "border-transparent bg-[oklch(0.93_0.03_28)] text-[oklch(0.45_0.12_28)]",
  "Closed Won": "border-transparent bg-[oklch(0.93_0.05_155)] text-[oklch(0.32_0.08_155)]",
  "Closed Lost": "border-transparent bg-[oklch(0.93_0.03_28)] text-[oklch(0.45_0.12_28)]",
  "Negotiation/Review": "border-transparent bg-[oklch(0.93_0.05_72)] text-[oklch(0.42_0.1_55)]",
  "Proposal/Price Quote": "border-transparent bg-[oklch(0.93_0.03_240)] text-[oklch(0.38_0.08_240)]",
  "Value Proposition": "border-transparent bg-[oklch(0.94_0.03_200)] text-[oklch(0.38_0.06_200)]",
  "Needs Analysis": "border-transparent bg-secondary text-secondary-foreground",
  Qualification: "border-border bg-card text-muted-foreground",
  Completed: "border-transparent bg-[oklch(0.93_0.05_155)] text-[oklch(0.32_0.08_155)]",
  "In Progress": "border-transparent bg-[oklch(0.93_0.05_72)] text-[oklch(0.42_0.1_55)]",
  "Not Started": "border-border bg-card text-muted-foreground",
  Deferred: "border-transparent bg-muted text-muted-foreground",
  Customer: "border-transparent bg-[oklch(0.93_0.05_155)] text-[oklch(0.32_0.08_155)]",
  Prospect: "border-transparent bg-[oklch(0.93_0.03_240)] text-[oklch(0.38_0.08_240)]",
  Partner: "border-transparent bg-[oklch(0.94_0.04_80)] text-[oklch(0.42_0.08_60)]",
  Active: "border-transparent bg-[oklch(0.93_0.05_155)] text-[oklch(0.32_0.08_155)]",
  Inactive: "border-transparent bg-muted text-muted-foreground",
  Synced: "border-transparent bg-[oklch(0.93_0.05_155)] text-[oklch(0.32_0.08_155)]",
  Retrying: "border-transparent bg-[oklch(0.93_0.05_72)] text-[oklch(0.42_0.1_55)]",
  Failed: "border-transparent bg-[oklch(0.93_0.04_28)] text-[oklch(0.45_0.14_28)]",
  Enterprise: "border-transparent bg-[oklch(0.93_0.03_52)] text-[oklch(0.38_0.06_52)]",
  "Mid-Market": "border-transparent bg-secondary text-secondary-foreground",
}

export function StatusBadge({
  value,
  className,
}: {
  value: LeadStatus | DealStage | ActivityStatus | string
  className?: string
}) {
  return (
    <Badge variant="outline" className={cn(tone[value] ?? "", className)}>
      {value}
    </Badge>
  )
}
