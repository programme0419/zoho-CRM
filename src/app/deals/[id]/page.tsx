import { DealDetail } from "@/components/views/deal-detail"

export default async function DealPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  return <DealDetail dealId={id} />
}
