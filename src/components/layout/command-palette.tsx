"use client"

import { useEffect, useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import { useCrm } from "@/lib/crm-store"

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const router = useRouter()
  const { leads, accounts, contacts, deals } = useCrm()
  const [query, setQuery] = useState("")

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault()
        onOpenChange(!open)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [open, onOpenChange])

  const q = query.trim().toLowerCase()
  const results = useMemo(() => {
    if (!q) {
      return {
        leads: leads.slice(0, 4),
        accounts: accounts.slice(0, 4),
        contacts: contacts.slice(0, 4),
        deals: deals.slice(0, 4),
      }
    }
    return {
      leads: leads
        .filter((lead) =>
          `${lead.firstName} ${lead.lastName} ${lead.company} ${lead.email}`
            .toLowerCase()
            .includes(q)
        )
        .slice(0, 6),
      accounts: accounts
        .filter((account) =>
          `${account.name} ${account.billingCity} ${account.industry}`.toLowerCase().includes(q)
        )
        .slice(0, 6),
      contacts: contacts
        .filter((contact) =>
          `${contact.firstName} ${contact.lastName} ${contact.email} ${contact.title}`
            .toLowerCase()
            .includes(q)
        )
        .slice(0, 6),
      deals: deals
        .filter((deal) => `${deal.name} ${deal.product}`.toLowerCase().includes(q))
        .slice(0, 6),
    }
  }, [q, leads, accounts, contacts, deals])

  function go(href: string) {
    router.push(href)
    onOpenChange(false)
  }

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <Command>
        <CommandInput
          placeholder="Search leads, accounts, contacts, deals…"
          value={query}
          onValueChange={setQuery}
        />
        <CommandList>
          <CommandEmpty>No matching Zoho records.</CommandEmpty>
          <CommandGroup heading="Workspace">
            <CommandItem value="scoring rules" onSelect={() => go("/scoring")}>
              Scoring rules
            </CommandItem>
            <CommandItem value="leads module" onSelect={() => go("/leads")}>
              Leads
            </CommandItem>
            <CommandItem value="pipeline deals" onSelect={() => go("/deals")}>
              Pipeline
            </CommandItem>
          </CommandGroup>
          <CommandGroup heading="Leads">
            {results.leads.map((lead) => (
              <CommandItem
                key={lead.id}
                value={`lead ${lead.firstName} ${lead.lastName} ${lead.company}`}
                onSelect={() => go(`/leads/${lead.id}`)}
              >
                {lead.firstName} {lead.lastName}
                <span className="text-muted-foreground ml-auto text-xs">{lead.company}</span>
              </CommandItem>
            ))}
          </CommandGroup>
          <CommandGroup heading="Accounts">
            {results.accounts.map((account) => (
              <CommandItem
                key={account.id}
                value={`account ${account.name}`}
                onSelect={() => go(`/accounts/${account.id}`)}
              >
                {account.name}
                <span className="text-muted-foreground ml-auto text-xs">{account.industry}</span>
              </CommandItem>
            ))}
          </CommandGroup>
          <CommandGroup heading="Contacts">
            {results.contacts.map((contact) => (
              <CommandItem
                key={contact.id}
                value={`contact ${contact.firstName} ${contact.lastName}`}
                onSelect={() => go(`/contacts/${contact.id}`)}
              >
                {contact.firstName} {contact.lastName}
                <span className="text-muted-foreground ml-auto text-xs">{contact.title}</span>
              </CommandItem>
            ))}
          </CommandGroup>
          <CommandGroup heading="Deals">
            {results.deals.map((deal) => (
              <CommandItem
                key={deal.id}
                value={`deal ${deal.name}`}
                onSelect={() => go(`/deals/${deal.id}`)}
              >
                {deal.name}
                <span className="text-muted-foreground ml-auto text-xs">{deal.stage}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
      </Command>
    </CommandDialog>
  )
}
