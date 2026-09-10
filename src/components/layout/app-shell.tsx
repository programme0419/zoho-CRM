"use client"

import { Sidebar } from "./sidebar"
import { Topbar } from "./topbar"
import type { ReactNode } from "react"

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="grain min-h-screen bg-background">
      <div className="flex min-h-screen">
        <aside className="sticky top-0 hidden h-screen w-60 shrink-0 lg:block">
          <Sidebar />
        </aside>
        <div className="flex min-w-0 flex-1 flex-col">
          <Topbar />
          <main className="flex-1 px-4 py-6 md:px-8 md:py-8">{children}</main>
        </div>
      </div>
    </div>
  )
}
