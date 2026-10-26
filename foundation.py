import itertools
import math

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle

# ====================================================
# INPUT SHEET
# ====================================================
REQUIRED_COLUMNS = [
    "Column ID", "X", "Y", "Dead Load", "Live Load", "Wind Load"
]
OPTIONAL_COLUMNS = ["Moment X", "Moment Y"]  # filled with 0 if missing


def load_columns_sheet(df):
    """Validate / clean the 'Columns' sheet. Returns (clean_df, error_message)."""
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return None, (
            "Missing column(s) in 'Columns' sheet: " + ", ".join(missing)
        )
    df = df.copy()
    for c in OPTIONAL_COLUMNS:
        if c not in df.columns:
            df[c] = 0.0
    num_cols = ["X", "Y", "Dead Load", "Live Load", "Wind Load"] + OPTIONAL_COLUMNS
    df[num_cols] = (
        df[num_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    )
    df["Column ID"] = df["Column ID"].astype(str)
    return df, None


# ====================================================
# HELPERS
# ====================================================
def _round_up(value, step):
    """Round value up to the next multiple of step."""
    return round(math.ceil(value / step - 1e-9) * step, 6)


# ====================================================
# BEARING PRESSURES UNDER A RECTANGULAR PAD
# ====================================================
def pad_pressures(service_load, mx, my, B, L, overburden):
    """
    Pressures under a rectangular pad B (along X) x L (along Y),
    column concentric with the pad.

    service_load : column vertical load (kN)
    mx, my       : moments (kNm). Same convention as the pile layout tool:
                   Moment X varies the pressure along Y,
                   Moment Y varies the pressure along X.
    overburden   : pad self weight + soil above pad, as a pressure (kPa)

    Returns total load (kN), average pressure, and the four corner pressures
    as (sign_x, sign_y, pressure).
    """
    area = B * L
    total = service_load + overburden * area
    q_avg = total / area

    kx = 6.0 * my / (B * B * L)   # pressure change at the edge from Moment Y
    ky = 6.0 * mx / (B * L * L)   # pressure change at the edge from Moment X

    corners = [
        (sx, sy, q_avg + sx * kx + sy * ky)
        for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))
    ]
    return total, q_avg, corners


# ====================================================
# PAD DESIGN
# ====================================================
def design_pad(
    row,
    allowable_pressure,
    thickness,
    founding_depth,
    aspect_ratio=1.0,
    size_step=0.1,
    min_size=1.0,
    max_size=6.0,
    load_increase_percent=0.0,
    soil_unit_weight=18.0,
    concrete_unit_weight=25.0,
):
    """
    Size a pad from the allowable (gross) bearing pressure.

    1. Size from the vertical load: area >= load / (q_allow - overburden)
    2. Increase the pad until, with the moments, the maximum corner pressure
       is <= q_allow and the minimum is >= 0 (full contact).

    Raises ValueError if the pad cannot be sized.
    """
    service_load = (
        float(row["Dead Load"])
        + float(row["Live Load"])
        + float(row["Wind Load"])
    ) * (1.0 + load_increase_percent / 100.0)

    mx = float(row["Moment X"])
    my = float(row["Moment Y"])

    if service_load <= 0:
        raise ValueError("Net vertical load is zero or negative (uplift)")

    cover = max(founding_depth - thickness, 0.0)
    overburden = thickness * concrete_unit_weight + cover * soil_unit_weight
    available = allowable_pressure - overburden
    if available <= 0:
        raise ValueError(
            "Allowable pressure is not enough to carry the pad and soil "
            "above it (reduce thickness / depth)"
        )

    min_L = _round_up(min_size, size_step)

    def dims(B):
        return B, max(_round_up(B * aspect_ratio, size_step), min_L)

    area_required = service_load / available
    B = _round_up(max(math.sqrt(area_required / aspect_ratio), min_size), size_step)

    B_vertical = None
    while True:
        B, L = dims(B)
        if B > max_size + 1e-9 or L > max_size + 1e-9:
            raise ValueError(f"Pad larger than {max_size:.1f} m needed")

        total, q_avg, corners = pad_pressures(
            service_load, mx, my, B, L, overburden
        )
        pressures = [c[2] for c in corners]
        q_max, q_min = max(pressures), min(pressures)

        if q_avg <= allowable_pressure + 1e-9:
            if B_vertical is None:
                B_vertical = B
            if q_max <= allowable_pressure + 1e-9 and q_min >= -1e-9:
                break
        B = round(B + size_step, 6)

    governed_by = "Moment" if B > B_vertical + 1e-9 else "Vertical load"
    area = B * L

    return {
        "Column ID": row["Column ID"],
        "X": float(row["X"]),
        "Y": float(row["Y"]),
        "B": B,
        "L": L,
        "Area": area,
        "Thickness": thickness,
        "Service Load": service_load,
        "Total Load": total,
        "Avg Pressure": q_avg,
        "Max Pressure": q_max,
        "Min Pressure": q_min,
        "Utilisation": q_max / allowable_pressure,
        "Corners": [
            (sx * B / 2.0, sy * L / 2.0, q) for sx, sy, q in corners
        ],
        "Governed By": governed_by,
        "Concrete Volume": area * thickness,
        "Excavation Volume": area * max(founding_depth, thickness),
        "Bbox": (
            float(row["X"]) - B / 2.0,
            float(row["Y"]) - L / 2.0,
            float(row["X"]) + B / 2.0,
            float(row["Y"]) + L / 2.0,
        ),
    }


# ====================================================
# OVERLAP CHECK
# ====================================================
def overlapping_pads(results, tol=1e-9):
    """Pairs of columns whose pads overlap in plan."""
    pairs = []
    for a, b in itertools.combinations(results, 2):
        ax0, ay0, ax1, ay1 = a["Bbox"]
        bx0, by0, bx1, by1 = b["Bbox"]
        if (
            min(ax1, bx1) - max(ax0, bx0) > tol
            and min(ay1, by1) - max(ay0, by0) > tol
        ):
            pairs.append((a["Column ID"], b["Column ID"]))
    return pairs


# ====================================================
# INDIVIDUAL PAD PLOT
# ====================================================
def plot_pad(foundation):
    B, L = foundation["B"], foundation["L"]
    fig, ax = plt.subplots(figsize=(6, 6))

    ax.add_patch(
        Rectangle(
            (-B / 2, -L / 2), B, L,
            facecolor="lightsteelblue", edgecolor="steelblue", linewidth=2
        )
    )
    ax.plot(0, 0, marker="s", color="red", markersize=12)

    for x, y, q in foundation["Corners"]:
        ax.text(
            x, y, f"{q:.0f} kPa",
            ha="right" if x > 0 else "left",
            va="top" if y > 0 else "bottom",
            fontsize=9,
        )

    margin = 0.15 * max(B, L)
    ax.set_xlim(-B / 2 - margin, B / 2 + margin)
    ax.set_ylim(-L / 2 - margin, L / 2 + margin)
    ax.set_aspect("equal")
    ax.grid(True)
    ax.set_xlabel("m")
    ax.set_ylabel("m")
    ax.set_title(f"{foundation['Column ID']}:  {B:.1f} x {L:.1f} m")
    return fig


# ====================================================
# BUILDING PLAN
# ====================================================
def plot_building_plan(results):
    overlaps = overlapping_pads(results)
    in_overlap = {c for pair in overlaps for c in pair}

    fig, ax = plt.subplots(figsize=(10, 8))

    for f in results:
        x0, y0, x1, y1 = f["Bbox"]
        clash = f["Column ID"] in in_overlap
        ax.add_patch(
            Rectangle(
                (x0, y0), x1 - x0, y1 - y0,
                facecolor="lightsteelblue", alpha=0.6,
                edgecolor="red" if clash else "steelblue",
                linewidth=2.0 if clash else 1.0,
            )
        )
        ax.plot(f["X"], f["Y"], marker="s", color="red", markersize=4)
        ax.text(
            f["X"], y1, f["Column ID"],
            ha="center", va="bottom", fontsize=8
        )
        ax.text(
            f["X"], y0, f"{f['B']:.1f}x{f['L']:.1f}",
            ha="center", va="top", fontsize=7
        )

    ax.autoscale_view()
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)
    ax.set_title("Pad Foundation Layout Plan (red outline = overlaps a neighbour)")
    return fig
