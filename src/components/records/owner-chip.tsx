import { initials } from "@/lib/format"
import type { User } from "@/lib/types"

export function OwnerChip({ user }: { user?: User }) {
  if (!user) return <span className="text-muted-foreground">Unassigned</span>
  return (
    <span className="inline-flex items-center gap-2">
      <span
        className="flex size-6 items-center justify-center rounded-full text-[10px] font-semibold text-white"
        style={{ background: `oklch(0.45 0.08 ${user.avatarHue})` }}
      >
        {initials(user.name)}
      </span>
      <span className="text-sm">{user.name}</span>
    </span>
  )
}
