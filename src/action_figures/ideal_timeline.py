"""Ideal (reference) production timeline for an action figure batch.

Static reference durations, in weeks, for the dashboard's "Ideal production
timeline" chart (issue #8). Every row is distilled from a verified lead-time
figure in ``reports/benchmarks/<source_file>`` and cites the on-page source
URL. This module is pure data + one CSV writer; it does not read any real
data file and knows nothing about the dashboard builder.

Per-stage derivation (scenario: one mid-complexity articulated figure,
3–5k unit batch, China factories):

- design_prototyping 1–3: 3D-print sample loop 7–10 days (simple) to
  10–15 days (complex multi-color) per revision round (Demeng prototypes
  guide); bare print floor ~5 working days (EDN Toy).
- tooling_molds/steel 5–7: production tooling ~4–10+ weeks (UTT Mould);
  steel to first sample 20–45 days (Haizol / My-Prototyping, same report).
- tooling_molds/aluminum 1–3: aluminum T1 samples 7–14 days (RapidAPlus);
  Formlabs classes aluminum mold-making at 3–4 weeks, hence the 3-week cap.
- injection_molding 1–2: mass-production run 6–10 days after approval
  (Haizol lead-time table, quoted in tooling_molds.md §6).
- textile_accessories 2–3: bulk figure-garment production typically 2–4
  weeks with 7-day sampling (Sanchuan Apparel); labels/webbing ~1–2 weeks
  (textile report §5). Runs in parallel with molding.
- painting_printing 1–2: spray-line throughput 200–500 finished pcs/day
  (Demeng spray painting) → a 3–5k batch paints in ~1–2 weeks.
- assembly_processing 1–2: gated by upstream batches, not line speed
  (~15 worker-min/toy at OEM scale, China Labor Watch); outsourced
  handwork lots land within ~10 days (EDNTOY, assembly report §5).
- packaging 1–2: printed boxes 10–20 days after proof approval (Qin
  Printing); blister mold lead 2–7 days (GoalPackaging, same report).
- qc_testing 1–2: EN 71 parts 1–3 report 7 working days after
  samples/payment (jjrlab); AQL man-day ~12 h end-to-end (AQI Service).
- logistics_freight 1–2: export air 3–7 days / express courier 1–5 days
  (ExFreight); domestic line-haul 2–5 days door-to-door (163.com guide).
  Sea freight (12–40 days port-to-port) is out of the ideal band and
  deliberately excluded from this reference.

All benchmark URLs were verified on-page on 2026-09-05 (see each report's
verification log). Durations are reference envelopes, not quotes.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TimelineStage:
    """One reference bar of the ideal production timeline.

    variant distinguishes mutually exclusive alternatives of the same stage
    (e.g. steel vs aluminum tooling); empty for single-variant stages.
    parallel_group groups stages that share one time window ("main" is the
    serial chain; any other value marks an overlap window).
    """

    stage_id: str
    min_weeks: int
    max_weeks: int
    parallel_group: str
    source_file: str
    source_url: str
    variant: str = ""


# Production order: design → tooling → [molding ‖ textile] → painting →
# assembly → packaging → QC → logistics.
IDEAL_TIMELINE: tuple[TimelineStage, ...] = (
    TimelineStage(
        stage_id="design_prototyping",
        min_weeks=1,
        max_weeks=3,
        parallel_group="main",
        source_file="design_prototyping.md",
        source_url="https://www.demengtoy.com/how-to-custom-collectible-toy-prototypes.html",
    ),
    TimelineStage(
        stage_id="tooling_molds",
        variant="steel",
        min_weeks=5,
        max_weeks=7,
        parallel_group="main",
        source_file="tooling_molds.md",
        source_url=(
            "https://www.uttmould.com/news/"
            "injection-mold-manufacturing-china-cost-lead-time-dfm-quality-guide.html"
        ),
    ),
    TimelineStage(
        stage_id="tooling_molds",
        variant="aluminum",
        min_weeks=1,
        max_weeks=3,
        parallel_group="main",
        source_file="tooling_molds.md",
        source_url="https://rapidaplus.com/aluminum-rapid-tooling/",
    ),
    TimelineStage(
        stage_id="injection_molding",
        min_weeks=1,
        max_weeks=2,
        parallel_group="molding_window",
        source_file="tooling_molds.md",
        source_url="https://www.haizol.com/blog/injection-molding-china-faq",
    ),
    TimelineStage(
        stage_id="textile_accessories",
        min_weeks=2,
        max_weeks=3,
        parallel_group="molding_window",
        source_file="textile_accessories.md",
        source_url="https://sanchuanapparel.com/blog/clothing-manufacturing-cost-china-2026",
    ),
    TimelineStage(
        stage_id="painting_printing",
        min_weeks=1,
        max_weeks=2,
        parallel_group="main",
        source_file="painting_printing.md",
        source_url="https://www.demengtoy.com/spray-painting.html",
    ),
    TimelineStage(
        stage_id="assembly_processing",
        min_weeks=1,
        max_weeks=2,
        parallel_group="main",
        source_file="assembly_processing.md",
        source_url=(
            "https://chinalaborwatch.org/"
            "labubu-unboxed-the-labor-behind-the-global-toy-phenomenon/"
        ),
    ),
    TimelineStage(
        stage_id="packaging",
        min_weeks=1,
        max_weeks=2,
        parallel_group="main",
        source_file="packaging.md",
        source_url="https://www.qinprinting.com/custom-toy-packaging/",
    ),
    TimelineStage(
        stage_id="qc_testing",
        min_weeks=1,
        max_weeks=2,
        parallel_group="main",
        source_file="qc_testing.md",
        source_url="https://www.jjrlab.com/news/how-much-does-an-en-71-test-report-cost.html",
    ),
    TimelineStage(
        stage_id="logistics_freight",
        min_weeks=1,
        max_weeks=2,
        parallel_group="main",
        source_file="logistics_freight.md",
        source_url="https://www.exfreight.com/shipping-from-china-to-usa/",
    ),
)

CSV_FIELDS = (
    "stage_id",
    "variant",
    "min_weeks",
    "max_weeks",
    "parallel_group",
    "source_file",
    "source_url",
)


def write_csv(path: Path) -> Path:
    """Export the timeline as CSV (parent dirs created); returns the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(CSV_FIELDS))
        writer.writeheader()
        for stage in IDEAL_TIMELINE:
            writer.writerow({field: getattr(stage, field) for field in CSV_FIELDS})
    return path
