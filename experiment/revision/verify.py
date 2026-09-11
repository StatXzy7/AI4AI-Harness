"""Fail if the corrected results, generated paper assets or compiled PDF are stale."""
import json

from experiment.revision.replay import ROOT, digest


def merge_expectations(*manifests):
    """Reject mismatched provenance even when one version matches today's file."""
    expected = {}
    for manifest in manifests:
        for name, sha in manifest.items():
            if name in expected and expected[name] != sha:
                raise SystemExit("CONFLICTING provenance: " + name)
            expected[name] = sha
    return expected


def main():
    directory = ROOT / "artifacts/revision_20260910"
    data = json.loads((directory / "corrected_analysis.json").read_text(encoding="utf-8"))
    assets = json.loads((directory / "paper_assets_manifest.json").read_text(encoding="utf-8"))
    sensitivity = json.loads((directory / "sensitivity.json").read_text(encoding="utf-8"))
    cost = json.loads((directory / "cost_audit.json").read_text(encoding="utf-8"))
    exploratory = {name: json.loads((directory / f"{name}.json").read_text(encoding="utf-8"))
                   for name in ("fingerprint", "selection")}
    verified = json.loads((directory / "verification.json").read_text(encoding="utf-8"))
    expected = merge_expectations({"artifacts/revision_20260910/corrected_analysis.json": assets["analysis_sha256"],
                "experiment/revision/render.py": assets["generator_sha256"],
                "artifacts/revision_20260910/sensitivity.json": assets["sensitivity_sha256"],
                "artifacts/revision_20260910/cost_audit.json": assets["cost_sha256"],
                "paper/latex/main.pdf": verified["pdf_sha256"]},
                assets["generated"], verified["manuscript_sources"], verified["build_inputs"],
                {r["path"]: r["sha256"] for r in data["inputs"]
                 if r["path"] == "experiment/revision/replay.py"},
                {r["path"]: r["sha256"] for r in sensitivity["inputs"]
                 if r["path"].startswith("experiment/revision/")},
                {r["path"]: r["sha256"] for r in cost["inputs"]
                 if r["path"].startswith("experiment/revision/")})
    for name, artifact in exploratory.items():
        expected = merge_expectations(expected, {
            f"artifacts/revision_20260910/{name}.json": assets[f"{name}_sha256"]},
            {r["path"]: r["sha256"] for r in artifact["inputs"]
             if r["path"].startswith("experiment/revision/")})
        if verified[f"{name}_sha256"] != assets[f"{name}_sha256"]:
            raise SystemExit(f"PDF verification used a different {name} artifact")
        if (artifact["n_cells"], artifact["n_harnesses"], artifact["n_tasks"]) != (18, 384, 400):
            raise SystemExit("unexpected exploratory sample size")
    stale = [name for name, sha in expected.items()
             if not (ROOT / name).is_file() or digest(ROOT / name) != sha]
    if stale:
        raise SystemExit("STALE: " + ", ".join(stale))
    if verified["analysis_sha256"] != assets["analysis_sha256"]:
        raise SystemExit("PDF verification used a different analysis artifact")
    if verified["sensitivity_sha256"] != assets["sensitivity_sha256"]:
        raise SystemExit("PDF verification used a different sensitivity artifact")
    if verified["cost_sha256"] != assets["cost_sha256"]:
        raise SystemExit("PDF verification used a different cost artifact")
    if sensitivity["n_boot"] != 10000 or sensitivity["kmatched"]["n_cells"] != 18 or sensitivity["r2"]["n_cells"] != 18:
        raise SystemExit("unexpected sensitivity analysis size")
    if (data["n_boot"], data["primary"]["n_cells"], data["primary"]["n_tasks"],
            data["core"]["n_tasks"], verified["main_pages"]) != (10000, 18, 1169, 400, 9):
        raise SystemExit("unexpected analysis size or manuscript page count")
    for study in ("primary", "core"):
        for m in data[study]["arm_means"].values():
            if abs(m["oracle_accuracy"] - m["best_fixed"] - m["headroom"]) > 1e-12:
                raise SystemExit("invalid headroom decomposition")
            if abs(m["K_candidate"] + 1 - m["K_total"]) > 1e-12:
                raise SystemExit("inconsistent bare-inclusive population size")
    print(f"PASS: {len(expected)} source/result/asset hashes; sample sizes, page count and decompositions")


if __name__ == "__main__":
    main()
