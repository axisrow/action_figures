"""Golden classification cases for action_figures cost line items.

All strings below are either synthetic or generic vocabulary commonly used in
Chinese reimbursement sheets — no real financial rows are reproduced here.
"""

from pathlib import Path

import pandas as pd
import pytest

from action_figures.classify import (
    REPO_CONFIG_TAXONOMY,
    classify_df,
    classify_text,
    load_taxonomy,
)

TAX = load_taxonomy(REPO_CONFIG_TAXONOMY)


# --- single-string golden cases -----------------------------------------
# (item, purpose, supplier, remarks, expected_stage)
GOLDEN_CASES = [
    # logistics / freight
    ("运费寄付", "", "星辰快运", "", "logistics_freight"),
    ("运费到付", "", "", "", "logistics_freight"),
    ("寄件费用", "", "云雁快递", "", "logistics_freight"),
    ("模具运费", "", "", "", "logistics_freight"),  # freight beats tooling
    # design & prototyping
    ("外发画图", "", "", "", "design_prototyping"),
    ("做样办", "", "", "", "design_prototyping"),
    ("3D打印材料", "", "", "", "design_prototyping"),
    ("打印费", "", "", "", "design_prototyping"),
    # tooling / molds
    ("搪胶模费", "", "搪胶", "", "tooling_molds"),
    ("开模定金", "", "", "", "tooling_molds"),
    ("线割冲模具", "", "", "", "tooling_molds"),
    ("压铸开模", "", "", "", "tooling_molds"),
    ("样例塑胶模定金", "", "", "", "tooling_molds"),  # 塑胶模 beats raw 材料 (GH#39)
    # injection molding / cast parts
    ("鞋底啤货", "", "", "", "injection_molding"),
    ("注塑加工", "", "", "", "injection_molding"),
    ("压铸件", "", "", "", "injection_molding"),
    # painting & printing
    ("喷油费用", "", "", "", "painting_printing"),
    ("头雕上色", "", "", "", "painting_printing"),
    ("数码印花货款", "", "", "", "painting_printing"),
    ("定制水贴", "", "", "", "painting_printing"),
    # assembly / handwork / processing
    ("外发手工费", "", "外发", "", "assembly_processing"),
    ("切割费", "", "", "", "assembly_processing"),
    ("外发剪线手工费", "", "", "", "assembly_processing"),
    ("车件", "", "", "", "assembly_processing"),
    ("折弯", "", "", "", "assembly_processing"),
    # raw materials & consumables
    ("买螺丝", "", "", "", "raw_materials"),
    ("买酒精", "", "网市商城", "", "raw_materials"),
    ("颜料", "", "", "", "raw_materials"),
    ("买焊锡丝", "", "", "", "raw_materials"),
    # textile & garment accessories
    ("买大货布", "", "", "", "textile_accessories"),
    ("买线", "", "线行", "", "textile_accessories"),
    ("织唛货款", "", "", "", "textile_accessories"),
    ("买羊皮", "", "", "", "textile_accessories"),
    ("买拉链", "", "", "", "textile_accessories"),
    # packaging
    ("封箱用", "", "", "", "packaging"),
    ("买彩盒", "", "", "", "packaging"),
    ("买纸箱", "", "", "", "packaging"),
    # qc / testing
    ("检测费", "", "", "", "qc_testing"),
    # admin / other known overhead
    ("出差油费", "", "", "", "admin_other"),
    ("高速费", "", "", "", "admin_other"),
    ("办公室空调", "", "", "", "admin_other"),
    # empty values
    ("", "", "", "", "unclassified"),
    (None, "", "", "", "unclassified"),
]


@pytest.mark.parametrize("item,purpose,supplier,remarks,expected", GOLDEN_CASES)
def test_golden_single_lines(item, purpose, supplier, remarks, expected):
    stage, confidence = classify_text(item, purpose, supplier, remarks, TAX)
    assert stage == expected, f"item={item!r} -> {stage!r}, want {expected!r}"
    if expected == "unclassified":
        assert confidence == 0.0
    else:
        assert 0.0 < confidence <= 1.0


def test_priority_first_stage_wins():
    """A text hitting two stages must resolve by taxonomy order, not hash luck."""
    # 画图 (design) + 模 (tooling) in one string: design is checked first.
    stage, _ = classify_text("头雕画图尾款", "", "", "", TAX)
    assert stage == "design_prototyping"


def test_purpose_and_supplier_are_searched():
    """Match must also come from purpose / supplier fields, not only item."""
    stage, _ = classify_text("货款", "", "云雁快递", "", TAX)
    assert stage == "logistics_freight"
    stage, _ = classify_text("货款", "喷漆车间用", "", "", TAX)
    assert stage == "painting_printing"


def test_classify_df_adds_columns():
    df = pd.DataFrame(
        {
            "line_id": ["L1", "L2", "L3"],
            "item": ["运费寄付", "喷油费用", ""],
            "purpose": ["", "", ""],
            "supplier": ["", "", ""],
            "remarks": ["", "", ""],
            "amount": [10.0, 20.0, 30.0],
        }
    )
    out = classify_df(df, TAX)
    assert "stage" in out.columns and "stage_confidence" in out.columns
    assert out["stage"].tolist() == ["logistics_freight", "painting_printing", "unclassified"]
    # input frame is not mutated (pure function)
    assert "stage" not in df.columns


def test_load_taxonomy_stage_order():
    """Taxonomy must load as an ordered mapping with non-empty keyword lists."""
    assert len(TAX) >= 10
    assert list(TAX)[0] == "logistics_freight"
    for stage, keywords in TAX.items():
        assert isinstance(keywords, list) and keywords, f"stage {stage} has no keywords"


def test_taxonomy_yaml_exists_in_config():
    assert Path(REPO_CONFIG_TAXONOMY).exists()
