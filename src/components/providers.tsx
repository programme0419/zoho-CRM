"use client"

import { ThemeProvider } from "next-themes"
import { TooltipProvider } from "@/components/ui/tooltip"
import { Toaster } from "@/components/ui/sonner"
import { CrmProvider } from "@/lib/crm-store"
import type { ReactNode } from "react"

export function Providers({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}>
      <CrmProvider>
        <TooltipProvider>
          {children}
          <Toaster />
        </TooltipProvider>
      </CrmProvider>
    </ThemeProvider>
  )
}
