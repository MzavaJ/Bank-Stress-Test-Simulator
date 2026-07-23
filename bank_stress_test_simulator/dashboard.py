import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import io

BOT_MINIMUM  = 12.0   # CAR floor (%)
LCR_MINIMUM  = 100.0  # Basel III / BOT LCR: HQLA / Net Cash Outflows >= 100%
LGD          = 0.50

st.set_page_config(page_title="Bank Stress Test", layout="wide")
st.title("FL-02 Bank Stress Test Simulator")
st.caption("Bank of Tanzania · CAR >= 12% | LCR >= 100% (HQLA / Net Cash Outflows)")
st.caption("Click a chart card below to open it in a popup. Inside the popup, click a bar for a plain-language breakdown.")
st.markdown(
    "<p style='font-size:18px'><b>Columns used:</b> "
    "<code>bank_name</code>, <code>tier1_capital_bn_tzs</code>, <code>tier2_capital_bn_tzs</code>, "
    "<code>performing_loans_bn_tzs</code>, <code>npl_bn_tzs</code>, <code>credit_rwa_bn_tzs</code>, "
    "<code>market_rwa_bn_tzs</code>, <code>operational_rwa_bn_tzs</code>, <code>hqla_bn_tzs</code>, "
    "<code>net_cash_outflows_bn_tzs</code>, <code>car_baseline_pct</code></p>",
    unsafe_allow_html=True,
)

# Sidebar
with st.sidebar:
    uploaded_file = st.file_uploader("Upload CSV", type=["csv", "tsv"])
    shock_pcts    = st.multiselect("NPL Shock Levels (%)", [10, 20, 30, 50, 70, 80, 90, 100], default=[20, 30, 50])
    fx_shock      = st.slider("FX Shock (TZS/USD)", 0, 1000, 500, 50)
    micro_shock   = st.slider("Micro-loan Default Increase (%)", 0, 50, 20, 5)


# Load data (user must upload a file)
# Dialog / chart-click interactions trigger a full script rerun, and on some
# reruns st.file_uploader can momentarily return None even though a file was
# already uploaded. To make the app resilient to that, we cache the raw
# bytes + filename as a single atomic session_state entry the first time a
# file arrives, and read from that cache from then on instead of trusting
# the widget every rerun.
if uploaded_file is not None:
    st.session_state["_uploaded"] = {
        "bytes": uploaded_file.getvalue(),
        "name":  uploaded_file.name,
    }

uploaded_cache = st.session_state.get("_uploaded")
if not uploaded_cache:
    st.info("Please upload a CSV or TSV file in the sidebar to begin. with the following metrics")
    st.stop()

with st.status("Loading dataset...", expanded=False) as load_status:
    sep = "\t" if uploaded_cache["name"].endswith(".tsv") else ","
    raw = pd.read_csv(io.BytesIO(uploaded_cache["bytes"]), sep=sep)
    load_status.update(label=f"Dataset loaded ({len(raw)} banks)", state="complete")

# Stress engine
with st.status("Running stress test calculations...", expanded=False) as calc_status:
    s = raw.copy()
    s["bank_name"]    = s["bank_name"].str.strip()
    s["perf_loan_rw"] = (s["credit_rwa_bn_tzs"] - s["npl_bn_tzs"]) / s["performing_loans_bn_tzs"]

    # CAR under NPL shocks
    for shock in [p / 100 for p in shock_pcts]:
        p          = int(shock * 100)
        inc_npl    = s["npl_bn_tzs"] * shock
        loss       = inc_npl * LGD
        st_capital = (s["tier1_capital_bn_tzs"] + s["tier2_capital_bn_tzs"] - loss).clip(lower=0)
        st_loans   = (s["performing_loans_bn_tzs"] - inc_npl).clip(lower=0)
        st_rwa     = st_loans * s["perf_loan_rw"] + s["npl_bn_tzs"] * (1 + shock) + s["market_rwa_bn_tzs"] + s["operational_rwa_bn_tzs"]
        s[f"loss_{p}"]         = loss
        s[f"car_stressed_{p}"] = st_capital / st_rwa * 100

    # Liquidity Coverage Ratio (LCR)
    # LCR = HQLA / Net Cash Outflows × 100    [Basel III / BOT floor: >= 100%]
    s["lcr_baseline"] = s["hqla_bn_tzs"] / s["net_cash_outflows_bn_tzs"] * 100

    for shock in [p / 100 for p in shock_pcts]:
        p          = int(shock * 100)
        drain      = s["npl_bn_tzs"] * shock * LGD
        st_hqla    = (s["hqla_bn_tzs"] - drain).clip(lower=0)
        st_outflow = s["net_cash_outflows_bn_tzs"] + drain
        s[f"lcr_stressed_{p}"] = st_hqla / st_outflow * 100

    calc_status.update(label="Computation complete", state="complete")

st.toast("Stress test computations completed!", )

# Explanatory 

CAR_INFO = """
**Capital Adequacy Ratio (CAR)** checks whether a bank has enough of its own
money (capital) set aside to absorb losses before those losses start hurting
depositors.

**Formula:** CAR = (Tier 1 Capital + Tier 2 Capital) ÷ Risk-Weighted Assets × 100

- **Tier 1 & Tier 2 Capital** — the bank's own money (shareholder funds,
  retained earnings, and similar buffers) that can absorve losses and keep the bank running.
- **Risk-Weighted Assets (RWA)** — the bank's loans and other assets, adjusted
  for how risky they are.

The **Bank of Tanzania requires CAR ≥ 12%**.The
bigger the CAR, the more room a bank has to absorb bad loans before it
becomes undercapitalized.
"""

CAR_SHOCK_INFO = """
This chart applies a **stress scenario**: what if a chosen share of the
bank's existing non-performing loans (NPLs) suddenly got worse?

We assume the bank has to write off **50% of that extra bad debt** (Loss
Given Default), which eats into capital. At the same time, risk-weighted
assets rise because the bad loans are now riskier.

A bank that stays above the **12% BOT minimum** after the shock is considered
resilient to that scenario. One that falls below it would be
undercapitalized and may need fresh capital or restructuring.
"""

LCR_INFO = """
**Liquidity Coverage Ratio (LCR)** checks whether a bank holds enough
easily-sellable, high-quality assets to survive a short, sharp bout of cash
withdrawals without collapsing.

**Formula:** LCR = High-Quality Liquid Assets (HQLA) ÷ Net Cash Outflows × 100

- **HQLA** — cash and assets the bank can quickly convert to cash (e.g.
  government securities).
- **Net Cash Outflows** — cash the bank expects to pay out over a 30-day
  stress period, minus expected inflows.

Basel III / BOT requires **LCR ≥ 100%** — the bank must hold at least as much
liquid cash as it might need to pay out.
"""

LCR_SHOCK_INFO = """
This chart shows what happens to liquidity if a share of a bank's bad loans
suddenly worsens. We assume the resulting losses **drain HQLA** (liquid
assets get used up to cover losses) **and simultaneously raise net cash
outflows** (nervous depositors withdraw funds, counterparties pull back).

A bank whose **stressed LCR stays above 100%** can still meet its short-term
obligations under the shock. Falling below 100% signals liquidity-crunch risk.
"""


def pass_fail_banner(passed, min_label):
    if passed:
        st.success(f" Passes the {min_label} minimum.")
    else:
        st.error(f"Breaches the {min_label} minimum.")


# Detail renderers — plain-language breakdown for a clicked bar.
# These render inline (not as their own popup) because a chart's popup is
# already open when a bar is clicked, and Streamlit only supports one modal
# dialog on screen at a time.
def render_car_baseline_detail(points):
    for p in points:
        cd = p.get("customdata")
        if not cd:
            continue
        bank, car, t1, t2, rwa = cd
        capital     = t1 + t2
        min_capital = BOT_MINIMUM / 100 * rwa
        buffer_tzs  = capital - min_capital
        passed      = car >= BOT_MINIMUM

        st.divider()
        st.markdown(f"### {bank}")
        st.metric("Capital Adequacy Ratio (CAR)", f"{car:.2f}%",
                  delta=f"{car - BOT_MINIMUM:+.2f} pts vs 12% BOT minimum")
        pass_fail_banner(passed, "12% CAR")

        st.markdown("**In plain terms**")
        if passed:
            st.write(f"{bank} holds about **{buffer_tzs:,.1f} bn TZS** more capital than the "
                      "bare minimum required — that's the safety cushion available to absorb "
                      "unexpected loan losses before falling below the regulatory floor.")
        else:
            st.write(f"{bank} is short by about **{abs(buffer_tzs):,.1f} bn TZS** of capital. "
                      "It would need to raise roughly this much fresh capital (or shrink its "
                      "risk-weighted assets) to meet the 12% BOT minimum.")

        with st.expander("See the calculation"):
            st.write(f"- Tier 1 Capital: **{t1:,.1f} bn TZS**")
            st.write(f"- Tier 2 Capital: **{t2:,.1f} bn TZS**")
            st.write(f"- Total Capital: **{capital:,.1f} bn TZS**")
            st.write(f"- Risk-Weighted Assets: **{rwa:,.1f} bn TZS**")
            st.latex(r"CAR=\frac{Tier\,1+Tier\,2}{RWA}\times100=" + f"{car:.2f}\\%")


def render_car_shock_detail(points):
    for p in points:
        cd = p.get("customdata")
        if not cd:
            continue
        bank, scenario, car, baseline_car = cd
        passed = car >= BOT_MINIMUM

        st.divider()
        st.markdown(f"### {bank} — {scenario}")
        st.metric("CAR under this scenario", f"{car:.2f}%",
                  delta=f"{car - BOT_MINIMUM:+.2f} pts vs 12% BOT minimum")
        pass_fail_banner(passed, "12% CAR")

        st.markdown("**In plain terms**")
        if scenario == "Baseline":
            st.write(f"This is {bank}'s current, unstressed CAR — no shock applied yet.")
        else:
            drop = baseline_car - car
            shock_label = scenario.replace(" Shock", "")
            st.write(f"**What's being tested:** if {shock_label} of {bank}'s existing bad loans "
                      f"worsen further, the bank writes off half of that extra amount and its "
                      f"risk-weighted assets rise. That pushes CAR down from "
                      f"**{baseline_car:.2f}%** (baseline) to **{car:.2f}%** — a drop of "
                      f"**{drop:.2f} percentage points**.")
            with st.expander("Why CAR falls under this shock"):
                st.write("- More bad loans mean more losses eating into Tier 1 + Tier 2 capital.")
                st.write("- Newly-worsened loans carry a higher risk weight, raising total RWA.")
                st.write("- Both effects combine to push CAR down; the further below 12% it "
                          "falls, the more capital the bank would need to raise.")


def render_lcr_baseline_detail(points):
    for p in points:
        cd = p.get("customdata")
        if not cd:
            continue
        bank, lcr, hqla, outflow = cd
        buffer_tzs = hqla - outflow
        passed     = lcr >= LCR_MINIMUM

        st.divider()
        st.markdown(f"### {bank}")
        st.metric("Liquidity Coverage Ratio (LCR)", f"{lcr:.2f}%",
                  delta=f"{lcr - LCR_MINIMUM:+.2f} pts vs 100% minimum")
        pass_fail_banner(passed, "100% LCR")

        st.markdown("**In plain terms**")
        if passed:
            st.write(f"{bank} holds about **{buffer_tzs:,.1f} bn TZS** more liquid assets than "
                      "it's expected to need over a stressed 30-day period — it should be able "
                      "to meet withdrawals and payments even under a short liquidity squeeze.")
        else:
            st.write(f"{bank} is short by about **{abs(buffer_tzs):,.1f} bn TZS** of liquid "
                      "assets versus what it might need to pay out in a stress period. It would "
                      "need more high-quality liquid assets, or less reliance on flighty "
                      "short-term funding.")

        with st.expander("See the calculation"):
            st.write(f"- High-Quality Liquid Assets (HQLA): **{hqla:,.1f} bn TZS**")
            st.write(f"- Net Cash Outflows (30-day stress): **{outflow:,.1f} bn TZS**")
            st.latex(r"LCR=\frac{HQLA}{Net\,Cash\,Outflows}\times100=" + f"{lcr:.2f}\\%")


def render_lcr_shock_detail(points):
    for p in points:
        cd = p.get("customdata")
        if not cd:
            continue
        bank, scenario, lcr, baseline_lcr = cd
        passed = lcr >= LCR_MINIMUM

        st.divider()
        st.markdown(f"### {bank} — {scenario}")
        st.metric("LCR under this scenario", f"{lcr:.2f}%",
                  delta=f"{lcr - LCR_MINIMUM:+.2f} pts vs 100% minimum")
        pass_fail_banner(passed, "100% LCR")

        st.markdown("**In plain terms**")
        if scenario == "Baseline":
            st.write(f"This is {bank}'s current, unstressed LCR — no shock applied yet.")
        else:
            drop = baseline_lcr - lcr
            shock_label = scenario.replace(" Shock", "")
            st.write(f"**What's being tested:** under a {shock_label} NPL shock, losses drain "
                      f"{bank}'s liquid assets and simultaneously push up expected cash "
                      f"outflows. That pushes LCR down from **{baseline_lcr:.2f}%** (baseline) "
                      f"to **{lcr:.2f}%** — a drop of **{drop:.2f} percentage points**.")
            with st.expander(" Why LCR falls under this shock"):
                st.write("- Provisioning losses eat into High-Quality Liquid Assets (HQLA).")
                st.write("- The same loss amount is added to expected net cash outflows, "
                          "assuming nervous depositors or counterparties pull back.")
                st.write("- Both effects push LCR down together; the lower it falls below "
                          "100%, the bigger the liquidity buffer the bank would need to rebuild.")


# Chart popups — the chart (and its explanation) only render once you click
# its card below. Clicking a bar inside the popup reveals that bank's detail
# in the same popup.
@st.dialog("Baseline CAR by Bank", width="large")
def car_baseline_chart_dialog():
    st.markdown(CAR_INFO)
    st.divider()
    car_colors = ["#2ecc71" if v >= BOT_MINIMUM else "#e74c3c" for v in s["car_baseline_pct"]]
    fig1 = go.Figure(go.Bar(
        x=s["bank_name"], y=s["car_baseline_pct"], marker_color=car_colors,
        customdata=s[["bank_name", "car_baseline_pct", "tier1_capital_bn_tzs",
                      "tier2_capital_bn_tzs", "total_rwa_bn_tzs"]].values,
        hovertemplate="<b>%{x}</b><br>CAR: %{y:.2f}%<extra></extra>",
    ))
    fig1.add_hline(y=BOT_MINIMUM, line_dash="dash", line_color="red", annotation_text="BOT Min 12%")
    fig1.update_layout(yaxis_title="CAR (%)", xaxis_tickangle=-30, height=420, margin=dict(t=30))
    st.caption(" Click a bar for that bank's breakdown.")
    event = st.plotly_chart(fig1, use_container_width=True, on_select="rerun", key="car_baseline_chart")
    if event and event.selection and event.selection.points:
        render_car_baseline_detail(event.selection.points)


@st.dialog("CAR Under NPL Shocks", width="large")
def car_shock_chart_dialog():
    st.markdown(CAR_SHOCK_INFO)
    st.divider()
    cols     = ["car_baseline_pct"] + [f"car_stressed_{p}" for p in shock_pcts]
    name_map = {"car_baseline_pct": "Baseline"}
    name_map.update({f"car_stressed_{p}": f"{p}% Shock" for p in shock_pcts})
    plot_df  = s.melt(id_vars="bank_name", value_vars=cols, var_name="Scenario", value_name="CAR")
    plot_df["Scenario"]     = plot_df["Scenario"].map(name_map)
    plot_df["baseline_car"] = plot_df["bank_name"].map(s.set_index("bank_name")["car_baseline_pct"])

    fig2 = px.bar(
        plot_df, x="bank_name", y="CAR", color="Scenario", barmode="group",
        custom_data=["bank_name", "Scenario", "CAR", "baseline_car"],
    )
    fig2.add_hline(y=BOT_MINIMUM, line_dash="dash", line_color="red", annotation_text="BOT Min 12%")
    fig2.update_traces(hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}: %{customdata[2]:.2f}%<extra></extra>")
    fig2.update_layout(xaxis_title="Bank", yaxis_title="CAR (%)", xaxis_tickangle=-30, height=460, margin=dict(t=30))
    st.caption(" Click a bar for that bank/scenario's breakdown.")
    event = st.plotly_chart(fig2, use_container_width=True, on_select="rerun", key="car_shock_chart")
    if event and event.selection and event.selection.points:
        render_car_shock_detail(event.selection.points)


@st.dialog("Baseline Liquidity Coverage Ratio (LCR) by Bank", width="large")
def lcr_baseline_chart_dialog():
    st.markdown(LCR_INFO)
    st.divider()
    lcr_colors = ["#2ecc68" if v >= LCR_MINIMUM else "#e74c3c" for v in s["lcr_baseline"]]
    fig3 = go.Figure(go.Bar(
        x=s["bank_name"], y=s["lcr_baseline"], marker_color=lcr_colors,
        customdata=s[["bank_name", "lcr_baseline", "hqla_bn_tzs", "net_cash_outflows_bn_tzs"]].values,
        hovertemplate="<b>%{x}</b><br>LCR: %{y:.2f}%<extra></extra>",
    ))
    fig3.add_hline(y=LCR_MINIMUM, line_dash="dash", line_color="red", annotation_text="BOT Min LCR 100%")
    fig3.update_layout(yaxis_title="LCR (%)", xaxis_tickangle=-30, height=420, margin=dict(t=30))
    st.caption("Click a bar for that bank's breakdown.")
    event = st.plotly_chart(fig3, use_container_width=True, on_select="rerun", key="lcr_baseline_chart")
    if event and event.selection and event.selection.points:
        render_lcr_baseline_detail(event.selection.points)


@st.dialog("LCR Under NPL Shocks", width="large")
def lcr_shock_chart_dialog():
    st.markdown(LCR_SHOCK_INFO)
    st.divider()
    lcr_cols     = ["lcr_baseline"] + [f"lcr_stressed_{p}" for p in shock_pcts]
    lcr_name_map = {"lcr_baseline": "Baseline"}
    lcr_name_map.update({f"lcr_stressed_{p}": f"{p}% Shock" for p in shock_pcts})
    lcr_df = s.melt(id_vars="bank_name", value_vars=lcr_cols, var_name="Scenario", value_name="LCR")
    lcr_df["Scenario"]     = lcr_df["Scenario"].map(lcr_name_map)
    lcr_df["baseline_lcr"] = lcr_df["bank_name"].map(s.set_index("bank_name")["lcr_baseline"])

    fig4 = px.bar(
        lcr_df, x="bank_name", y="LCR", color="Scenario", barmode="group",
        custom_data=["bank_name", "Scenario", "LCR", "baseline_lcr"],
    )
    fig4.add_hline(y=LCR_MINIMUM, line_dash="dash", line_color="red", annotation_text="BOT Min LCR 100%")
    fig4.update_traces(hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}: %{customdata[2]:.2f}%<extra></extra>")
    fig4.update_layout(xaxis_title="Bank", yaxis_title="LCR (%)", xaxis_tickangle=-30, height=460, margin=dict(t=30))
    st.caption(" Click a bar for that bank/scenario's breakdown.")
    event = st.plotly_chart(fig4, use_container_width=True, on_select="rerun", key="lcr_shock_chart")
    if event and event.selection and event.selection.points:
        render_lcr_shock_detail(event.selection.points)


# Chart launcher cards — nothing renders until a card is clicked
st.subheader("Charts")

if st.button("Baseline CAR by Bank", use_container_width=True):
    car_baseline_chart_dialog()

if shock_pcts:
    if st.button("CAR Under NPL Shocks", use_container_width=True):
        car_shock_chart_dialog()

if st.button("Baseline Liquidity Coverage Ratio (LCR) by Bank", use_container_width=True):
    lcr_baseline_chart_dialog()

if shock_pcts:
    if st.button("LCR Under NPL Shocks", use_container_width=True):
        lcr_shock_chart_dialog()

# Pass / Fail summary popups
def style(val):
    if val == "PASS":   return "background-color:#d4efdf; color:green; font-weight:bold"
    if val == "BREACH": return "background-color:#ffd6d6; color:red;   font-weight:bold"
    return ""


@st.dialog("CAR Pass / Fail Summary", width="large")
def car_summary_dialog():
    rows = []
    for p in [0] + shock_pcts:
        col   = "car_baseline_pct" if p == 0 else f"car_stressed_{p}"
        label = "Baseline"         if p == 0 else f"{p}% Shock"
        for _, row in s.iterrows():
            rows.append({"Scenario": label, "Bank": row["bank_name"],
                         "Status": "PASS" if row[col] >= BOT_MINIMUM else "BREACH"})
    pivot = pd.DataFrame(rows).pivot(index="Bank", columns="Scenario", values="Status")
    st.dataframe(pivot.style.map(style), use_container_width=True)


@st.dialog("LCR Pass / Fail Summary", width="large")
def lcr_summary_dialog():
    lcr_rows = []
    for p in [0] + shock_pcts:
        col   = "lcr_baseline" if p == 0 else f"lcr_stressed_{p}"
        label = "Baseline"     if p == 0 else f"{p}% Shock"
        for _, row in s.iterrows():
            lcr_rows.append({"Scenario": label, "Bank": row["bank_name"],
                             "Status": "PASS" if row[col] >= LCR_MINIMUM else "BREACH"})
    lcr_pivot = pd.DataFrame(lcr_rows).pivot(index="Bank", columns="Scenario", values="Status")
    st.dataframe(lcr_pivot.style.map(style), use_container_width=True)


if st.button("CAR Pass / Fail Summary", use_container_width=True):
    car_summary_dialog()

if st.button("LCR Pass / Fail Summary", use_container_width=True):
    lcr_summary_dialog()
# Additional Shock Narratives
st.subheader("Additional Shock Narratives")
col_a, col_b = st.columns(2)
col_a.metric("FX Shock", f"TZS {fx_shock}/USD")
col_a.info("Depreciation raises FX-loan debt costs, increasing effective NPL on foreign-currency exposures.")
col_b.metric("Micro-loan Default", f"+{micro_shock}%")
col_b.info(f"A {micro_shock}% rise in micro-loan defaults compresses margins and raises provisioning needs.")

# CSV Download
st.markdown("---")
all_cols  = (["bank_name", "car_baseline_pct"] + [f"car_stressed_{p}" for p in shock_pcts]
           + ["lcr_baseline"] + [f"lcr_stressed_{p}" for p in shock_pcts])
col_names = {"bank_name": "Bank", "car_baseline_pct": "Baseline CAR (%)", "lcr_baseline": "Baseline LCR (%)"}
col_names.update({f"car_stressed_{p}": f"CAR @{p}% Shock (%)" for p in shock_pcts})
col_names.update({f"lcr_stressed_{p}": f"LCR @{p}% Shock (%)" for p in shock_pcts})
result_df = s[list(dict.fromkeys(all_cols))].rename(columns=col_names).round(2)
st.download_button("⬇ Download Results CSV", result_df.to_csv(index=False).encode(),
                   "stress_test_results.csv", "text/csv")
