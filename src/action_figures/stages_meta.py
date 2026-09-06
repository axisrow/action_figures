"""Stage metadata for the Process Explorer pages (GH#5).

Canonical production order of the cost stages — design first, logistics last —
with English labels and 1–2-sentence plain-English descriptions distilled from
reports/audit/audit.md and reports/benchmarks/*.md. The two service buckets
(admin_other, unclassified) close the list with order 11 and 12.

zh_keys are not hardcoded here: stages_metadata() pulls the current Chinese
keywords from config/taxonomy.yaml, so the menu always matches the classifier.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pandas as pd

STAGE_ORDER = [
    "design_prototyping",
    "tooling_molds",
    "raw_materials",
    "injection_molding",
    "painting_printing",
    "textile_accessories",
    "assembly_processing",
    "packaging",
    "qc_testing",
    "logistics_freight",
    # service buckets
    "admin_other",
    "unclassified",
]

STAGE_LABELS_EN = {
    "design_prototyping": "Design & Prototyping",
    "tooling_molds": "Tooling & Molds",
    "raw_materials": "Raw Materials",
    "injection_molding": "Injection Molding",
    "painting_printing": "Painting & Printing",
    "textile_accessories": "Textiles & Accessories",
    "assembly_processing": "Assembly & Handwork",
    "packaging": "Packaging",
    "qc_testing": "QC & Testing",
    "logistics_freight": "Logistics & Freight",
    "admin_other": "Admin & Other",
    "unclassified": "Unclassified",
}

# What the stage is and why it costs money (for a non-expert reader).
STAGE_DESCRIPTIONS_EN = {
    "design_prototyping": (
        "Design and prototyping: artists draw and sculpt every part digitally, "
        "then sample parts are 3D printed and revised until approved. It is paid "
        "per model before any production can start, so it does not get cheaper "
        "with bigger orders."
    ),
    "tooling_molds": (
        "Tooling and molds: steel, aluminum or resin molds are made before any "
        "plastic part can be mass-produced. The project's largest one-off "
        "investment — many small cheap molds instead of a few expensive ones, "
        "typical for small-batch production."
    ),
    "raw_materials": (
        "Raw materials and consumables: plastic compound, paint, glue, thinner, "
        "screws, magnets and other workshop supplies consumed by production and "
        "assembly."
    ),
    "injection_molding": (
        "Molded parts production: factory runs that inject, cast or rotocast "
        "plastic parts — soles, buckles, weapons, helmets — from the molds. Paid "
        "per part, so it scales with the size of the production run."
    ),
    "painting_printing": (
        "Painting and printing: spray-painted parts, hand-painted head sculpts, "
        "fabric printing, decals and plating. Very labor-intensive, which makes "
        "it a major per-unit cost for collectible figures."
    ),
    "textile_accessories": (
        "Textiles and garment accessories: fabric, leather, thread, zippers, "
        "buttons and woven labels for the figures' outfits. Tailoring is the "
        "backbone of cost for clothed 1/6 scale figures."
    ),
    "assembly_processing": (
        "Assembly and handwork: cutting fabric, sewing garments, trimming "
        "threads, turning metal parts and gluing everything into the finished "
        "figure. Mostly manual labor paid per unit or per operation."
    ),
    "packaging": (
        "Packaging: boxes, cartons, blister trays and manuals. Almost absent in "
        "this project — figures ship as collectibles without retail boxes."
    ),
    "qc_testing": (
        "Quality control and testing: product inspections and laboratory safety "
        "tests. Billed per report or per inspection day, so it costs relatively "
        "more on small production runs."
    ),
    "logistics_freight": (
        "Logistics and freight: courier and shipping fees for samples, parts and "
        "materials moving between the studio and outsourcing partners. Many "
        "small shipments — each cheap, but very frequent."
    ),
    "admin_other": (
        "Admin and office overhead: business trips, fuel, tolls, office "
        "equipment and meals — everything not part of physically making the "
        "figures."
    ),
    "unclassified": (
        "Lines the taxonomy could not classify with confidence; reviewed "
        "manually in unclassified.csv."
    ),
}


def stages_metadata(taxonomy: Mapping[str, Sequence[str]]) -> pd.DataFrame:
    """Build the stages.csv frame.

    Columns: stage_id, order (1-12), label_en, description_en, zh_keys
    (';'-joined taxonomy keywords; the `unclassified` fallback has none).
    """
    missing = set(taxonomy) - set(STAGE_ORDER)
    if missing:
        raise ValueError(f"taxonomy stages missing from STAGE_ORDER: {sorted(missing)}")
    rows = [
        {
            "stage_id": stage,
            "order": order,
            "label_en": STAGE_LABELS_EN[stage],
            "description_en": STAGE_DESCRIPTIONS_EN[stage],
            "zh_keys": ";".join(taxonomy.get(stage, ())),
        }
        for order, stage in enumerate(STAGE_ORDER, start=1)
    ]
    return pd.DataFrame(rows)
