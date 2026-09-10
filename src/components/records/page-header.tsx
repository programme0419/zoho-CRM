import type { ReactNode } from "react"

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string
  title: string
  description?: string
  actions?: ReactNode
}) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:mb-8 sm:flex-row sm:items-end sm:justify-between">
      <div>
        {eyebrow ? (
          <p className="text-muted-foreground mb-1 text-[11px] tracking-[0.18em] uppercase">
            {eyebrow}
          </p>
        ) : null}
        <h1 className="font-heading text-3xl tracking-tight text-balance md:text-4xl">{title}</h1>
        {description ? (
          <p className="text-muted-foreground mt-2 max-w-2xl text-sm leading-relaxed md:text-[15px]">
            {description}
          </p>
        ) : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  )
}
