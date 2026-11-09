import type { CaseKind } from "../types/api";

export const BEHAVIOUR_PLAIN: Record<string, string> = {
  Onset: "Just started", Intensifying: "Getting stronger", Expanding: "Spreading", Persistent: "Burning for days",
  Stable: "Steady", Decaying: "Dying down", Uncertain: "Too early to tell",
};
export const KIND_COLORS: Record<CaseKind, string> = {
  agricultural_burn: "#eab308", wildfire: "#ef4444", controlled_burn: "#a855f7", industrial_source: "#22d3ee",
  building_fire: "#f97316", volcanic: "#be123c", not_a_fire: "#94a3b8", unknown: "#e2e8f0",
};
export const KIND_LABELS: Record<CaseKind, string> = {
  agricultural_burn: "Agricultural burn", wildfire: "Forest or wildfire", controlled_burn: "Controlled burn",
  industrial_source: "Industrial heat / gas flare", building_fire: "Building or industrial fire", volcanic: "Volcanic activity",
  not_a_fire: "Not a fire", unknown: "Type not yet known",
};
export const REALITY_WEIGHT: Record<string, number> = {
  "Confirmed fire": 5, "Highly likely fire": 4, "Possible fire (needs verification)": 2,
  "No external confirmation yet": 2, "Likely non-fire thermal anomaly": 1,
};
export const BEHAVIOUR_COLORS: Record<string, string> = {
  Onset: "#38bdf8", Intensifying: "#f43f5e", Expanding: "#f97316", Persistent: "#eab308",
  Stable: "#a3e635", Decaying: "#94a3b8", Uncertain: "#c4b5fd",
};
