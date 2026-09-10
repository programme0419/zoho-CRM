import Link from "next/link"
import { Button } from "@/components/ui/button"

export default function NotFound() {
  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center text-center">
      <p className="text-muted-foreground text-[11px] tracking-[0.18em] uppercase">404</p>
      <h1 className="font-heading mt-2 text-3xl">That record is not in this org.</h1>
      <p className="text-muted-foreground mt-2 max-w-md text-sm">
        It may have been converted, merged, or you followed a stale Zoho ID.
      </p>
      <Button className="mt-6" asChild>
        <Link href="/">Back to command center</Link>
      </Button>
    </div>
  )
}
