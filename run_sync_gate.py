"""D68 synchronization gate for every window, then the synchronized-window analyses.

    E:\anaconda\envs\flameseek\python.exe run_sync_gate.py

Windows: current_2026 (gate only; must fail on part (a)), sync_2016, sync_2014 (if
data/raw/archive/2014/ has FIRMS files). Results: outputs/stages/stage5_sync_gate.json.
"""
from pipeline import himawari as hw, sync_window
from pipeline.config import ROOT
from run_phase3c import calibration_table, recommendations

WINDOWS = ["current_2026", "sync_2016", "sync_2014"]


def main() -> dict:
    results = {}
    for w in WINDOWS:
        print(f"[sync gate] {w}", flush=True)
        results[w] = sync_window.process(w)
        g = results[w]["gate"]
        print(f"[sync gate] {w}: {g.get('status')} synchronized={g.get('synchronized')}", flush=True)
    cal = {w: results[w].get("calibration", {}) for w in ("sync_2016", "sync_2014")}
    comparison = sync_window.compare_calibrations(cal["sync_2016"], cal["sync_2014"])
    if results["sync_2014"]["gate"].get("status") == "awaiting data":
        comparison = {"status": "awaiting data", "reason": "data/raw/archive/2014/ has no FIRMS files"}
    rows = calibration_table(None)
    selection = recommendations(rows)
    hw.json_write(ROOT / "outputs/phase3c_calibration_selection.json",
                  dict(calibrations=rows, recommendations=selection, active_parameters_changed=False))
    out = {"windows": results, "calibration_2014_vs_2016": comparison}
    hw.json_write(ROOT / "outputs/stages/stage5_sync_gate.json", out)
    return out


if __name__ == "__main__":
    main()
