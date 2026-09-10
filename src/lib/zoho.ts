export const ZOHO_SCOPES = [
  "ZohoCRM.modules.leads.ALL",
  "ZohoCRM.modules.contacts.ALL",
  "ZohoCRM.modules.accounts.ALL",
  "ZohoCRM.modules.deals.ALL",
  "ZohoCRM.modules.tasks.ALL",
  "ZohoCRM.modules.calls.ALL",
  "ZohoCRM.modules.events.ALL",
  "ZohoCRM.modules.notes.ALL",
  "ZohoCRM.settings.ALL",
  "ZohoCRM.coql.READ",
]

export const ZOHO_ENDPOINTS = [
  {
    method: "GET",
    path: "/crm/v8/Leads",
    purpose: "List inbound leads with pagination and field selection",
  },
  {
    method: "POST",
    path: "/crm/v8/Leads",
    purpose: "Create a lead from web form or SDR capture",
  },
  {
    method: "POST",
    path: "/crm/v8/Leads/{id}/actions/convert",
    purpose: "Convert lead → Account + Contact + Deal in one transaction",
  },
  {
    method: "GET",
    path: "/crm/v8/Deals",
    purpose: "Pull pipeline for the command-center kanban",
  },
  {
    method: "PUT",
    path: "/crm/v8/Deals/{id}",
    purpose: "Stage moves, amount edits, PO number on Closed Won",
  },
  {
    method: "GET",
    path: "/crm/v8/settings/pipeline",
    purpose: "Read layout pipelines and mapped stages",
  },
  {
    method: "POST",
    path: "/crm/v8/coql",
    purpose: "Forecast and stale-proposal queries without full module scans",
  },
  {
    method: "GET",
    path: "/crm/v8/settings/automation/scoring_rules",
    purpose: "Read the Helios lead scoring rule set (positive / negative)",
  },
  {
    method: "PUT",
    path: "/crm/v8/Leads/{id}",
    purpose: "Write Lead_Score and Rating after the engine recalculates",
  },
]

export const FIELD_MAP = [
  { ui: "Company", zoho: "Company", module: "Leads" },
  { ui: "Lead status", zoho: "Lead_Status", module: "Leads" },
  { ui: "Lead source", zoho: "Lead_Source", module: "Leads" },
  { ui: "Lead score", zoho: "Lead_Score", module: "Leads" },
  { ui: "Rating", zoho: "Rating", module: "Leads" },
  { ui: "CHP calculator used", zoho: "CHP_Calculator_Used (custom)", module: "Leads" },
  { ui: "Website sessions", zoho: "Website_Sessions (custom)", module: "Leads" },
  { ui: "Annual revenue", zoho: "Annual_Revenue", module: "Leads / Accounts" },
  { ui: "Account name", zoho: "Account_Name", module: "Accounts" },
  { ui: "Deal name", zoho: "Deal_Name", module: "Deals" },
  { ui: "Stage", zoho: "Stage", module: "Deals" },
  { ui: "Amount", zoho: "Amount", module: "Deals" },
  { ui: "Probability", zoho: "Probability", module: "Deals" },
  { ui: "Closing date", zoho: "Closing_Date", module: "Deals" },
  { ui: "Pipeline", zoho: "Pipeline", module: "Deals" },
  { ui: "PO number", zoho: "PO_Number (custom)", module: "Deals" },
  { ui: "Owner", zoho: "Owner", module: "All" },
]

export const SAMPLE_COQL = `select Deal_Name, Amount, Stage, Probability, Closing_Date, Owner
from Deals
where Stage not in ('Closed Won', 'Closed Lost')
  and Closing_Date between '2026-09-01' and '2026-09-30'
order by Amount desc`

export const SAMPLE_SCORE_COQL = `select Last_Name, Company, Lead_Score, Rating, Annual_Revenue
from Leads
where Lead_Score >= 70
  and Lead_Status not in ('Lost Lead', 'Unqualified')
order by Lead_Score desc`

export const SAMPLE_CONVERT = `{
  "data": [
    {
      "overwrite": true,
      "notify_lead_owner": true,
      "notify_new_entity_owner": true,
      "Accounts": { "Account_Name": "Alpine Grid Services" },
      "Contacts": { "Last_Name": "Keller", "Email": "sabine.keller@alpinegrid.ch" },
      "Deals": {
        "Deal_Name": "Alpine Grid — CHP discovery",
        "Stage": "Qualification",
        "Closing_Date": "2026-11-30",
        "Pipeline": "Enterprise"
      }
    }
  ]
}`

export const SAMPLE_LEAD_PAYLOAD = `{
  "data": [
    {
      "Last_Name": "Keller",
      "First_Name": "Sabine",
      "Company": "Alpine Grid Services",
      "Email": "sabine.keller@alpinegrid.ch",
      "Lead_Source": "Website",
      "Lead_Status": "Hot",
      "Industry": "Utilities",
      "Annual_Revenue": 220000000,
      "Layout": { "name": "Standard" }
    }
  ],
  "trigger": ["workflow", "blueprint"]
}`
