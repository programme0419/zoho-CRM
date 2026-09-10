const moneyFmt = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
})

const compactFmt = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  notation: "compact",
  maximumFractionDigits: 1,
})

const dateFmt = new Intl.DateTimeFormat("en-GB", {
  day: "2-digit",
  month: "short",
  year: "numeric",
})

const dateTimeFmt = new Intl.DateTimeFormat("en-GB", {
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
})

export function money(value: number) {
  return moneyFmt.format(value)
}

export function moneyCompact(value: number) {
  return compactFmt.format(value)
}

export function formatDate(iso: string) {
  return dateFmt.format(new Date(iso))
}

export function formatDateTime(iso: string) {
  return dateTimeFmt.format(new Date(iso))
}

export function initials(name: string) {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("")
}

export function percent(value: number) {
  return `${Math.round(value)}%`
}

export function daysUntil(iso: string) {
  const delta = new Date(iso).getTime() - Date.now()
  return Math.ceil(delta / (1000 * 60 * 60 * 24))
}

export function relativeDay(iso: string) {
  const days = daysUntil(iso)
  if (days === 0) return "Today"
  if (days === 1) return "Tomorrow"
  if (days === -1) return "Yesterday"
  if (days > 1 && days < 14) return `In ${days} days`
  if (days < 0 && days > -14) return `${Math.abs(days)} days ago`
  return formatDate(iso)
}

export function nowIso() {
  return new Date().toISOString()
}

export function id(prefix: string) {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`
}
