import type { Metadata } from "next"
import type { ReactNode } from "react"
import { Geist, Geist_Mono, Instrument_Serif } from "next/font/google"
import { AppShell } from "@/components/layout/app-shell"
import { Providers } from "@/components/providers"
import "./globals.css"

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
})

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
})

const instrument = Instrument_Serif({
  variable: "--font-instrument",
  subsets: ["latin"],
  weight: "400",
})

export const metadata: Metadata = {
  title: "Meridian — Zoho CRM for Helios Industrial",
  description:
    "Client-ready Zoho CRM workspace: pipeline, lead conversion, blueprints, and API v8 integration.",
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} ${instrument.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  )
}
