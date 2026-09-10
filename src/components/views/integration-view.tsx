"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { PageHeader } from "@/components/records/page-header"
import { StatusBadge } from "@/components/records/status-badge"
import { useCrm } from "@/lib/crm-store"
import { formatDateTime } from "@/lib/format"
import {
  FIELD_MAP,
  SAMPLE_COQL,
  SAMPLE_SCORE_COQL,
  SAMPLE_CONVERT,
  SAMPLE_LEAD_PAYLOAD,
  ZOHO_ENDPOINTS,
  ZOHO_SCOPES,
} from "@/lib/zoho"
import { ORG } from "@/lib/seed"

export function IntegrationView() {
  const { syncLog } = useCrm()

  return (
    <div>
      <PageHeader
        eyebrow="Zoho CRM API v8"
        title="The integration a client can audit."
        description={`${ORG.name} talks to ${ORG.region} on ${ORG.apiVersion}. This workspace ships with a demo org so the UI is always live; point the same routes at a real refresh token when you are ready.`}
      />

      <div className="mb-4 grid gap-3 md:grid-cols-3">
        <Card>
          <CardContent>
            <p className="text-muted-foreground text-[11px] tracking-wide uppercase">Connection</p>
            <p className="mt-2 text-lg font-medium">Demo org · mock + API map</p>
            <p className="text-muted-foreground mt-1 text-sm">{ORG.zohoOrg}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <p className="text-muted-foreground text-[11px] tracking-wide uppercase">Auth</p>
            <p className="mt-2 text-lg font-medium">OAuth 2.0 · offline</p>
            <p className="text-muted-foreground mt-1 text-sm">accounts.zoho.eu/oauth/v2/token</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <p className="text-muted-foreground text-[11px] tracking-wide uppercase">Webhooks</p>
            <p className="mt-2 text-lg font-medium">actions/watch</p>
            <p className="text-muted-foreground mt-1 text-sm">Leads, Deals, Contacts</p>
          </CardContent>
        </Card>
      </div>

      <Card className="mb-4">
        <CardHeader className="border-b">
          <CardTitle>OAuth scopes</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          {ZOHO_SCOPES.map((scope) => (
            <code key={scope} className="rounded-md bg-muted px-2 py-1 font-mono text-[11px]">
              {scope}
            </code>
          ))}
        </CardContent>
      </Card>

      <Card className="mb-4">
        <CardHeader className="border-b">
          <CardTitle>Endpoints this workspace uses</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Method</TableHead>
                <TableHead>Path</TableHead>
                <TableHead>Purpose</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ZOHO_ENDPOINTS.map((endpoint) => (
                <TableRow key={endpoint.path}>
                  <TableCell className="font-mono text-xs">{endpoint.method}</TableCell>
                  <TableCell className="font-mono text-xs">{endpoint.path}</TableCell>
                  <TableCell>{endpoint.purpose}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card className="mb-4">
        <CardHeader className="border-b">
          <CardTitle>UI field → Zoho API name</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Workspace</TableHead>
                <TableHead>Zoho</TableHead>
                <TableHead>Module</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {FIELD_MAP.map((field) => (
                <TableRow key={field.ui}>
                  <TableCell>{field.ui}</TableCell>
                  <TableCell className="font-mono text-xs">{field.zoho}</TableCell>
                  <TableCell>{field.module}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <div className="mb-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="border-b">
            <CardTitle>COQL — deals closing this month</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="overflow-x-auto rounded-xl bg-[oklch(0.22_0.02_50)] p-4 font-mono text-[12px] leading-6 text-[oklch(0.93_0.02_90)]">
              {SAMPLE_COQL}
            </pre>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="border-b">
            <CardTitle>COQL — hot scored leads</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="overflow-x-auto rounded-xl bg-[oklch(0.22_0.02_50)] p-4 font-mono text-[12px] leading-6 text-[oklch(0.93_0.02_90)]">
              {SAMPLE_SCORE_COQL}
            </pre>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="border-b">
            <CardTitle>Create lead payload</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="overflow-x-auto rounded-xl bg-[oklch(0.22_0.02_50)] p-4 font-mono text-[12px] leading-6 text-[oklch(0.93_0.02_90)]">
              {SAMPLE_LEAD_PAYLOAD}
            </pre>
          </CardContent>
        </Card>
      </div>

      <Card className="mb-4">
        <CardHeader className="border-b">
          <CardTitle>Convert lead body</CardTitle>
        </CardHeader>
        <CardContent>
          <pre className="overflow-x-auto rounded-xl bg-[oklch(0.22_0.02_50)] p-4 font-mono text-[12px] leading-6 text-[oklch(0.93_0.02_90)]">
            {SAMPLE_CONVERT}
          </pre>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="border-b">
          <CardTitle>Sync log</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>When</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Endpoint</TableHead>
                <TableHead>Records</TableHead>
                <TableHead>Latency</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {syncLog.map((event) => (
                <TableRow key={event.id}>
                  <TableCell className="text-muted-foreground text-xs">
                    {formatDateTime(event.at)}
                  </TableCell>
                  <TableCell className="font-mono text-xs">{event.action}</TableCell>
                  <TableCell className="font-mono text-xs">{event.endpoint}</TableCell>
                  <TableCell>{event.records}</TableCell>
                  <TableCell>{event.latencyMs}ms</TableCell>
                  <TableCell>
                    <StatusBadge value={event.status} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
