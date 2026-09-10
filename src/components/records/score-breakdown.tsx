import { ScoreMeter } from "@/components/records/score-meter"
import type { ScoreResult } from "@/lib/scoring"

const categoryOrder = ["Firmographic", "Intent", "Behavioral", "Negative"] as const

export function ScoreBreakdown({ result }: { result: ScoreResult }) {
  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between gap-4">
        <div>
          <p className="text-muted-foreground text-[11px] tracking-wide uppercase">Lead_Score</p>
          <p className="font-heading text-4xl tabular-nums">{result.total}</p>
        </div>
        <ScoreMeter score={result.total} />
      </div>
      {categoryOrder.map((category) => {
        const hits = result.hits.filter((hit) => hit.category === category)
        if (hits.length === 0) return null
        return (
          <div key={category}>
            <p className="text-muted-foreground mb-2 text-[11px] tracking-wide uppercase">
              {category}
            </p>
            <ul className="space-y-1.5">
              {hits.map((hit) => (
                <li key={hit.ruleId} className="flex items-start justify-between gap-3 text-sm">
                  <span>
                    <span className="font-medium">{hit.name}</span>
                    <span className="text-muted-foreground mt-0.5 block font-mono text-[11px]">
                      {hit.zohoCondition}
                    </span>
                  </span>
                  <span
                    className={
                      hit.points >= 0
                        ? "font-semibold text-[oklch(0.38_0.08_155)]"
                        : "font-semibold text-[oklch(0.48_0.14_28)]"
                    }
                  >
                    {hit.points > 0 ? "+" : ""}
                    {hit.points}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )
      })}
    </div>
  )
}
