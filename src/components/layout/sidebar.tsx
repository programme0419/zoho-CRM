"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  Activity,
  Building2,
  Contact,
  Gauge,
  GitBranch,
  Handshake,
  LayoutDashboard,
  Plug2,
  UserPlus,
  Workflow,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { ORG } from "@/lib/seed"

const nav = [
  { href: "/", label: "Command center", icon: LayoutDashboard },
  { href: "/leads", label: "Leads", icon: UserPlus },
  { href: "/scoring", label: "Scoring", icon: Gauge },
  { href: "/accounts", label: "Accounts", icon: Building2 },
  { href: "/contacts", label: "Contacts", icon: Contact },
  { href: "/deals", label: "Pipeline", icon: Handshake },
  { href: "/activities", label: "Activities", icon: Activity },
  { href: "/automations", label: "Blueprints", icon: Workflow },
  { href: "/integration", label: "Zoho API v8", icon: Plug2 },
]

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname()

  return (
    <div className="flex h-full flex-col bg-sidebar text-sidebar-foreground">
      <div className="px-5 pt-6 pb-5">
        <Link href="/" onClick={onNavigate} className="flex items-center gap-3">
          <span className="flex size-9 items-center justify-center rounded-xl bg-sidebar-primary text-sidebar-primary-foreground shadow-[0_8px_24px_rgba(0,0,0,0.25)]">
            <GitBranch className="size-4" />
          </span>
          <span>
            <span className="font-heading block text-lg leading-none tracking-tight">
              {ORG.workspace}
            </span>
            <span className="mt-1 block text-[11px] tracking-[0.16em] text-sidebar-foreground/55 uppercase">
              Zoho CRM
            </span>
          </span>
        </Link>
      </div>

      <nav className="flex flex-1 flex-col gap-0.5 px-3">
        {nav.map((item) => {
          const active =
            item.href === "/" ? pathname === "/" : pathname.startsWith(item.href)
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              className={cn(
                "flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] transition-colors",
                active
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-sidebar-foreground/70 hover:bg-sidebar-accent/70 hover:text-sidebar-accent-foreground"
              )}
            >
              <item.icon className="size-4 opacity-80" />
              {item.label}
            </Link>
          )
        })}
      </nav>

      <div className="m-3 rounded-xl border border-sidebar-border bg-sidebar-accent/50 p-3">
        <p className="text-[11px] tracking-wide text-sidebar-foreground/50 uppercase">
          Connected org
        </p>
        <p className="mt-1 text-sm font-medium">{ORG.name}</p>
        <p className="text-xs text-sidebar-foreground/55">
          {ORG.zohoOrg} · {ORG.region}
        </p>
      </div>
    </div>
  )
}
