import pandas as pd
import streamlit as st

from foundation import (
    design_pad,
    load_columns_sheet,
    overlapping_pads,
    plot_building_plan,
    plot_pad,
)

# =====================================================
# PAGE SETTINGS
# =====================================================
st.set_page_config(
    page_title="Pad Foundation Layout Generator",
    layout="wide"
)

st.title("Pad Foundation Layout Generator")

# =====================================================
# SIDEBAR
# =====================================================
st.sidebar.header("Pad Design Parameters")

allowable_pressure = st.sidebar.number_input(
    "Allowable Bearing Pressure (kPa)",
    value=200.0,
    step=10.0,
    min_value=10.0,
    help="Treated as a gross pressure at founding level: pad self weight "
         "and soil above the pad are deducted automatically."
)

thickness = st.sidebar.number_input(
    "Pad Thickness (m)", value=0.6, step=0.05, min_value=0.2
)

founding_depth = st.sidebar.number_input(
    "Founding Depth (m)",
    value=1.5,
    step=0.1,
    min_value=0.2,
    help="Ground level to underside of pad."
)

aspect_ratio = st.sidebar.number_input(
    "Pad Aspect Ratio (L / B)",
    value=1.0,
    step=0.1,
    min_value=0.5,
    help="1.0 = square. B is along X, L is along Y."
)

load_increase_percent = st.sidebar.number_input(
    "Additional Load Increase (%)", value=0.0, step=1.0
)

st.sidebar.subheader("Size limits")
size_step = st.sidebar.number_input(
    "Size Increment (m)", value=0.1, step=0.05, min_value=0.05
)
min_size = st.sidebar.number_input(
    "Minimum Pad Size (m)", value=1.0, step=0.1, min_value=0.3
)
max_size = st.sidebar.number_input(
    "Maximum Pad Size (m)", value=6.0, step=0.5, min_value=1.0
)

st.sidebar.subheader("Unit weights")
concrete_uw = st.sidebar.number_input(
    "Concrete (kN/m3)", value=25.0, step=1.0
)
soil_uw = st.sidebar.number_input(
    "Soil above pad (kN/m3)", value=18.0, step=1.0
)

# =====================================================
# FILE UPLOAD
# =====================================================
uploaded_file = st.file_uploader(
    "Upload Excel File",
    type=["xlsx"]
)

if uploaded_file is None:
    st.info(
        "Upload an Excel file with a sheet named 'Columns' and the columns: "
        "Column ID, X, Y, Dead Load, Live Load, Wind Load "
        "(Moment X and Moment Y are optional)."
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
# PARAMETERS TABLE
# =====================================================
st.subheader("Pad Parameters")

parameters_df = pd.DataFrame({
    "Parameter": [
        "Allowable Bearing Pressure",
        "Pad Thickness",
        "Founding Depth",
        "Aspect Ratio (L/B)",
        "Pad + soil weight (pressure)",
        "Load Increase",
    ],
    "Value": [
        f"{allowable_pressure:.0f} kPa",
        f"{thickness:.2f} m",
        f"{founding_depth:.2f} m",
        f"{aspect_ratio:.2f}",
        f"{thickness * concrete_uw + max(founding_depth - thickness, 0) * soil_uw:.1f} kPa",
        f"{load_increase_percent:.1f} %",
    ]
})

st.dataframe(
    parameters_df,
    hide_index=True,
    use_container_width=True
)

# =====================================================
# DESIGN PADS
# =====================================================
results = []
failed = []

for _, row in columns_df.iterrows():
    try:
        results.append(
            design_pad(
                row=row,
                allowable_pressure=allowable_pressure,
                thickness=thickness,
                founding_depth=founding_depth,
                aspect_ratio=aspect_ratio,
                size_step=size_step,
                min_size=min_size,
                max_size=max_size,
                load_increase_percent=load_increase_percent,
                soil_unit_weight=soil_uw,
                concrete_unit_weight=concrete_uw,
            )
        )
    except ValueError as e:
        failed.append({"Column ID": row["Column ID"], "Reason": str(e)})

if failed:
    st.warning("Some columns could not be sized:")
    st.dataframe(pd.DataFrame(failed), hide_index=True, use_container_width=True)

if not results:
    st.error("No pads could be designed with these parameters.")
    st.stop()

overlaps = overlapping_pads(results)
overlap_map = {}
for a, b in overlaps:
    overlap_map.setdefault(a, []).append(b)
    overlap_map.setdefault(b, []).append(a)

# =====================================================
# HEADLINE NUMBERS
# =====================================================
m1, m2, m3, m4 = st.columns(4)
m1.metric("Pads", len(results))
m2.metric("Total footprint (m2)", f"{sum(f['Area'] for f in results):.1f}")
m3.metric("Concrete (m3)", f"{sum(f['Concrete Volume'] for f in results):.1f}")
m4.metric("Overlapping pairs", len(overlaps))

# =====================================================
# FOUNDATION SCHEDULE
# =====================================================
schedule = pd.DataFrame([
    {
        "Column ID": f["Column ID"],
        "X": f["X"],
        "Y": f["Y"],
        "Service Load (kN)": round(f["Service Load"], 1),
        "Total Load (kN)": round(f["Total Load"], 1),
        "B (m)": round(f["B"], 2),
        "L (m)": round(f["L"], 2),
        "Area (m2)": round(f["Area"], 2),
        "Avg Pressure (kPa)": round(f["Avg Pressure"], 1),
        "Max Pressure (kPa)": round(f["Max Pressure"], 1),
        "Min Pressure (kPa)": round(f["Min Pressure"], 1),
        "Utilisation (%)": round(f["Utilisation"] * 100, 1),
        "Governed By": f["Governed By"],
        "Overlaps With": ", ".join(overlap_map.get(f["Column ID"], [])),
    }
    for f in results
])

st.subheader("Foundation Schedule")
st.dataframe(schedule, use_container_width=True)

# =====================================================
# BUILDING PLAN
# =====================================================
st.subheader("Building Foundation Plan")
st.pyplot(plot_building_plan(results))

# =====================================================
# INDIVIDUAL FOUNDATION
# =====================================================
st.subheader("Individual Foundation Layout")

selected_column = st.selectbox(
    "Select Column",
    schedule["Column ID"]
)

selected = next(f for f in results if f["Column ID"] == selected_column)

col1, col2 = st.columns([3, 1])

with col1:
    st.pyplot(plot_pad(selected))

with col2:
    st.markdown("### Foundation Summary")
    st.write(f"**Column:** {selected['Column ID']}")
    st.write(f"**Pad Size:** {selected['B']:.1f} x {selected['L']:.1f} m")
    st.write(f"**Thickness:** {selected['Thickness']:.2f} m")
    st.write(f"**Total Load:** {selected['Total Load']:.1f} kN")
    st.write(f"**Max Pressure:** {selected['Max Pressure']:.1f} kPa")
    st.write(f"**Min Pressure:** {selected['Min Pressure']:.1f} kPa")
    st.write(f"**Utilisation:** {selected['Utilisation'] * 100:.0f} %")
    st.write(f"**Governed By:** {selected['Governed By']}")

# =====================================================
# DOWNLOAD SCHEDULE
# =====================================================
csv = schedule.to_csv(index=False).encode("utf-8")

st.download_button(
    label="Download Schedule CSV",
    data=csv,
    file_name="pad_foundation_schedule.csv",
    mime="text/csv"
)

with st.expander("Assumptions"):
    st.markdown(
        "- Service load = dead + live + wind, plus the % increase "
        "(same approach as the pile tool, no load combinations).\n"
        "- Allowable pressure is treated as **gross** at founding level; pad "
        "self weight and soil above the pad are added to the load.\n"
        "- Pads are concentric with the column.\n"
        "- A pad is enlarged until the maximum corner pressure is within the "
        "allowable pressure and the minimum is not negative (full contact).\n"
        "- Moment X changes the pressure along Y; Moment Y along X.\n"
        "- Sizing from bearing pressure only: punching shear, bending and "
        "settlement are not checked."
    )
