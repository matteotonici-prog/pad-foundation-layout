import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from matplotlib.colors import Normalize
from matplotlib.patches import Rectangle

from comparison import (
    METRICS,
    per_column_tables,
    run_option,
    summarise,
)
from foundation import load_columns_sheet, overlapping_pads

st.set_page_config(page_title="Pad Option Comparison", layout="wide")
st.title("Pad Option Comparison")
st.caption(
    "Runs the same column loads through several pad options (bearing "
    "pressure, thickness, depth, shape) and compares sizes, quantities, "
    "utilisation and pad overlaps."
)

# =====================================================
# SIDEBAR - settings common to all options
# =====================================================
st.sidebar.header("Common settings")

load_increase = st.sidebar.number_input(
    "Additional Load Increase (%)", value=0.0, step=1.0
)
size_step = st.sidebar.number_input(
    "Size Increment (m)", value=0.1, step=0.05, min_value=0.05
)
min_size = st.sidebar.number_input(
    "Minimum Pad Size (m)", value=1.0, step=0.1, min_value=0.3
)
max_size = st.sidebar.number_input(
    "Maximum Pad Size (m)", value=6.0, step=0.5, min_value=1.0
)
concrete_uw = st.sidebar.number_input("Concrete (kN/m3)", value=25.0, step=1.0)
soil_uw = st.sidebar.number_input("Soil above pad (kN/m3)", value=18.0, step=1.0)

st.sidebar.header("Cost index (optional)")
st.sidebar.caption("Placeholder rates - replace with your own.")
rate_concrete = st.sidebar.number_input(
    "Cost per m3 of pad concrete (incl. rebar, formwork)", value=250.0, step=10.0
)
rate_excavation = st.sidebar.number_input(
    "Cost per m3 of excavation", value=40.0, step=5.0
)

settings = dict(
    size_step=size_step,
    min_size=min_size,
    max_size=max_size,
    load_increase_percent=load_increase,
    soil_unit_weight=soil_uw,
    concrete_unit_weight=concrete_uw,
)

# =====================================================
# PAD OPTIONS TABLE
# =====================================================
st.subheader("1. Pad options")
st.caption(
    "Edit the table or add rows. The values below are placeholders - "
    "enter your own allowable bearing pressures and geometry."
)

default_options = pd.DataFrame({
    "Option": ["150 kPa", "200 kPa", "300 kPa"],
    "Allowable pressure (kPa)": [150.0, 200.0, 300.0],
    "Thickness (m)": [0.6, 0.6, 0.6],
    "Founding depth (m)": [1.5, 1.5, 1.5],
    "Aspect ratio (L/B)": [1.0, 1.0, 1.0],
})

options_df = st.data_editor(
    default_options,
    num_rows="dynamic",
    use_container_width=True,
    key="options_editor",
)

options_df = options_df.dropna().reset_index(drop=True)
if options_df.empty:
    st.warning("Add at least one pad option.")
    st.stop()

# make option names unique and non-empty
seen = {}
names = []
for i, n in enumerate(options_df["Option"].astype(str)):
    n = n.strip() or f"Option {i + 1}"
    seen[n] = seen.get(n, 0) + 1
    names.append(n if seen[n] == 1 else f"{n} ({seen[n]})")
options_df["Option"] = names

numeric_cols = [c for c in options_df.columns if c != "Option"]
if (options_df[numeric_cols] <= 0).any().any():
    st.error("All option values must be greater than zero.")
    st.stop()

# =====================================================
# FILE UPLOAD
# =====================================================
st.subheader("2. Column loads")
uploaded_file = st.file_uploader(
    "Upload the same Excel file used in the layout generator (sheet 'Columns')",
    type=["xlsx"],
)

if uploaded_file is None:
    st.info(
        "Expected columns: Column ID, X, Y, Dead Load, Live Load, Wind Load "
        "(Moment X / Moment Y are optional and default to 0)."
    )
    st.stop()

try:
    raw_df = pd.read_excel(uploaded_file, sheet_name="Columns")
except Exception as e:
    st.error(f"Could not read sheet 'Columns': {e}")
    st.stop()

columns_df, err = load_columns_sheet(raw_df)
if err:
    st.error(err)
    st.stop()

# =====================================================
# RUN ALL OPTIONS
# =====================================================
runs = {}
for _, opt in options_df.iterrows():
    results, failed = run_option(opt, columns_df, settings)
    runs[opt["Option"]] = (opt, results, failed)

summary = pd.DataFrame({
    name: summarise(results, failed, rate_concrete, rate_excavation)
    for name, (_opt, results, failed) in runs.items()
})

incomplete = [n for n, (_o, _r, f) in runs.items() if f]
if incomplete:
    with st.expander("Some columns could not be sized (totals exclude them)", expanded=True):
        for n in incomplete:
            _o, _r, f = runs[n]
            st.markdown(f"**{n}**")
            st.dataframe(
                pd.DataFrame(f, columns=["Column ID", "Reason"]),
                hide_index=True,
                use_container_width=True,
            )

# =====================================================
# SUMMARY TABLE
# =====================================================
st.subheader("3. Comparison summary")
st.caption("Green = best value in that row.")

text_table = summary.copy().astype(object)
for metric, (fmt, _best) in METRICS.items():
    text_table.loc[metric] = summary.loc[metric].map(lambda v, f=fmt: f.format(v))


def highlight_best(_):
    css = pd.DataFrame("", index=summary.index, columns=summary.columns)
    for metric, (_fmt, best) in METRICS.items():
        row = summary.loc[metric]
        if row.max() == row.min():
            continue
        target = row.min() if best == "low" else row.max()
        css.loc[metric, row[row == target].index] = (
            "background-color:#d4edda;color:#155724;font-weight:600"
        )
    return css


st.dataframe(
    text_table.style.apply(highlight_best, axis=None),
    use_container_width=True,
    height=36 * (len(METRICS) + 1),
)

# =====================================================
# CHARTS
# =====================================================
st.subheader("4. Charts")
c1, c2, c3 = st.columns(3)
with c1:
    st.markdown("**Total footprint area (m²)**")
    st.bar_chart(summary.loc["Total footprint area (m²)"])
with c2:
    st.markdown("**Concrete volume (m³)**")
    st.bar_chart(summary.loc["Concrete volume (m³)"])
with c3:
    st.markdown("**Relative cost index**")
    st.bar_chart(summary.loc["Relative cost index"])

st.markdown("**How many pads fall in each size band (largest dimension)**")
bins = [0, 1.5, 2.0, 2.5, 3.0, 4.0, 100.0]
labels = ["<=1.5 m", "1.5-2 m", "2-2.5 m", "2.5-3 m", "3-4 m", ">4 m"]
dist = pd.DataFrame({
    name: pd.cut(
        pd.Series([max(f["B"], f["L"]) for f in results], dtype=float),
        bins=bins, labels=labels, right=True,
    ).value_counts().reindex(labels)
    for name, (_o, results, _f) in runs.items()
}).fillna(0)
dist.index.name = "Largest pad dimension"
st.bar_chart(dist)

# =====================================================
# PER-COLUMN TABLES
# =====================================================
st.subheader("5. Column by column")
sizes_tbl, util_tbl, gov_tbl = per_column_tables(runs, columns_df)
tab_sizes, tab_util, tab_gov = st.tabs(
    ["Pad size (B x L, m)", "Max bearing utilisation (%)", "Governing case"]
)
with tab_sizes:
    st.dataframe(sizes_tbl, use_container_width=True)
with tab_util:
    st.caption("Maximum corner pressure / allowable pressure.")
    st.dataframe(
        util_tbl.style
        .background_gradient(cmap="RdYlGn_r", vmin=30, vmax=100, axis=None)
        .format("{:.0f}"),
        use_container_width=True,
    )
with tab_gov:
    st.caption(
        "'Moment' = the pad had to be made bigger than the vertical load "
        "alone requires."
    )
    st.dataframe(gov_tbl, use_container_width=True)

# =====================================================
# PLAN VIEW
# =====================================================
st.subheader("6. Plan view by option")
chosen = st.selectbox("Option", list(runs.keys()))
opt, results, failed = runs[chosen]

if not results:
    st.info("No columns could be sized for this option.")
else:
    overlaps = overlapping_pads(results)
    in_overlap = {c for pair in overlaps for c in pair}
    norm = Normalize(vmin=0.3, vmax=1.0)
    cmap = plt.get_cmap("RdYlGn_r")

    fig, ax = plt.subplots(figsize=(11, 8))
    for f in results:
        x0, y0, x1, y1 = f["Bbox"]
        clash = f["Column ID"] in in_overlap
        ax.add_patch(Rectangle(
            (x0, y0), x1 - x0, y1 - y0,
            facecolor=cmap(norm(f["Utilisation"])), alpha=0.75,
            edgecolor="red" if clash else "black",
            linewidth=2.0 if clash else 0.8,
        ))
        ax.plot(f["X"], f["Y"], marker="s", color="black", markersize=4)
        ax.text(f["X"], y1, f["Column ID"], ha="center", va="bottom", fontsize=7)
        ax.text(f["X"], y0, f"{f['B']:.1f}x{f['L']:.1f}",
                ha="center", va="top", fontsize=6)
    ax.autoscale_view()
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)
    ax.set_title(
        f"{chosen}: bearing utilisation (red outline = overlaps a neighbour)"
    )
    fig.colorbar(
        plt.cm.ScalarMappable(norm=norm, cmap=cmap), ax=ax,
        label="Max pressure / allowable", shrink=0.8,
    )
    st.pyplot(fig)

    if overlaps:
        st.warning(
            "Overlapping pads (consider combined or strap footings): "
            + ", ".join(f"{a}-{b}" for a, b in overlaps[:20])
            + (" ..." if len(overlaps) > 20 else "")
        )

# =====================================================
# DOWNLOADS
# =====================================================
st.subheader("7. Export")
d1, d2 = st.columns(2)
with d1:
    st.download_button(
        "Download comparison summary (CSV)",
        summary.round(2).to_csv().encode("utf-8"),
        file_name="pad_option_comparison.csv",
        mime="text/csv",
    )
with d2:
    st.download_button(
        "Download pad sizes per column (CSV)",
        sizes_tbl.to_csv().encode("utf-8"),
        file_name="pad_sizes_per_column_by_option.csv",
        mime="text/csv",
    )

with st.expander("Assumptions"):
    st.markdown(
        "- Uses `design_pad()` from `foundation.py`: service load = dead + live "
        "+ wind (plus the % increase), no load combinations.\n"
        "- Allowable pressure is **gross** at founding level; pad self weight "
        "and soil above the pad are added to the load.\n"
        "- Pads are concentric with the column, sized in steps of the size "
        "increment, with full contact (min corner pressure >= 0).\n"
        "- Excavation volume = pad footprint x founding depth (no working space "
        "or side slopes).\n"
        "- Overlap checks compare pad rectangles in plan.\n"
        "- Bearing pressure only: punching shear, bending and settlement are "
        "not checked.\n"
        "- Cost index is only a relative indicator from the rates in the sidebar."
    )
