export type UserId = string
export type AccountId = string
export type ContactId = string
export type LeadId = string
export type DealId = string
export type ActivityId = string
export type NoteId = string

export type UserRole =
  | "VP Sales"
  | "Enterprise AE"
  | "Mid-Market AE"
  | "SDR"
  | "Solutions Consultant"
  | "CSM"

export type LeadStatus =
  | "Not Contacted"
  | "Contacted"
  | "Qualified"
  | "Hot"
  | "Unqualified"
  | "Lost Lead"

export type LeadSource =
  | "Website"
  | "Trade Show"
  | "Referral"
  | "Outbound"
  | "Partner"
  | "Inbound Call"

export type AccountType = "Customer" | "Prospect" | "Partner" | "Competitor"

export type DealStage =
  | "Qualification"
  | "Needs Analysis"
  | "Value Proposition"
  | "Proposal/Price Quote"
  | "Negotiation/Review"
  | "Closed Won"
  | "Closed Lost"

export type ActivityType = "Task" | "Call" | "Meeting"
export type ActivityStatus = "Not Started" | "In Progress" | "Completed" | "Deferred"

export type User = {
  id: UserId
  name: string
  email: string
  role: UserRole
  territory: string
  avatarHue: number
  quota: number
}

export type Account = {
  id: AccountId
  name: string
  industry: string
  type: AccountType
  website: string
  phone: string
  billingCity: string
  billingCountry: string
  annualRevenue: number
  employees: number
  ownerId: UserId
  rating: "Hot" | "Warm" | "Cold"
  description: string
  createdTime: string
}

export type Contact = {
  id: ContactId
  firstName: string
  lastName: string
  title: string
  email: string
  phone: string
  accountId: AccountId
  ownerId: UserId
  department: string
  mailingCity: string
  mailingCountry: string
  createdTime: string
}

export type Lead = {
  id: LeadId
  firstName: string
  lastName: string
  company: string
  title: string
  email: string
  phone: string
  status: LeadStatus
  source: LeadSource
  industry: string
  annualRevenue: number
  rating: "Hot" | "Warm" | "Cold"
  ownerId: UserId
  score: number
  city: string
  country: string
  createdTime: string
  converted: boolean
  convertedContactId?: ContactId
  convertedAccountId?: AccountId
  convertedDealId?: DealId
}

export type Deal = {
  id: DealId
  name: string
  accountId: AccountId
  contactId: ContactId
  stage: DealStage
  amount: number
  probability: number
  closingDate: string
  ownerId: UserId
  pipeline: "Enterprise" | "Mid-Market"
  nextStep: string
  product: string
  leadSource: LeadSource
  createdTime: string
  poNumber?: string
  lostReason?: string
}

export type Activity = {
  id: ActivityId
  subject: string
  type: ActivityType
  status: ActivityStatus
  dueDate: string
  ownerId: UserId
  relatedModule: "Leads" | "Contacts" | "Accounts" | "Deals"
  relatedId: string
  relatedName: string
  notes: string
}

export type Note = {
  id: NoteId
  module: "Leads" | "Contacts" | "Accounts" | "Deals"
  recordId: string
  authorId: UserId
  body: string
  createdTime: string
}

export type WorkflowRule = {
  id: string
  name: string
  module: string
  trigger: string
  condition: string
  actions: string[]
  status: "Active" | "Inactive"
  lastRun: string
  runs: number
}

export type SyncEvent = {
  id: string
  at: string
  module: string
  action: "GET" | "POST" | "PUT" | "CONVERT" | "COQL" | "WATCH"
  endpoint: string
  records: number
  status: "Synced" | "Retrying" | "Failed"
  latencyMs: number
}

export type CrmState = {
  users: User[]
  accounts: Account[]
  contacts: Contact[]
  leads: Lead[]
  deals: Deal[]
  activities: Activity[]
  notes: Note[]
  workflows: WorkflowRule[]
  syncLog: SyncEvent[]
  currentUserId: UserId
}

export const STAGE_ORDER: DealStage[] = [
  "Qualification",
  "Needs Analysis",
  "Value Proposition",
  "Proposal/Price Quote",
  "Negotiation/Review",
  "Closed Won",
  "Closed Lost",
]

export const STAGE_PROBABILITY: Record<DealStage, number> = {
  Qualification: 10,
  "Needs Analysis": 20,
  "Value Proposition": 40,
  "Proposal/Price Quote": 60,
  "Negotiation/Review": 80,
  "Closed Won": 100,
  "Closed Lost": 0,
}

export const OPEN_STAGES: DealStage[] = [
  "Qualification",
  "Needs Analysis",
  "Value Proposition",
  "Proposal/Price Quote",
  "Negotiation/Review",
]
