import { LeadDetail } from "@/components/views/lead-detail"

export default async function LeadPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  return <LeadDetail leadId={id} />
}
