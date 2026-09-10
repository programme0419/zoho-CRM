"use client"

import { useMemo, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { EmptyState } from "@/components/records/empty-state"
import { OwnerChip } from "@/components/records/owner-chip"
import { PageHeader } from "@/components/records/page-header"
import { StatusBadge } from "@/components/records/status-badge"
import { useCrm } from "@/lib/crm-store"
import { moneyCompact } from "@/lib/format"

export function AccountsView() {
  const { accounts, userById, deals } = useCrm()
  const router = useRouter()
  const [query, setQuery] = useState("")
  const rows = useMemo(() => {
    const q = query.toLowerCase()
    return accounts.filter((account) =>
      `${account.name} ${account.industry} ${account.billingCity}`.toLowerCase().includes(q)
    )
  }, [accounts, query])

  return (
    <div>
      <PageHeader
        eyebrow="Accounts module"
        title="The companies that pay."
        description="Zoho Accounts with 360° related lists — contacts, open pipeline, and installed-base type."
      />
      <Input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Filter accounts…"
        className="mb-4 max-w-md bg-card"
      />
      {rows.length === 0 ? (
        <EmptyState title="No accounts" description="Try another search." />
      ) : (
        <div className="overflow-hidden rounded-2xl border border-border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Account</TableHead>
                <TableHead>Industry</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Location</TableHead>
                <TableHead>Open pipeline</TableHead>
                <TableHead>Owner</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((account) => {
                const pipeline = deals
                  .filter((deal) => deal.accountId === account.id && deal.stage !== "Closed Won" && deal.stage !== "Closed Lost")
                  .reduce((sum, deal) => sum + deal.amount, 0)
                return (
                  <TableRow
                    key={account.id}
                    className="cursor-pointer"
                    onClick={() => router.push(`/accounts/${account.id}`)}
                  >
                    <TableCell>
                      <Link href={`/accounts/${account.id}`} className="font-medium hover:underline">
                        {account.name}
                      </Link>
                      <p className="text-muted-foreground text-xs">{account.website}</p>
                    </TableCell>
                    <TableCell>{account.industry}</TableCell>
                    <TableCell>
                      <StatusBadge value={account.type} />
                    </TableCell>
                    <TableCell>
                      {account.billingCity}, {account.billingCountry}
                    </TableCell>
                    <TableCell>{pipeline ? moneyCompact(pipeline) : "—"}</TableCell>
                    <TableCell>
                      <OwnerChip user={userById(account.ownerId)} />
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
