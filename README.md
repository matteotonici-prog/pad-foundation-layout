# Pad Foundation Layout

Streamlit app that sizes pad foundations from an Excel sheet of column loads and an allowable bearing pressure.

- `app.py` - layout generator (schedule, plan, individual pad)
- `foundation.py` - design logic and plots
- `comparison.py` - comparison logic
- `pages/1_Pad_Option_Comparison.py` - compare several pad options
- `sample_columns.xlsx` - example input

Input: sheet `Columns` with `Column ID, X, Y, Dead Load, Live Load, Wind Load` (+ optional `Moment X, Moment Y`). Units: kN, kNm, m.
