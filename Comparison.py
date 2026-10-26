"""
Pad option comparison - core logic (no Streamlit imports).

Runs design_pad() from foundation.py once per option and collects
comparison metrics.

Units: kN, kNm, kPa, metres.
"""

import numpy as np
import pandas as pd

from foundation import design_pad, overlapping_pads

# metric name -> (number format, "low" / "high" = which value is best)
METRICS = {
    "Total footprint area (m²)": ("{:,.1f}", "low"),
    "Avg pad area (m²)": ("{:,.2f}", "low"),
    "Largest pad dimension (m)": ("{:,.1f}", "low"),
    "Concrete volume (m³)": ("{:,.1f}", "low"),
    "Excavation volume (m³)": ("{:,.1f}", "low"),
    "Avg bearing utilisation (%)": ("{:,.1f}", "high"),
    "Max bearing utilisation (%)": ("{:,.1f}", "low"),
    "Pads governed by moment": ("{:,.0f}", "low"),
    "Overlapping pad pairs": ("{:,.0f}", "low"),
    "Columns not sized": ("{:,.0f}", "low"),
    "Relative cost index": ("{:,.0f}", "low"),
}


def run_option(opt, columns_df, settings):
    """
    Design every column for one pad option.

    opt: dict-like with Allowable pressure (kPa), Thickness (m),
         Founding depth (m), Aspect ratio (L/B)
    settings: dict with size_step, min_size, max_size, load_increase_percent,
              soil_unit_weight, concrete_unit_weight
    Returns (results, failed) where failed is a list of (column id, reason).
    """
    results, failed = [], []
    for _, row in columns_df.iterrows():
        try:
            results.append(
                design_pad(
                    row=row,
                    allowable_pressure=float(opt["Allowable pressure (kPa)"]),
                    thickness=float(opt["Thickness (m)"]),
                    founding_depth=float(opt["Founding depth (m)"]),
                    aspect_ratio=float(opt["Aspect ratio (L/B)"]),
                    **settings,
                )
            )
        except ValueError as e:
            failed.append((str(row["Column ID"]), str(e)))
    return results, failed


def summarise(results, failed, rate_concrete=0.0, rate_excavation=0.0):
    """One column of the comparison table."""
    n = len(results)
    util = np.array([f["Utilisation"] for f in results]) if results else np.array([0.0])
    concrete = sum(f["Concrete Volume"] for f in results)
    excavation = sum(f["Excavation Volume"] for f in results)
    total_area = sum(f["Area"] for f in results)

    return {
        "Total footprint area (m²)": total_area,
        "Avg pad area (m²)": total_area / n if n else 0.0,
        "Largest pad dimension (m)": max(
            (max(f["B"], f["L"]) for f in results), default=0.0
        ),
        "Concrete volume (m³)": concrete,
        "Excavation volume (m³)": excavation,
        "Avg bearing utilisation (%)": float(util.mean()) * 100.0,
        "Max bearing utilisation (%)": float(util.max()) * 100.0,
        "Pads governed by moment": sum(
            1 for f in results if f["Governed By"] == "Moment"
        ),
        "Overlapping pad pairs": len(overlapping_pads(results)),
        "Columns not sized": len(failed),
        "Relative cost index": concrete * rate_concrete + excavation * rate_excavation,
    }


def per_column_tables(runs, columns_df):
    """
    Pad size, bearing utilisation and governing case per column,
    one column per option.
    runs: {option_name: (opt, results, failed)}
    """
    base = columns_df[["Column ID", "X", "Y"]].copy()
    base["Service load (kN)"] = (
        columns_df["Dead Load"] + columns_df["Live Load"] + columns_df["Wind Load"]
    )
    sizes = base.set_index("Column ID")
    util = base.set_index("Column ID")[[]].copy()
    governing = base.set_index("Column ID")[[]].copy()

    for name, (_opt, results, _failed) in runs.items():
        sizes[name] = pd.Series(
            {f["Column ID"]: f"{f['B']:.1f} x {f['L']:.1f}" for f in results}
        )
        util[name] = pd.Series(
            {f["Column ID"]: f["Utilisation"] * 100.0 for f in results}
        )
        governing[name] = pd.Series(
            {f["Column ID"]: f["Governed By"] for f in results}
        )
    return sizes, util, governing
