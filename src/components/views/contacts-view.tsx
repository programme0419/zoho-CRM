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
import { useCrm } from "@/lib/crm-store"

export function ContactsView() {
  const { contacts, accounts, userById, accountById } = useCrm()
  const router = useRouter()
  const [query, setQuery] = useState("")
  const rows = useMemo(() => {
    const q = query.toLowerCase()
    return contacts.filter((contact) =>
      `${contact.firstName} ${contact.lastName} ${contact.email} ${contact.title}`
        .toLowerCase()
        .includes(q)
    )
  }, [contacts, query])

  return (
    <div>
      <PageHeader
        eyebrow="Contacts module"
        title="People behind the account."
        description={`${contacts.length} contacts across ${accounts.length} accounts — lookup-linked the Zoho way.`}
      />
      <Input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Filter contacts…"
        className="mb-4 max-w-md bg-card"
      />
      {rows.length === 0 ? (
        <EmptyState title="No contacts" description="Try another search." />
      ) : (
        <div className="overflow-hidden rounded-2xl border border-border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Contact</TableHead>
                <TableHead>Title</TableHead>
                <TableHead>Account</TableHead>
                <TableHead>Location</TableHead>
                <TableHead>Owner</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((contact) => (
                <TableRow
                  key={contact.id}
                  className="cursor-pointer"
                  onClick={() => router.push(`/contacts/${contact.id}`)}
                >
                  <TableCell>
                    <Link href={`/contacts/${contact.id}`} className="font-medium hover:underline">
                      {contact.firstName} {contact.lastName}
                    </Link>
                    <p className="text-muted-foreground text-xs">{contact.email}</p>
                  </TableCell>
                  <TableCell>{contact.title}</TableCell>
                  <TableCell>{accountById(contact.accountId)?.name}</TableCell>
                  <TableCell>
                    {contact.mailingCity}, {contact.mailingCountry}
                  </TableCell>
                  <TableCell>
                    <OwnerChip user={userById(contact.ownerId)} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
