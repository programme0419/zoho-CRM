"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { FieldList } from "@/components/records/field-list"
import { OwnerChip } from "@/components/records/owner-chip"
import { PageHeader } from "@/components/records/page-header"
import { useCrm } from "@/lib/crm-store"

export function ContactDetail({ contactId }: { contactId: string }) {
  const crm = useCrm()
  const router = useRouter()
  const contact = crm.contacts.find((item) => item.id === contactId)

  if (!contact) {
    return (
      <div className="py-20 text-center">
        <p className="font-heading text-2xl">Contact not found</p>
        <Button className="mt-4" variant="outline" onClick={() => router.push("/contacts")}>
          Back to contacts
        </Button>
      </div>
    )
  }

  const account = crm.accountById(contact.accountId)
  const deals = crm.deals.filter((deal) => deal.contactId === contact.id)

  return (
    <div>
      <PageHeader
        eyebrow="Contacts · Zoho CRM"
        title={`${contact.firstName} ${contact.lastName}`}
        description={`${contact.title} · ${contact.department || "—"}`}
      />
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="border-b">
            <CardTitle>Contact fields</CardTitle>
          </CardHeader>
          <CardContent>
            <FieldList
              fields={[
                { label: "Email", value: contact.email },
                { label: "Phone", value: contact.phone },
                {
                  label: "Account",
                  value: account ? (
                    <Link href={`/accounts/${account.id}`} className="hover:underline">
                      {account.name}
                    </Link>
                  ) : (
                    "—"
                  ),
                },
                { label: "Title", value: contact.title },
                {
                  label: "Mailing address",
                  value: `${contact.mailingCity}, ${contact.mailingCountry}`,
                },
                { label: "Owner", value: <OwnerChip user={crm.userById(contact.ownerId)} /> },
              ]}
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="border-b">
            <CardTitle>Deals as contact</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {deals.length === 0 ? (
              <p className="text-muted-foreground text-sm">No deals linked.</p>
            ) : (
              deals.map((deal) => (
                <Link key={deal.id} href={`/deals/${deal.id}`} className="block text-sm hover:underline">
                  {deal.name}
                </Link>
              ))
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
