"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { FieldList } from "@/components/records/field-list"
import { OwnerChip } from "@/components/records/owner-chip"
import { PageHeader } from "@/components/records/page-header"
import { StatusBadge } from "@/components/records/status-badge"
import { useCrm } from "@/lib/crm-store"
import { money, moneyCompact } from "@/lib/format"
import { OPEN_STAGES } from "@/lib/types"

export function AccountDetail({ accountId }: { accountId: string }) {
  const crm = useCrm()
  const router = useRouter()
  const account = crm.accounts.find((item) => item.id === accountId)

  if (!account) {
    return (
      <div className="py-20 text-center">
        <p className="font-heading text-2xl">Account not found</p>
        <Button className="mt-4" variant="outline" onClick={() => router.push("/accounts")}>
          Back to accounts
        </Button>
      </div>
    )
  }

  const contacts = crm.contacts.filter((contact) => contact.accountId === account.id)
  const relatedDeals = crm.deals.filter((deal) => deal.accountId === account.id)
  const open = relatedDeals.filter((deal) => OPEN_STAGES.includes(deal.stage))

  return (
    <div>
      <PageHeader
        eyebrow="Accounts · Zoho CRM"
        title={account.name}
        description={account.description}
        actions={<StatusBadge value={account.type} />}
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="border-b">
            <CardTitle>Account 360</CardTitle>
          </CardHeader>
          <CardContent>
            <FieldList
              fields={[
                { label: "Industry", value: account.industry },
                { label: "Website", value: account.website },
                { label: "Phone", value: account.phone },
                {
                  label: "Billing address",
                  value: `${account.billingCity}, ${account.billingCountry}`,
                },
                { label: "Annual revenue", value: money(account.annualRevenue) },
                { label: "Employees", value: account.employees.toLocaleString("en-US") },
                { label: "Rating", value: <StatusBadge value={account.rating} /> },
                { label: "Owner", value: <OwnerChip user={crm.userById(account.ownerId)} /> },
              ]}
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="border-b">
            <CardTitle>Open pipeline</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="font-heading text-3xl">
              {moneyCompact(open.reduce((sum, deal) => sum + deal.amount, 0))}
            </p>
            <p className="text-muted-foreground mt-1 text-sm">{open.length} open deals</p>
          </CardContent>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="border-b">
            <CardTitle>Contacts</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {contacts.map((contact) => (
              <Link key={contact.id} href={`/contacts/${contact.id}`} className="block text-sm hover:underline">
                <span className="font-medium">
                  {contact.firstName} {contact.lastName}
                </span>
                <span className="text-muted-foreground"> · {contact.title}</span>
              </Link>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="border-b">
            <CardTitle>Deals</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {relatedDeals.map((deal) => (
              <Link key={deal.id} href={`/deals/${deal.id}`} className="flex items-center justify-between gap-3">
                <span className="text-sm font-medium hover:underline">{deal.name}</span>
                <StatusBadge value={deal.stage} />
              </Link>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
