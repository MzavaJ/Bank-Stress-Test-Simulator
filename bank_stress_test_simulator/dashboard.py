import streamlit as st
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
import io, os

BOT_MINIMUM  = 12.0   # CAR floor (%)
LCR_MINIMUM  = 100.0  # Basel III / BOT LCR: HQLA / Net Cash Outflows >= 100%
LGD          = 0.50

st.set_page_config(page_title="Bank Stress Test", layout="wide")
st.title("FL-02 Bank Stress Test Simulator")
st.caption("Bank of Tanzania · CAR >= 12% | LCR >= 100% (HQLA / Net Cash Outflows)")

# Sidebar
with st.sidebar:
    uploaded_file = st.file_uploader("Upload CSV", type=["csv", "tsv"])
    shock_pcts    = st.multiselect("NPL Shock Levels (%)", [10, 20, 30, 50, 70, 80, 90, 100], default=[20, 30, 50])
    fx_shock      = st.slider("FX Shock (TZS/USD)", 0, 1000, 500, 50)
    micro_shock   = st.slider("Micro-loan Default Increase (%)", 0, 50, 20, 5)

# Load data
if uploaded_file:
    sep = "\t" if uploaded_file.name.endswith(".tsv") else ","
    raw = pd.read_csv(io.BytesIO(uploaded_file.read()), sep=sep)
else:
    sample = os.path.join(os.path.dirname(__file__), "bank_stess_test_simulator.csv")
    raw = pd.read_csv(sample) if os.path.exists(sample) else None

if raw is None:
    st.info("Upload a CSV file to begin."); st.stop()

# Stress engine — CAR
s = raw.copy()
s["bank_name"]    = s["bank_name"].str.strip()
s["perf_loan_rw"] = (s["credit_rwa_bn_tzs"] - s["npl_bn_tzs"]) / s["performing_loans_bn_tzs"]

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
# Stress: NPL shock erodes HQLA via provisioning losses (Drain = NPL × Shock × LGD)
#         and raises net cash outflows by the same drain (deposit withdrawals / margin calls)
s["lcr_baseline"] = s["hqla_bn_tzs"] / s["net_cash_outflows_bn_tzs"] * 100

for shock in [p / 100 for p in shock_pcts]:
    p          = int(shock * 100)
    drain      = s["npl_bn_tzs"] * shock * LGD
    st_hqla    = (s["hqla_bn_tzs"] - drain).clip(lower=0)
    st_outflow = s["net_cash_outflows_bn_tzs"] + drain          # outflows rise by same drain
    s[f"lcr_stressed_{p}"] = st_hqla / st_outflow * 100

# Chart 1: Baseline CAR
st.subheader("Baseline CAR by Bank")
fig, ax = plt.subplots(figsize=(12, 4))
colors = ["#2ecc3b" if v >= BOT_MINIMUM else "#e74c3c" for v in s["car_baseline_pct"]]
ax.bar(s["bank_name"], s["car_baseline_pct"], color=colors, edgecolor="white")
ax.axhline(BOT_MINIMUM, color="red", linestyle="--", linewidth=2, label="BOT Min 12%")
ax.set_ylabel("CAR (%)"); ax.legend(); plt.xticks(rotation=30, ha="right"); plt.tight_layout()
st.pyplot(fig)

# Chart 2: CAR Under NPL Shocks
if shock_pcts:
    st.subheader("CAR Under NPL Shocks")
    cols     = ["car_baseline_pct"] + [f"car_stressed_{p}" for p in shock_pcts]
    name_map = {"car_baseline_pct": "Baseline"}
    name_map.update({f"car_stressed_{p}": f"{p}% Shock" for p in shock_pcts})
    plot_df  = s.melt(id_vars="bank_name", value_vars=cols, var_name="Scenario", value_name="CAR")
    plot_df["Scenario"] = plot_df["Scenario"].map(name_map)
    fig2, ax2 = plt.subplots(figsize=(14, 5))
    sns.barplot(data=plot_df, x="bank_name", y="CAR", hue="Scenario", ax=ax2)
    ax2.axhline(BOT_MINIMUM, color="red", linestyle="--", linewidth=2)
    ax2.set_xlabel("Bank"); ax2.set_ylabel("CAR (%)")
    plt.xticks(rotation=30, ha="right"); plt.tight_layout()
    st.pyplot(fig2)

# Chart 3: Baseline LCR
st.subheader("Baseline Liquidity Coverage Ratio (LCR) by Bank")
fig3, ax3 = plt.subplots(figsize=(12, 4))
lcr_colors = ["#2ecc3b" if v >= LCR_MINIMUM else "#e74c3c" for v in s["lcr_baseline"]]
ax3.bar(s["bank_name"], s["lcr_baseline"], color=lcr_colors, edgecolor="white")
ax3.axhline(LCR_MINIMUM, color="red", linestyle="--", linewidth=2, label="BOT Min LCR 100%")
ax3.set_ylabel("LCR (%)"); ax3.legend()
plt.xticks(rotation=30, ha="right"); plt.tight_layout()
st.pyplot(fig3)

# Chart 4: LCR Under NPL Shocks
if shock_pcts:
    st.subheader("LCR Under NPL Shocks")
    lcr_cols     = ["lcr_baseline"] + [f"lcr_stressed_{p}" for p in shock_pcts]
    lcr_name_map = {"lcr_baseline": "Baseline"}
    lcr_name_map.update({f"lcr_stressed_{p}": f"{p}% Shock" for p in shock_pcts})
    lcr_df = s.melt(id_vars="bank_name", value_vars=lcr_cols, var_name="Scenario", value_name="LCR")
    lcr_df["Scenario"] = lcr_df["Scenario"].map(lcr_name_map)
    fig4, ax4 = plt.subplots(figsize=(14, 5))
    sns.barplot(data=lcr_df, x="bank_name", y="LCR", hue="Scenario", ax=ax4)
    ax4.axhline(LCR_MINIMUM, color="red", linestyle="--", linewidth=2, label="BOT Min LCR 100%")
    ax4.set_xlabel("Bank"); ax4.set_ylabel("LCR (%)"); ax4.legend()
    plt.xticks(rotation=30, ha="right"); plt.tight_layout()
    st.pyplot(fig4)

# Pass / Fail — CAR
st.subheader("CAR Pass / Fail Summary")
rows = []
for p in [0] + shock_pcts:
    col   = "car_baseline_pct" if p == 0 else f"car_stressed_{p}"
    label = "Baseline"         if p == 0 else f"{p}% Shock"
    for _, row in s.iterrows():
        rows.append({"Scenario": label, "Bank": row["bank_name"],
                     "Status": "PASS" if row[col] >= BOT_MINIMUM else "BREACH"})
pivot = pd.DataFrame(rows).pivot(index="Bank", columns="Scenario", values="Status")

def style(val):
    if val == "PASS":   return "background-color:#d4efdf; color:green; font-weight:bold"
    if val == "BREACH": return "background-color:#ffd6d6; color:red;   font-weight:bold"
    return ""
st.dataframe(pivot.style.map(style), use_container_width=True)

# Pass / Fail — LCR
st.subheader("LCR Pass / Fail Summary")
lcr_rows = []
for p in [0] + shock_pcts:
    col   = "lcr_baseline" if p == 0 else f"lcr_stressed_{p}"
    label = "Baseline"     if p == 0 else f"{p}% Shock"
    for _, row in s.iterrows():
        lcr_rows.append({"Scenario": label, "Bank": row["bank_name"],
                         "Status": "PASS" if row[col] >= LCR_MINIMUM else "BREACH"})
lcr_pivot = pd.DataFrame(lcr_rows).pivot(index="Bank", columns="Scenario", values="Status")
st.dataframe(lcr_pivot.style.map(style), use_container_width=True)

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
