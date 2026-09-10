import type { ReactNode } from "react"

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border bg-card/60 px-6 py-16 text-center">
      <p className="font-heading text-xl">{title}</p>
      <p className="text-muted-foreground mt-2 max-w-md text-sm">{description}</p>
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  )
}
