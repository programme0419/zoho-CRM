import { cn } from "@/lib/utils"
import { ratingFromScore, SCORE_THRESHOLDS } from "@/lib/scoring"

export function ScoreMeter({
  score,
  size = "md",
}: {
  score: number
  size?: "sm" | "md"
}) {
  const rating = ratingFromScore(score)
  const width = `${Math.min(100, Math.max(0, score))}%`
  const fill =
    rating === "Hot"
      ? "bg-[oklch(0.55_0.14_28)]"
      : rating === "Warm"
        ? "bg-[oklch(0.68_0.12_62)]"
        : "bg-[oklch(0.55_0.03_250)]"

  return (
    <div className={cn("min-w-16", size === "md" ? "w-28" : "w-20")}>
      <div className="mb-0.5 flex items-baseline justify-between gap-2">
        <span className={cn("font-semibold tabular-nums", size === "md" ? "text-sm" : "text-xs")}>
          {score}
        </span>
        <span className="text-muted-foreground text-[10px] uppercase">{rating}</span>
      </div>
      <div className={cn("overflow-hidden rounded-full bg-muted", size === "md" ? "h-1.5" : "h-1")}>
        <div className={cn("h-full rounded-full transition-all", fill)} style={{ width }} />
      </div>
      {size === "md" ? (
        <p className="text-muted-foreground mt-1 text-[10px]">
          Hot ≥ {SCORE_THRESHOLDS.hot} · Warm ≥ {SCORE_THRESHOLDS.warm}
        </p>
      ) : null}
    </div>
  )
}
