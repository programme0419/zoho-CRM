"use client"

import {
  createContext,
  useContext,
  useMemo,
  useReducer,
  type Dispatch,
  type ReactNode,
} from "react"
import { canMoveDeal } from "./blueprint"
import { id, nowIso } from "./format"
import { seed } from "./seed"
import type {
  Account,
  Activity,
  Contact,
  CrmState,
  Deal,
  DealStage,
  Lead,
  LeadSource,
  Note,
} from "./types"
import { STAGE_PROBABILITY } from "./types"

type Action =
  | { type: "add-lead"; lead: Lead }
  | { type: "convert-lead"; leadId: string; account: Account; contact: Contact; deal: Deal }
  | { type: "move-deal"; dealId: string; stage: DealStage }
  | { type: "patch-deal"; dealId: string; patch: Partial<Deal> }
  | { type: "complete-activity"; activityId: string }
  | { type: "add-note"; note: Note }
  | { type: "add-activity"; activity: Activity }
  | { type: "add-sync"; module: string; action: CrmState["syncLog"][number]["action"]; endpoint: string }

function reducer(state: CrmState, action: Action): CrmState {
  switch (action.type) {
    case "add-lead":
      return { ...state, leads: [action.lead, ...state.leads] }
    case "convert-lead":
      return {
        ...state,
        leads: state.leads.map((lead) =>
          lead.id === action.leadId
            ? {
                ...lead,
                converted: true,
                status: "Qualified",
                convertedAccountId: action.account.id,
                convertedContactId: action.contact.id,
                convertedDealId: action.deal.id,
              }
            : lead
        ),
        accounts: [action.account, ...state.accounts],
        contacts: [action.contact, ...state.contacts],
        deals: [action.deal, ...state.deals],
      }
    case "move-deal":
      return {
        ...state,
        deals: state.deals.map((deal) =>
          deal.id === action.dealId
            ? { ...deal, stage: action.stage, probability: STAGE_PROBABILITY[action.stage] }
            : deal
        ),
      }
    case "patch-deal":
      return {
        ...state,
        deals: state.deals.map((deal) =>
          deal.id === action.dealId ? { ...deal, ...action.patch } : deal
        ),
      }
    case "complete-activity":
      return {
        ...state,
        activities: state.activities.map((activity) =>
          activity.id === action.activityId ? { ...activity, status: "Completed" } : activity
        ),
      }
    case "add-note":
      return { ...state, notes: [action.note, ...state.notes] }
    case "add-activity":
      return { ...state, activities: [action.activity, ...state.activities] }
    case "add-sync":
      return {
        ...state,
        syncLog: [
          {
            id: id("sync"),
            at: nowIso(),
            module: action.module,
            action: action.action,
            endpoint: action.endpoint,
            records: 1,
            status: "Synced",
            latencyMs: 80 + Math.round(Math.random() * 160),
          },
          ...state.syncLog,
        ],
      }
    default:
      return state
  }
}

type CrmContextValue = CrmState & {
  dispatch: Dispatch<Action>
  currentUser: CrmState["users"][number]
  userById: (id: string) => CrmState["users"][number] | undefined
  accountById: (id: string) => Account | undefined
  contactById: (id: string) => Contact | undefined
  convertLead: (leadId: string, dealName: string) => {
    ok: boolean
    message: string
    dealId?: string
  }
  moveDeal: (dealId: string, stage: DealStage) => { ok: boolean; message: string }
  addLead: (input: {
    firstName: string
    lastName: string
    company: string
    email: string
    source: LeadSource
  }) => void
}

const CrmContext = createContext<CrmContextValue | null>(null)

export function CrmProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, seed)

  const value = useMemo<CrmContextValue>(() => {
    const userById = (userId: string) => state.users.find((user) => user.id === userId)
    const accountById = (accountId: string) =>
      state.accounts.find((account) => account.id === accountId)
    const contactById = (contactId: string) =>
      state.contacts.find((contact) => contact.id === contactId)
    const currentUser = userById(state.currentUserId) ?? state.users[0]

    return {
      ...state,
      dispatch,
      currentUser,
      userById,
      accountById,
      contactById,
      addLead: (input) => {
        const lead: Lead = {
          id: id("led"),
          firstName: input.firstName,
          lastName: input.lastName,
          company: input.company,
          title: "New inquiry",
          email: input.email,
          phone: "",
          status: "Not Contacted",
          source: input.source,
          industry: "Unknown",
          annualRevenue: 0,
          rating: "Warm",
          ownerId: currentUser.id,
          score: 35,
          city: "",
          country: "",
          createdTime: nowIso(),
          converted: false,
        }
        dispatch({ type: "add-lead", lead })
        dispatch({
          type: "add-sync",
          module: "Leads",
          action: "POST",
          endpoint: "POST /crm/v8/Leads",
        })
      },
      convertLead: (leadId, dealName) => {
        const lead = state.leads.find((item) => item.id === leadId)
        if (!lead) return { ok: false, message: "Lead not found." }
        if (lead.converted) return { ok: false, message: "This lead is already converted." }

        const accountId = id("acc")
        const contactId = id("con")
        const dealId = id("dea")
        const account: Account = {
          id: accountId,
          name: lead.company,
          industry: lead.industry,
          type: "Prospect",
          website: "",
          phone: lead.phone,
          billingCity: lead.city,
          billingCountry: lead.country,
          annualRevenue: lead.annualRevenue,
          employees: 0,
          ownerId: lead.ownerId,
          rating: lead.rating,
          description: `Converted from lead ${lead.firstName} ${lead.lastName}.`,
          createdTime: nowIso(),
        }
        const contact: Contact = {
          id: contactId,
          firstName: lead.firstName,
          lastName: lead.lastName,
          title: lead.title,
          email: lead.email,
          phone: lead.phone,
          accountId,
          ownerId: lead.ownerId,
          department: "",
          mailingCity: lead.city,
          mailingCountry: lead.country,
          createdTime: nowIso(),
        }
        const deal: Deal = {
          id: dealId,
          name: dealName || `${lead.company} — discovery`,
          accountId,
          contactId,
          stage: "Qualification",
          amount: 0,
          probability: 10,
          closingDate: new Date(Date.now() + 1000 * 60 * 60 * 24 * 45).toISOString(),
          ownerId: lead.ownerId,
          pipeline: lead.annualRevenue > 250_000_000 ? "Enterprise" : "Mid-Market",
          nextStep: "Discovery call",
          product: "To be qualified",
          leadSource: lead.source,
          createdTime: nowIso(),
        }
        dispatch({ type: "convert-lead", leadId, account, contact, deal })
        dispatch({
          type: "add-sync",
          module: "Leads",
          action: "CONVERT",
          endpoint: `POST /crm/v8/Leads/${leadId}/actions/convert`,
        })
        return {
          ok: true,
          message: `Converted to Account, Contact, and Deal “${deal.name}”.`,
          dealId,
        }
      },
      moveDeal: (dealId, stage) => {
        const deal = state.deals.find((item) => item.id === dealId)
        if (!deal) return { ok: false, message: "Deal not found." }
        const check = canMoveDeal(deal, stage, state.activities)
        if (!check.ok) return check
        dispatch({ type: "move-deal", dealId, stage })
        dispatch({
          type: "add-sync",
          module: "Deals",
          action: "PUT",
          endpoint: `PUT /crm/v8/Deals/${dealId}`,
        })
        return check
      },
    }
  }, [state])

  return <CrmContext.Provider value={value}>{children}</CrmContext.Provider>
}

export function useCrm() {
  const ctx = useContext(CrmContext)
  if (!ctx) throw new Error("useCrm must be used inside CrmProvider")
  return ctx
}
