"use client"

import { useState } from "react"
import { Menu, Plus, Search } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet"
import { useCrm } from "@/lib/crm-store"
import { initials } from "@/lib/format"
import { ORG } from "@/lib/seed"
import { Sidebar } from "./sidebar"
import { CommandPalette } from "./command-palette"
import { CreateLeadDialog } from "@/components/records/create-lead-dialog"

export function Topbar() {
  const { currentUser } = useCrm()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [commandOpen, setCommandOpen] = useState(false)
  const [leadOpen, setLeadOpen] = useState(false)

  return (
    <>
      <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border/70 bg-background/80 px-4 backdrop-blur-md md:px-6">
        <Button
          variant="ghost"
          size="icon-sm"
          className="lg:hidden"
          onClick={() => setMobileOpen(true)}
          aria-label="Open navigation"
        >
          <Menu />
        </Button>

        <div className="hidden min-w-0 flex-1 items-center gap-3 md:flex">
          <p className="truncate text-sm text-muted-foreground">
            <span className="text-foreground font-medium">{ORG.name}</span>
            <span className="mx-2 text-border">/</span>
            {ORG.quarter} revenue workspace
          </p>
        </div>

        <button
          type="button"
          onClick={() => setCommandOpen(true)}
          className="text-muted-foreground hover:bg-muted/80 ml-auto flex h-8 max-w-xs flex-1 items-center gap-2 rounded-lg border border-border bg-card px-3 text-left text-sm md:ml-0 md:max-w-sm"
        >
          <Search className="size-3.5" />
          <span className="flex-1">Search records…</span>
          <kbd className="hidden rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px] md:inline">
            ⌘K
          </kbd>
        </button>

        <Button size="sm" onClick={() => setLeadOpen(true)}>
          <Plus data-icon="inline-start" />
          New lead
        </Button>

        <div className="flex items-center gap-2 pl-1">
          <span
            className="flex size-8 items-center justify-center rounded-full text-xs font-semibold text-white"
            style={{ background: `oklch(0.42 0.08 ${28})` }}
          >
            {initials(currentUser.name)}
          </span>
          <div className="hidden leading-tight sm:block">
            <p className="text-sm font-medium">{currentUser.name}</p>
            <p className="text-muted-foreground text-[11px]">{currentUser.role}</p>
          </div>
        </div>
      </header>

      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="w-72 p-0">
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <Sidebar onNavigate={() => setMobileOpen(false)} />
        </SheetContent>
      </Sheet>

      <CommandPalette open={commandOpen} onOpenChange={setCommandOpen} />
      <CreateLeadDialog open={leadOpen} onOpenChange={setLeadOpen} />
    </>
  )
}
