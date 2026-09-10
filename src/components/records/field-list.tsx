import type { ReactNode } from "react"

export function FieldList({
  fields,
}: {
  fields: { label: string; value: ReactNode }[]
}) {
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2">
      {fields.map((field) => (
        <div key={field.label} className="min-w-0">
          <dt className="text-muted-foreground text-[11px] tracking-wide uppercase">{field.label}</dt>
          <dd className="mt-1 text-sm font-medium text-pretty">{field.value || "—"}</dd>
        </div>
      ))}
    </dl>
  )
}
