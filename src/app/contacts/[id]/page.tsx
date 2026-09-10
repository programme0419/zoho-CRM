import { ContactDetail } from "@/components/views/contact-detail"

export default async function ContactPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  return <ContactDetail contactId={id} />
}
