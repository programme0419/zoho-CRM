import type { Activity, Deal, DealStage } from "./types"

export type BlueprintCheck = {
  ok: boolean
  message: string
}

export function canMoveDeal(
  deal: Deal,
  target: DealStage,
  activities: Activity[]
): BlueprintCheck {
  if (deal.stage === target) {
    return { ok: false, message: "Deal is already in this stage." }
  }

  if (target === "Needs Analysis") {
    const discovery = activities.some(
      (activity) =>
        activity.relatedId === deal.id &&
        (activity.type === "Call" || activity.type === "Meeting") &&
        activity.status === "Completed"
    )
    if (!discovery) {
      return {
        ok: false,
        message:
          "Blueprint: log a completed discovery call or meeting before Needs Analysis.",
      }
    }
  }

  if (target === "Proposal/Price Quote" && deal.amount <= 0) {
    return { ok: false, message: "Blueprint: Amount must be greater than zero before a proposal." }
  }

  if (target === "Closed Won" && !deal.poNumber) {
    return {
      ok: false,
      message: "Blueprint: PO Number is required to close-win. Add it on the deal, then retry.",
    }
  }

  if (target === "Closed Lost" && !deal.lostReason && deal.stage !== "Closed Lost") {
    return {
      ok: false,
      message: "Blueprint: capture a lost reason before closing lost.",
    }
  }

  return { ok: true, message: `Stage moved to ${target}. Workflows will fire on Zoho CRM.` }
}
