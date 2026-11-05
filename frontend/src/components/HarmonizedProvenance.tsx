import { useSnapshotMeta } from "../api/harmonized";
import { useLanguage } from "../context/LanguageContext";
import DataCoverageNotice from "./DataCoverageNotice";

/** data_version and last_observation_time from /meta, in the hero-chips style. */
export default function HarmonizedProvenance({ window }: { window?: string }) {
  const { meta, fromApi } = useSnapshotMeta(window);
  const { t } = useLanguage();
  return (
    <><ul className="hero-chips hz-provenance" aria-label="Data provenance">
      <li><span className="dot" />{t("window")}: {meta?.window ?? "…"}</li>
      <li><span className="dot" />{t("data_version")}: <code>{meta?.data_version ?? t("awaiting")}</code></li>
      <li><span className="dot" />{t("last_obs")}: {meta?.last_observation_time ? `${meta.last_observation_time} UTC` : t("awaiting")}</li>
      {meta && !fromApi && <li className="hz-warn"><span className="dot" />{t("api_offline")}</li>}
    </ul>
    <DataCoverageNotice start={meta?.start} end={meta?.end} snapshot />
    </>
  );
}

/** Status shown with an icon and text, never colour alone. */
export function StatusPill({ status }: { status: string }) {
  const s = status.toLowerCase();
  const kind = s.includes("awaiting") ? "await" : s.includes("not applied") || s.includes("artifact") || s === "fail" ? "warn"
    : s.includes("validated") || s === "pass" || s === "computed" ? "ok" : "info";
  const icon = { await: "…", warn: "!", ok: "✓", info: "i" }[kind];
  return <span className={`hz-pill hz-pill-${kind}`}><span aria-hidden="true">{icon}</span>{status}</span>;
}
