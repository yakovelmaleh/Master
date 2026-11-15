#!/usr/bin/env python3
"""Append four T5 diagnostic slides from verified saved aggregate evidence."""

import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from pptx import Presentation
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches

TASK = Path(__file__).resolve().parent
REPO = TASK.parents[1]
GENERATOR = REPO / "skills/sprint-presentation/scripts/sprint_presentation.py"
RUN_ID = "diag-m2-20261111-01"
CONFIG_SHA = "49f8e6ba0db07f3948856e0647e3ac2b24f81845c470606dd49f3f9dc86a05de"


def sha(content):
    return hashlib.sha256(content).hexdigest()


def preserve_data(path, content):
    if path.exists() and path.read_bytes() != content:
        raise ValueError(f"Existing evidence differs: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(content)


def load_evidence(path):
    names = [
        "run.json", "summary.json", "manifest/status.json",
        "manifest/embedding_status.json", "complexity/length_evidence.json",
        "complexity/characteristic_profiles.json",
        "complexity/matched_characteristic_metrics.json",
        "complexity/exact_duplicate_disagreement.json", "shift/temporal_shift.json",
    ]
    with tarfile.open(path) as archive:
        members = archive.getmembers()
        if len({m.name for m in members}) != len(members):
            raise ValueError("Duplicate archive members.")
        raw = {}
        for name in names:
            if not archive.getmember(name).isfile():
                raise ValueError(f"Not a regular aggregate file: {name}")
            raw[name] = archive.extractfile(name).read()
    data = {name: json.loads(content) for name, content in raw.items()}
    status = data["manifest/status.json"]
    for name, content in raw.items():
        if name != "manifest/status.json" and sha(content) != status["outputs_sha256"][name]:
            raise ValueError(f"Aggregate hash mismatch: {name}")
        if data[name]["run_id"] != RUN_ID or data[name]["configuration_sha256"] != CONFIG_SHA:
            raise ValueError("Unexpected run or configuration.")
    summary = data["summary.json"]
    metrics = data["complexity/matched_characteristic_metrics.json"]["comparisons"]
    if (summary["t5_text_status"] != "succeeded" or len(metrics) != 2304
            or sum(r["adequate_support"] for r in metrics) != 1197):
        raise ValueError("Unexpected T5 completion/support counts.")
    blocks = data["manifest/embedding_status.json"]["blocked"]
    if len(blocks) != 6 or any(r.get("split") != "test" for r in blocks):
        raise ValueError("This presentation expects six unavailable test embedding caches.")
    balance = []
    for family in ("SLM1", "SLM2", "Jev"):
        row = {"family": family}
        for split in ("validation", "test"):
            cells = [r for r in metrics if r["family"] == family and r["split"] == split
                     and r["slice"].startswith("length_bin:") and r["adequate_support"]]
            row[split] = {
                "supported": len(cells),
                "wins": sum(r["auc_prc_difference_model_minus_classical"] > 0 for r in cells),
                "interval_includes_zero": sum(
                    r["uncertainty"]["interval_95"][0] <= 0 <= r["uncertainty"]["interval_95"][1]
                    for r in cells
                ),
            }
        balance.append(row)
    selected = []
    for project, level, bin_index, family in (
        ("Apache", 5, 2, "SLM1"), ("Qt", 15, 3, "SLM2"),
    ):
        for split in ("validation", "test"):
            matches = [r for r in metrics if
                       (r["project"], r["level"], r["slice"], r["family"], r["split"]) ==
                       (project, level, f"length_bin:{bin_index}", family, split)]
            if len(matches) != 1 or not matches[0]["adequate_support"]:
                raise ValueError("Missing supported illustrative comparison.")
            selected.append(matches[0])
    profiles = data["complexity/characteristic_profiles.json"]["profiles"]
    rare = {}
    for flag in ("summary_equals_description", "reference_only_description",
                 "duplicate_within_split", "seen_in_train"):
        rare[flag] = {
            split: sum(r["adequate_support"] for r in profiles if
                       r["split"] == split and r["slice"] == flag + ":true")
            for split in ("validation", "test")
        }
    if any(value for splits in rare.values() for value in splits.values()):
        raise ValueError("Repetition support changed; review the conclusions.")
    return {
        "run": data["run.json"], "summary": summary,
        "source_archive_sha256": sha(path.read_bytes()),
        "source_files_sha256": {name: sha(value) for name, value in raw.items()},
        "balance": balance, "selected_scores": selected, "rare_flag_support": rare,
        "temporal": [r for r in data["shift/temporal_shift.json"]["comparisons"]
                     if r["project"] in ("Jira", "IntelDAOS")],
        "temporal_label_profiles": [r for r in profiles if r["project"] in ("Jira", "IntelDAOS")
                                    and r["slice"] == "all" and r["level"] in (5, 20)],
        "empty_scores": [r for r in metrics if r["project"] == "Apache" and
                         r["level"] == 5 and r["family"] == "SLM2" and
                         r["slice"].startswith("empty_description:")],
        "length_profiles": [r for r in profiles if r["project"] in ("Apache", "Hyperledger")
                            and r["level"] == 5 and r["slice"].startswith("length_bin:")
                            and r["split"] in ("validation", "test")],
        "duplicate_profiles": data["complexity/exact_duplicate_disagreement.json"]["comparisons"],
        "selection_note": "All supported length cells counted. Apache/Qt paired split examples illustrate adverse and favorable test outcomes, not a random sample or a model-selection rule.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--presentation", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument("--output", type=Path)
    destination.add_argument("--in-place", action="store_true")
    args = parser.parse_args()
    root = Path(subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], cwd=REPO, text=True
    ).strip()).resolve()
    remote = subprocess.check_output(
        ["git", "remote", "get-url", "origin"], cwd=REPO, text=True
    ).strip()
    if (root != REPO or root.name != "Master" or "yakovelmaleh/Master" not in remote
            or not (REPO / "Tasks/run_cluster_task.sh").is_file() or not GENERATOR.is_file()):
        raise ValueError("This builder requires yakovelmaleh/Master.")
    original = args.presentation.read_bytes()
    prs = Presentation(io.BytesIO(original))
    initial_count = len(prs.slides)
    if any(s.has_notes_slide and RUN_ID in s.notes_slide.notes_text_frame.text for s in prs.slides):
        raise ValueError("These diagnostic results are already in the deck.")
    output = args.presentation if args.in_place else args.output
    if output.exists() and not args.in_place:
        raise FileExistsError(output)
    if args.backup.resolve() in (args.presentation.resolve(), output.resolve()):
        raise ValueError("Backup must not replace the input or output deck.")
    evidence = load_evidence(args.archive)
    evidence_path = TASK / "data" / f"{RUN_ID}-presentation.json"
    spec_path = TASK / "specs" / f"{RUN_ID}.json"
    preserve_data(evidence_path, (json.dumps(evidence, indent=2) + "\n").encode())
    spec = {
        "experiment": "Why do instability models disagree?",
        "task": "Inspect saved predictions using frozen text characteristics.",
        "why": ["Explain heterogeneous results without changing labels or training new models."],
        "data": {
            "old": {"name": "Earlier studies", "metrics": {"Population": "23,822 stories"}},
            "new": {"name": "T5 diagnostics", "metrics": {"Population": "Same 23,822 stories"}},
            "notes": ["Same chronological splits; test interpretation remains exploratory."],
        },
        "results": {
            "visual": "table", "columns": ["Family", "Validation wins", "Test wins"],
            "rows": [[r["family"]] + [
                f'{r[s]["wins"]}/{r[s]["supported"]}' for s in ("validation", "test")
            ] for r in evidence["balance"]],
        },
        "conclusions": {
            "findings": ["No general SLM length advantage.", "Missing/repetitive-text mechanisms unresolved."],
            "next_steps": ["Return evidence to coordination; no improvement experiments."],
        },
        "source_evidence": evidence_path.relative_to(TASK).as_posix(),
        "source_evidence_sha256": sha(evidence_path.read_bytes()),
    }
    preserve_data(spec_path, (json.dumps(spec, indent=2) + "\n").encode())
    preserve_data(args.backup, original)
    module_spec = importlib.util.spec_from_file_location("sprint_style", GENERATOR)
    style = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(style)
    provenance = (
        f"Run {RUN_ID}, SLURM 24109367; interpreted November 15, 2026.\n"
        f"Source archive SHA256 {evidence['source_archive_sha256']}.\n"
        f"Evidence {evidence_path.relative_to(REPO)}; SHA256 {sha(evidence_path.read_bytes())}.\n"
        f"Config SHA256 {CONFIG_SHA}. Cluster root /home/yakovelm/master-hf/diagnostics/{RUN_ID}/.\n"
        "Eight included outputs match the accompanying manifest; not independent authentication. "
        "No analysis, bootstrap, training or inference rerun. Labels require >=K changed words AND "
        "at least one relevant recorded edit. K tasks are nested, not disjoint or percentages. "
        "SLM1=ModernBERT/Qwen embeddings; SLM2=Phi/Gemma/Qwen3.5; Jev=local community zero-shot model. "
        "AUC-PRC is primary; AP retained in evidence. Classical/model choices and thresholds are "
        "the existing validation-selected choices. Validation was used for selection; test is a "
        "previously observed exploratory holdout. Length bins are per-project training quartiles, "
        "numbered 0 (shortest) to 3 (longest); exact word cutoffs not in this archive. "
        "Minimum support: 50 rows, 10 positives, 10 negatives. Paired within-slice intervals: "
        "500 non-circular chronological 20-row blocks, seed 20261111; gaps compressed within slices; "
        "unadjusted, no model-selection correction. Not cross-split or interaction intervals. "
        "Earlier study slides retain their original IID intervals; these different procedures "
        "must not be selected by favorable sign. Scores alone do not establish significance. "
        "Twenty human text reviews generated hypotheses, not new labels or population rates. "
        "Actual histories remain unavailable; labels unverified. All six test embedding caches "
        "are missing; available embedding comparisons are not test findings. "
        "Exit 2 is expected partial blockage, not a crash. No T6/T7.\n"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".t5-slides-", dir=output.parent) as temporary:
        staged = Path(temporary) / "presentation.pptx"
        subprocess.run([
            sys.executable, str(GENERATOR), "append", "--presentation", str(args.presentation),
            "--spec", str(spec_path), "--output", str(staged),
        ], cwd=REPO, check=True)
        prs = Presentation(staged)
        intro, data_slide, results, conclusions = list(prs.slides)[initial_count:]

        def clear(slide, title):
            for shape in list(slide.shapes):
                if not shape.is_placeholder:
                    shape._element.getparent().remove(shape._element)
            style.set_slide_title(slide, title)

        def text(slide, y, value, size=17, color=None, height=0.5):
            style.add_textbox(slide, 0.95, y, 11.45, height, value,
                              size=size, color=color or style.DARK_GRAY)

        clear(intro, "Why do instability models disagree?")
        text(intro, 1.42, "T5 diagnostics: explain existing results, not train another model.", 22)
        style.add_section_card(intro, 0.95, 2.12, 5.5, 3.5, "COMPLETED EVIDENCE", style.ORANGE)
        style.add_bullets(intro, 1.2, 2.78, 4.95, 2.65, [
            "Same six projects; saved predictions and original sprint-entry text.",
            "2,304 characteristic comparisons; 1,197 meet support minimums.",
            "Length, empty/repetitive text and chronological shifts.",
        ], size=19)
        style.add_section_card(intro, 6.85, 2.12, 5.5, 3.5, "WHAT THIS CAN ESTABLISH", style.ORANGE)
        style.add_bullets(intro, 7.1, 2.78, 4.95, 2.65, [
            "Associations with recorded future edits, not perceived writing quality.",
            "20 human text reviews generate hypotheses only.",
            "No single failure explanation; labels remain unverified.",
        ], size=19)
        text(intro, 5.82, "SLM1: ModernBERT / Qwen embeddings. SLM2: Phi / Gemma / Qwen3.5.", 14, height=0.32)
        text(intro, 6.16, "Jev: local community zero-shot model. T5 text succeeded; six test embedding caches unavailable.", 14, height=0.32)
        text(intro, 6.55, "Label: >=K changed words AND >=1 recorded text edit; K=5/10/15/20. Test findings are exploratory.", 14)

        clear(data_slide, "Data Analysis - same stories, new diagnostic view")
        style.add_table(data_slide, 0.95, 1.43, 11.45, 2.05,
                        ["Contract", "Earlier model comparisons", "This diagnostic"], [
            ["Population", "23,822 stories; six projects", "Same stories; no new exclusions"],
            ["Train / validation / test", "14,290 / 4,762 / 4,770", "Same frozen chronological splits"],
            ["Labels / models", "K=5/10/15/20; validation selection", "Unchanged; no relabeling or training"],
            ["Comparison unit", "Whole project / K", "Training-defined length bins + text flags"],
        ], font_size=15, column_widths=[2.55, 4.45, 4.45])
        text(data_slide, 3.65, "Chronological shift: longer text does not always mean more recorded instability.", 18)
        temporal_index = {(r["project"], r["split"]): r for r in evidence["temporal"]}
        temporal_rows = []
        for project in ("Jira", "IntelDAOS"):
            row = [project + " / K5"]
            for split in ("train", "validation", "test"):
                value = temporal_index[project, split]
                label = value["labels"]["5"]
                row.append(
                    f'{value["rows"]:,} stories / {label["positives"]} positives\n'
                    f'{value["word_length_quantiles"]["0.5"]:g} median words\n'
                    f'{label["prevalence"]:.1%} recorded instability'
                )
            temporal_rows.append(row)
        temporal_table = style.add_table(
            data_slide, 0.95, 4.3, 11.45, 2.13,
            ["Project / K", "Training", "Validation", "Exploratory test"],
            temporal_rows, font_size=15, column_widths=[1.7, 3.25, 3.25, 3.25])
        temporal_table.rows[0].height = Inches(0.39)
        for row in list(temporal_table.rows)[1:]:
            row.height = Inches(0.87)
        text(data_slide, 6.61, "Descriptive shifts, not causal effects. K20 differs from K5 in Jira; counts and prevalence intervals are in notes.", 13)

        clear(results, "Results - SLM gains vary by length and split")
        text(results, 1.4, "Numerical AUC-PRC wins over classical across ALL supported project / K / length-bin cells.", 17)
        style.add_table(results, 0.95, 1.85, 11.45, 1.4,
                        ["Family", "Validation wins", "Test wins", "Test intervals include zero"], [
            [r["family"], f'{r["validation"]["wins"]}/{r["validation"]["supported"]}',
             f'{r["test"]["wins"]}/{r["test"]["supported"]}',
             f'{r["test"]["interval_includes_zero"]}/{r["test"]["supported"]}']
            for r in evidence["balance"]
        ], font_size=17, column_widths=[1.5, 2.8, 2.8, 4.35])
        result_rows = []
        for row in evidence["selected_scores"]:
            model, classical = row["metrics"]["model"], row["metrics"]["classical"]
            low, high = row["uncertainty"]["interval_95"]
            result_rows.append([
                f'{row["project"]} K{row["level"]}\nbin {row["slice"].split(":")[1]}',
                f'{row["split"].title()}\n{row["rows"]}/{row["positives"]}',
                row["family"],
                f'{model["auc_prc"]:.4f}\n/ {classical["auc_prc"]:.4f}',
                f'{row["auc_prc_difference_model_minus_classical"]:+.3f}',
                f'[{low:.3f},\n{high:.3f}]',
                f'{model["accuracy"]:.1%}', f'{model["roc_auc"]:.3f}',
            ])
        style.add_table(results, 0.95, 3.78, 11.45, 2.5,
                        ["Project / K", "Split; n/+", "Model", "Model / class\nAUC-PRC",
                         "Delta", "95% delta\ninterval", "Model\naccuracy", "Model\nROC AUC"],
                        result_rows, font_size=13,
                        column_widths=[1.8, 1.6, 0.8, 1.55, 0.8, 2.1, 1.4, 1.4])
        text(results, 6.66, "n/+ = stories / positives; bin 3 = longest. Delta = model - classical. Paired block intervals, unadjusted; cells overlap.", 12, height=0.35)

        clear(conclusions, "Conclusions - associations, not a single cause")
        style.add_section_card(conclusions, 0.95, 1.6, 5.5, 4.7, "WHAT THE DATA SHOW", style.ORANGE)
        style.add_bullets(conclusions, 1.2, 2.25, 4.95, 3.85, [
            "Length: Hyperledger K5 test prevalence rises 14.2% to 28.7% (bins 1 to 3); Apache is not monotonic.",
            "Empty descriptions: Apache K5 test has 38/500 positives. SLM2 delta -.015 [-.044, .016]: inconclusive.",
            "Repetition/reference flags: zero supported flag-present project/K cells in validation or test.",
        ], size=17)
        style.add_section_card(conclusions, 6.85, 1.6, 5.5, 4.7, "LIMITATIONS / HANDOFF", style.ORANGE)
        style.add_bullets(conclusions, 7.1, 2.25, 4.95, 3.85, [
            "No general SLM length advantage. Favorable and adverse slices both exist.",
            "Temporal shifts differ by project and K; they do not establish why models fail.",
            "Actual edit histories are missing; labels unverified. No test embedding conclusions.",
            "Return findings to MAster SLM; no new training, inference or T6/T7.",
        ], size=17)
        text(conclusions, 6.56, "Support: >=50 stories, >=10 positives and >=10 negatives. All test findings exploratory; full evidence in notes.", 14)

        note_sections = [
            {"run": evidence["run"], "summary": evidence["summary"]},
            {"temporal": evidence["temporal"], "length_profiles": evidence["length_profiles"],
             "prevalence_intervals": evidence["temporal_label_profiles"],
             "note": "Jira K20 train/validation/test: 120/944, 19/314, 41/316; not the K5 trend. Prevalence CIs are in characteristic_profiles.json, not cross-split delta intervals."},
            {"balance": evidence["balance"], "selected_scores": evidence["selected_scores"],
             "selection_note": evidence["selection_note"]},
            {"length_profiles": evidence["length_profiles"], "empty_scores": evidence["empty_scores"],
             "rare_flag_support": evidence["rare_flag_support"], "duplicate_profiles": evidence["duplicate_profiles"]},
        ]
        for number, (slide, notes) in enumerate(
                zip((intro, data_slide, results, conclusions), note_sections), initial_count + 1):
            style.set_slide_number(slide, number)
            if not any(p.placeholder_format.idx == 12 for p in slide.placeholders):
                style.add_textbox(slide, 11.75, 7.08, 0.7, 0.28, str(number),
                                  size=12, color=style.WHITE, align=PP_ALIGN.RIGHT)
            slide.notes_slide.notes_text_frame.text = provenance + json.dumps(notes, indent=2)
        prs.save(staged)
        style.validate(staged, expected_slides=initial_count + 4)
        preserved = Path(temporary) / "preserved.pptx"
        with ZipFile(io.BytesIO(original)) as before, ZipFile(staged) as after, ZipFile(preserved, "w") as merged:
            if after.testzip():
                raise ValueError("Corrupt generated PowerPoint.")
            protected = ("ppt/slides/", "ppt/notesSlides/", "ppt/media/", "ppt/theme/",
                         "ppt/slideLayouts/", "ppt/slideMasters/")
            for name in before.namelist():
                if name.startswith(protected) and before.read(name) != after.read(name):
                    old, new = before.read(name), after.read(name)
                    if name.endswith(".rels"):
                        a, b = ET.fromstring(old), ET.fromstring(new)
                        equivalent = a.tag == b.tag and a.attrib == b.attrib and (
                            sorted(tuple(sorted(r.attrib.items())) for r in a) ==
                            sorted(tuple(sorted(r.attrib.items())) for r in b))
                    elif name.endswith(".xml"):
                        equivalent = ET.canonicalize(old) == ET.canonicalize(new)
                    else:
                        equivalent = False
                    if not equivalent:
                        raise ValueError(f"Existing presentation content changed: {name}")
            # Keep original bytes despite harmless XML declaration/relationship reordering.
            for item in after.infolist():
                if item.filename.startswith(protected) and item.filename in before.namelist():
                    merged.writestr(before.getinfo(item.filename), before.read(item.filename))
                else:
                    merged.writestr(item, after.read(item.filename))
        style.validate(preserved, expected_slides=initial_count + 4)
        with ZipFile(io.BytesIO(original)) as before, ZipFile(preserved) as after:
            if after.testzip() or any(
                before.read(name) != after.read(name)
                for name in before.namelist() if name.startswith(protected)
            ):
                raise ValueError("Original slide parts were not preserved.")
        reopened = Presentation(preserved)
        if [s.slide_id for s in list(reopened.slides)[:initial_count]] != [
                s.slide_id for s in Presentation(io.BytesIO(original)).slides]:
            raise ValueError("Original slide order changed.")
        if args.presentation.read_bytes() != original:
            raise ValueError("Source deck changed concurrently; refusing to overwrite.")
        if output.exists() and not args.in_place:
            raise FileExistsError(output)
        os.replace(preserved, output)
    print(f"Saved {output}: preserved {initial_count} slides; appended four diagnostic slides.")


if __name__ == "__main__":
    main()
