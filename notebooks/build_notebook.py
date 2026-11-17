"""Builds OPMT375_Ag_Model_Lab.ipynb (Colab) from the cells below. Run: python3 build_notebook.py"""
import nbformat as nbf

cells = []
md = lambda s: cells.append(nbf.v4.new_markdown_cell(s.strip("\n")))
code = lambda s: cells.append(nbf.v4.new_code_cell(s.strip("\n")))

md(r"""
# OPMT 375 · Ag Model Lab
### Will our chain feed the Hungry Consumers through the launch?

You will build a small model of **our class supply chain**: the consumer's orders, the four firms that fill them, and the public data that pushes on them.

| Part | Session | Question | You hand in |
|---|---|---|---|
| **1 · Forecast** | Tue Nov 24 | How much will the consumer order next, and does our model beat a naive guess? | An FVA table, a memo, and a forecast **signal** committed to your repo |
| **2 · Chain** | Tue Dec 1 | With that demand, our capacities and Minnesota weather, where does the chain break during the launch? | A red/yellow/green readiness check and, if red, an **alert** signal |

**Public data (no keys needed)**
- **Weather** at each firm's location: Open-Meteo historical API (ERA5 reanalysis), daily snowfall, rain and temperature.
- **Global price of corn**: IMF, via FRED (`PMAIZMTUSDM`), monthly.
- **US diesel price**: EIA, via FRED (`GASDESW`), weekly.

**Chain data:** the class chain database (orders, shipments, capabilities). Live orders only started Nov 19. To have enough history to learn from, the lab adds a **prototype history**: 18 months of synthetic weekly orders, labeled as synthetic everywhere it appears.

**How to run it**
1. **File → Save a copy in Drive.** Work in your copy.
2. Fill in the form in cell 1 (your team slug).
3. **Runtime → Run all.** Then read top to bottom. Every place you must decide something is marked **🟡 YOUR CALL**.

You will not write code. You will read it as instructions, change the numbers marked as assumptions, and defend them. As in S6: *how would you know?*
""")

code(r'''
#@title 1 · Setup: your firm and the chain database { display-mode: "form" }
TEAM = "your-team-slug"  #@param {type:"string"}
CHAIN_URL = ""  #@param {type:"string"}
CHAIN_KEY = ""  #@param {type:"string"}
SEED = 375  #@param {type:"integer"}

import os, io, json, math, zipfile, datetime as dt
import numpy as np, pandas as pd, requests
import matplotlib.pyplot as plt
from sklearn.linear_model import LinearRegression

pd.set_option("display.width", 160); pd.set_option("display.max_columns", 20)
rng = np.random.default_rng(SEED)
TODAY = pd.Timestamp(os.environ.get("LAB_TODAY", dt.date.today().isoformat())).normalize()
WEATHER_API = os.environ.get("LAB_WEATHER_API", "https://archive-api.open-meteo.com/v1/archive")
GEOCODE_API = os.environ.get("LAB_GEOCODE_API", "https://geocoding-api.open-meteo.com/v1/search")
FRED_CSV = os.environ.get("LAB_FRED_CSV", "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}")
CHAIN_URL = os.environ.get("LAB_CHAIN_URL", CHAIN_URL).rstrip("/")
CHAIN_KEY = os.environ.get("LAB_CHAIN_KEY", CHAIN_KEY)
TEAM = os.environ.get("LAB_TEAM", TEAM)

week_of = lambda d: pd.to_datetime(d).dt.tz_localize(None).dt.to_period("W-SUN").dt.start_time
THIS_WEEK = TODAY.to_period("W-SUN").start_time
START = THIS_WEEK - pd.Timedelta(weeks=78)
HORIZON = 8   # weeks we forecast and simulate ahead
WEEKS_HIST = pd.date_range(START, THIS_WEEK - pd.Timedelta(weeks=1), freq="W-MON")
WEEKS_FUT = pd.date_range(THIS_WEEK, periods=HORIZON, freq="W-MON")

SOURCES = []   # where every number in this notebook came from
def note(kind, data, detail):
    SOURCES.append({"kind": kind, "data": data, "detail": detail})
    print(f"  [{kind}] {data}: {detail}")

print(f"Lab date {TODAY.date()} · history {START.date()} → {WEEKS_HIST[-1].date()} · forecast {WEEKS_FUT[0].date()} → {WEEKS_FUT[-1].date()}")
''')

md(r"""
## 2 · Load the chain
The chain database is the consolidated copy of every team's repo (S6). If the lab can't reach it, or a firm hasn't added its capabilities yet, it uses **prototype** values for that link and says so.
""")

code(r'''
#@title 2 · Read the chain database (or fall back to the prototype chain)
def chain_get(path):
    if not CHAIN_URL or not CHAIN_KEY:
        return None
    try:
        r = requests.get(f"{CHAIN_URL}/rest/v1/{path}", timeout=20,
                         headers={"apikey": CHAIN_KEY, "Authorization": f"Bearer {CHAIN_KEY}"})
        r.raise_for_status()
        return pd.DataFrame(r.json())
    except Exception as e:
        print(f"  could not read {path.split('?')[0]}: {e}")
        return None

teams    = chain_get("teams?select=team,name,link,gln_prefix")
parties  = chain_get("parties?select=gln,name,role,county,city,team")
products = chain_get("products?select=gtin,name,uom,team")
caps     = chain_get("v_capability_map?select=*")
orders   = chain_get("v_orders?select=*")
LIVE = teams is not None and parties is not None and orders is not None
print("Chain database:", "connected" if LIVE else "not connected (prototype chain only)")

# The prototype chain: a 2-lb bag of cornmeal, from Redwood County corn to a Twin Cities shelf.
# Every number here is an ASSUMPTION for class. Your team's capabilities replace them when they exist.
LINKS = ["Source", "Deliver", "Make", "Sell"]
PROTO = pd.DataFrame([
    # link,     site,                         city,            lat,    lon,     unit,  units_per_bag, capacity/wk (own units), lead_weeks, weather
    ["Source",  "Corn growers (stored grain)", "Redwood Falls", 44.54, -95.12,  "bu",  4/56,          120,                     1,          "roads"],
    ["Deliver", "Elevator and haul to mill",   "Morton",        44.55, -94.98,  "bu",  4/56,          85,                      1,          "roads"],
    ["Make",    "Mill: cornmeal, 2-lb bags",   "Mankato",       44.16, -94.00,  "lb",  2,             2500,                    1,          "indoor"],
    ["Sell",    "Grocery shelves",             "Minneapolis",   44.98, -93.27,  "bag", 1,             1600,                    0,          "indoor"],
], columns=["link","site","city","lat","lon","unit","units_per_bag","capacity_week","lead_weeks","weather"])
PROTO["team"] = "prototype"; PROTO["source"] = "prototype"
print("\nPrototype chain (assumptions):"); print(PROTO[["link","site","unit","units_per_bag","capacity_week","lead_weeks"]].to_string(index=False))
''')

md(r"""
### 🟡 YOUR CALL · units and the share of capacity
Last week's meaning problem is back: the store counts **bags**, the mill counts **pounds**, the elevator counts **bushels**. The model needs one conversion per link, from one consumer bag to that link's unit.

A real elevator also serves many customers. **Share** is the fraction of a link's capacity committed to *this* chain. Change the values below for your link, and be ready to say where each number came from.
""")

code(r'''
#@title 3 · Assumptions you must defend { display-mode: "form" }
BAG_LB = 2.0          #@param {type:"number"}
MILL_YIELD = 0.5      #@param {type:"number"}
LB_PER_BU = 56.0      #@param {type:"number"}
SHARE_SOURCE = 1.0    #@param {type:"number"}
SHARE_DELIVER = 1.0   #@param {type:"number"}
SHARE_MAKE = 1.0      #@param {type:"number"}
SHARE_SELL = 1.0      #@param {type:"number"}
# MILL_YIELD = lb of cornmeal per lb of corn: a placeholder. Find a source for your number.
BU_PER_BAG = BAG_LB / MILL_YIELD / LB_PER_BU
UNITS_PER_BAG = {"Source": BU_PER_BAG, "Deliver": BU_PER_BAG, "Make": BAG_LB, "Sell": 1.0}
SHARE = {"Source": SHARE_SOURCE, "Deliver": SHARE_DELIVER, "Make": SHARE_MAKE, "Sell": SHARE_SELL}
PER_PERIOD = {"hour": 24*7, "day": 7, "week": 1, "month": 12/52}

# Build the chain: one node per link. Live capabilities replace prototype values where they exist.
nodes = PROTO.copy()
nodes["units_per_bag"] = nodes["link"].map(UNITS_PER_BAG)
if LIVE and caps is not None and len(caps):
    c = caps.copy()
    c = c[c["capacity_qty"].notna() & c["capacity_period"].isin(PER_PERIOD.keys())]
    for link in LINKS:
        mine = c[c["link"] == link]
        if not len(mine):
            continue
        best = mine.assign(cw=mine["capacity_qty"].astype(float) * mine["capacity_period"].map(PER_PERIOD)).sort_values("cw").iloc[0]
        i = nodes.index[nodes["link"] == link][0]
        nodes.loc[i, ["team","site","capacity_week","source"]] = [best["team"], f'{best["team_name"]}: {best["name"]}', float(best["cw"]), "live capability"]
        if pd.notna(best.get("lead_time_days")):
            nodes.loc[i, "lead_weeks"] = int(math.ceil(float(best["lead_time_days"]) / 7))
        note("chain", f"{link} capacity", f'{best["name"]} ({best["team"]}): {best["cw"]:,.0f} {best.get("capacity_uom") or ""}/week, the smallest of {len(mine)} capabilities')
nodes["share"] = nodes["link"].map(SHARE)
nodes["cap_bags_week"] = nodes["capacity_week"] * nodes["share"] / nodes["units_per_bag"]
nodes["lead_weeks"] = nodes["lead_weeks"].astype(int)
print(nodes[["link","site","source","unit","capacity_week","share","cap_bags_week","lead_weeks"]].round(1).to_string(index=False))
print("\nOne bag of cornmeal =", round(BU_PER_BAG, 4), "bu of corn under these assumptions.")
''')

md(r"""
## 4 · Load the public data
Each source is fetched live. If one can't be reached, the lab uses a **labeled synthetic stand-in** so the class can keep going. Check the printout and say which you used.
""")

code(r'''
#@title 4 · Weather at every node, corn price and diesel price
def geocode(city):
    try:
        r = requests.get(GEOCODE_API, params={"name": city, "count": 5, "country_code": "US"}, timeout=15).json()
        mn = [x for x in r.get("results", []) if x.get("admin1") == "Minnesota"]
        return (mn[0]["latitude"], mn[0]["longitude"]) if mn else None
    except Exception:
        return None

if LIVE and parties is not None and len(parties):   # put each live link at its first party's city
    for i, n in nodes.iterrows():
        p = parties[(parties["team"] == n["team"]) & parties["city"].notna()]
        if len(p) and (ll := geocode(p.iloc[0]["city"])):
            nodes.loc[i, ["city","lat","lon"]] = [p.iloc[0]["city"], ll[0], ll[1]]

def weather_live(lat, lon):
    r = requests.get(WEATHER_API, timeout=30, params={
        "latitude": lat, "longitude": lon, "timezone": "America/Chicago",
        "start_date": (START - pd.Timedelta(days=7)).date().isoformat(),
        "end_date": (TODAY - pd.Timedelta(days=6)).date().isoformat(),
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,snowfall_sum"})
    r.raise_for_status()
    d = pd.DataFrame(r.json()["daily"]).rename(columns={"time": "date"})
    d["date"] = pd.to_datetime(d["date"])
    return d

def weather_synthetic(lat, lon):
    # SYNTHETIC: a smooth southern-Minnesota climate plus random storms. Used only if the API is unreachable.
    days = pd.date_range(START - pd.Timedelta(days=7), TODAY - pd.Timedelta(days=6))
    doy = days.dayofyear.values
    tmean = 7 - 16 * np.cos(2 * np.pi * (doy - 15) / 365) + rng.normal(0, 4, len(days))
    wet = rng.random(len(days)) < 0.28
    precip = np.where(wet, rng.gamma(1.2, 6, len(days)), 0.0)
    snow = np.where(tmean < 0, precip * 0.9, 0.0)
    return pd.DataFrame({"date": days, "temperature_2m_max": tmean + 5, "temperature_2m_min": tmean - 5,
                         "precipitation_sum": precip, "snowfall_sum": snow})

wx = []
for _, n in nodes.iterrows():
    try:
        d = weather_live(n["lat"], n["lon"]); src = "Open-Meteo archive (ERA5), live"
    except Exception as e:
        d = weather_synthetic(n["lat"], n["lon"]); src = f"SYNTHETIC climate stand-in ({type(e).__name__})"
    d["link"] = n["link"]; wx.append(d)
    note("public" if "live" in src else "synthetic", f"weather · {n['link']} ({n['city']})", f"{src}, {len(d)} days")
wx = pd.concat(wx, ignore_index=True)

def fred(series, name):
    try:
        t = pd.read_csv(io.StringIO(requests.get(FRED_CSV.format(series), timeout=20).text))
        t.columns = ["date", "value"]; t["date"] = pd.to_datetime(t["date"])
        t["value"] = pd.to_numeric(t["value"], errors="coerce"); t = t.dropna()
        note("public", name, f"FRED {series}, {len(t)} rows, latest {t['date'].max().date()} = {t['value'].iloc[-1]:,.2f}")
        return t
    except Exception as e:
        months = pd.date_range(START - pd.Timedelta(days=120), TODAY, freq="MS")
        base = 210 if series == "PMAIZMTUSDM" else 4.0
        v = base * np.exp(np.cumsum(rng.normal(0, 0.03, len(months))))
        note("synthetic", name, f"SYNTHETIC random walk ({type(e).__name__}); FRED {series} unreachable")
        return pd.DataFrame({"date": months, "value": v})

corn = fred("PMAIZMTUSDM", "global corn price, $/metric ton (IMF)")
diesel = fred("GASDESW", "US diesel retail price, $/gal (EIA)")
''')

code(r'''
#@title 5 · From daily weather to a weekly capacity factor { display-mode: "form" }
#@markdown 🟡 **YOUR CALL:** how much does bad weather cut hauling and field work? These are assumptions, not facts.
SNOW_CM = 2.0          #@param {type:"number"}
SNOW_FACTOR = 0.5      #@param {type:"number"}
RAIN_MM = 20.0         #@param {type:"number"}
RAIN_FACTOR = 0.8      #@param {type:"number"}
COLD_C = -25.0         #@param {type:"number"}
COLD_FACTOR = 0.85     #@param {type:"number"}

w = wx.copy()
w["factor"] = 1.0
w.loc[w["temperature_2m_min"] <= COLD_C, "factor"] = COLD_FACTOR
w.loc[w["precipitation_sum"] >= RAIN_MM, "factor"] = np.minimum(w["factor"], RAIN_FACTOR)
w.loc[w["snowfall_sum"] >= SNOW_CM, "factor"] = np.minimum(w["factor"], SNOW_FACTOR)
w["bad_day"] = (w["factor"] < 1).astype(int)
w["tmean"] = (w["temperature_2m_max"] + w["temperature_2m_min"]) / 2
w["week"] = week_of(w["date"])
wk_wx = w.groupby(["link","week"]).agg(factor=("factor","mean"), bad_days=("bad_day","sum"), tmean=("tmean","mean"),
                                       snow_cm=("snowfall_sum","sum")).reset_index()
weather_links = set(nodes.loc[nodes["weather"] == "roads", "link"])
wk_wx.loc[~wk_wx["link"].isin(weather_links), "factor"] = 1.0   # indoor links don't feel the weather
print("Weeks with the worst road weather (Deliver link):")
print(wk_wx[wk_wx["link"] == "Deliver"].nsmallest(5, "factor")[["week","factor","bad_days","snow_cm"]].round({"factor": 2, "snow_cm": 1}).to_string(index=False))
''')

md(r"""
## 6 · The consumer's orders
**Prototype history (synthetic, seeded):** weekly orders for 2-lb bags of cornmeal at the store. They follow a pattern with a level, a slow trend, holiday weeks, a response to the corn price, cold snaps and noise. The pattern is hidden in the code on purpose. Your model has to find it.

**Live orders:** any consumer orders in the chain database replace the prototype for the weeks they cover.
""")

code(r'''
#@title 6 · Build the weekly order history
def thanksgiving(y):
    nov1 = pd.Timestamp(y, 11, 1); return nov1 + pd.Timedelta(days=(3 - nov1.weekday()) % 7 + 21)
def holiday_flag(weeks):
    out = []
    for wk in weeks:
        f = 0
        for y in (wk.year - 1, wk.year, wk.year + 1):
            if wk <= thanksgiving(y) < wk + pd.Timedelta(days=7): f = 1
            if wk <= pd.Timestamp(y, 12, 24) < wk + pd.Timedelta(days=7): f = 1
        out.append(f)
    return np.array(out)

all_weeks = WEEKS_HIST.append(WEEKS_FUT)
corn_wk = corn.set_index("date")["value"].resample("D").ffill().reindex(pd.date_range(START - pd.Timedelta(days=60), all_weeks[-1]), method="ffill")
diesel_wk = diesel.set_index("date")["value"].resample("D").ffill().reindex(pd.date_range(START - pd.Timedelta(days=60), all_weeks[-1]), method="ffill")
X = pd.DataFrame({"week": all_weeks})
X["t"] = np.arange(len(X))
X["holiday"] = holiday_flag(X["week"])
X["corn_price_lag4"] = corn_wk.reindex(X["week"] - pd.Timedelta(weeks=4)).bfill().ffill().values
X["diesel"] = diesel_wk.reindex(X["week"]).bfill().ffill().values
sell_wx = wk_wx[wk_wx["link"] == "Sell"].set_index("week")
X["tmean_sell"] = sell_wx["tmean"].reindex(X["week"]).values
# Future weeks have no weather yet: use the same weeks one year earlier (a scenario, not a forecast)
for col in ["tmean_sell"]:
    miss = X[col].isna()
    X.loc[miss, col] = sell_wx["tmean"].reindex(X.loc[miss, "week"] - pd.Timedelta(weeks=52)).values
X["tmean_sell"] = X["tmean_sell"].fillna(X["tmean_sell"].mean())

# Prototype demand (synthetic). Hidden pattern: level, trend, holidays, corn price, cold weeks, noise.
p0 = X["corn_price_lag4"].iloc[:52].mean()
true = (1000 + 1.5 * X["t"]) * (1 + 0.45 * X["holiday"]) * (X["corn_price_lag4"] / p0) ** -0.6 * (1 + 0.06 * (X["tmean_sell"] < -10))
X["demand"] = np.round(true * rng.normal(1, 0.06, len(X)))
X["origin"] = "prototype (synthetic)"
X.loc[X["week"] >= THIS_WEEK, ["demand", "origin"]] = [np.nan, "future"]

# Live consumer orders replace the prototype for the weeks they cover
DEMAND_SCALE = 1.0
if LIVE and orders is not None and len(orders):
    o = orders[orders["buyer_team"] == "consumer"].copy()
    if len(o):
        o["week"] = week_of(o["sent_at"])
        sell_units = 1.0  # the consumer orders the Sell firm's product in bags
        live = o.groupby("week")["quantity"].sum().astype(float) / sell_units
        hit = X["week"].isin(live.index) & (X["week"] < THIS_WEEK)
        # Calibrate: scale the prototype so its level matches the real chain's orders, then let the live weeks replace it
        DEMAND_SCALE = float(live.reindex(X.loc[hit, "week"]).mean() / true[hit].mean())
        proto = X["origin"] == "prototype (synthetic)"
        X.loc[proto, "demand"] = np.round(X.loc[proto, "demand"] * DEMAND_SCALE)
        nodes.loc[nodes["source"] == "prototype", "cap_bags_week"] *= DEMAND_SCALE
        X.loc[hit, "demand"] = X.loc[hit, "week"].map(live)
        X.loc[hit, "origin"] = "live chain orders"
        note("chain", "consumer orders", f"{int(hit.sum())} live week(s) replace prototype weeks: {', '.join(str(w.date()) for w in X.loc[hit,'week'])}")
        note("assumption", "prototype scale", f"prototype orders and prototype capacities × {DEMAND_SCALE:.3f} to match the live order level")
note("synthetic", "consumer orders", f"{int((X['origin']=='prototype (synthetic)').sum())} prototype weeks (seed {SEED})")

avg = X.loc[X["week"] < THIS_WEEK, "demand"].tail(12).mean()
for _, n in nodes.iterrows():
    r = n["cap_bags_week"] / avg
    if r > 20:
        print(f"⚠ {n['link']}: capacity is {r:,.0f}× recent demand. Most of it serves other customers: set SHARE_{n['link'].upper()} in cell 3.")
    elif r < 1:
        print(f"⚠ {n['link']}: capacity is only {r:.2f}× recent demand. The chain can't keep up there.")

H = X[X["week"] < THIS_WEEK].copy()
ax = H.plot(x="week", y="demand", figsize=(11, 3.2), legend=False, color="#204E37", title="Consumer orders per week (bags)")
H[H["holiday"] == 1].plot.scatter(x="week", y="demand", ax=ax, color="#A84A26", label="holiday week")
live_pts = H[H["origin"] == "live chain orders"]
if len(live_pts): live_pts.plot.scatter(x="week", y="demand", ax=ax, color="#D9A441", s=60, label="live orders")
plt.ylabel("bags"); plt.tight_layout(); plt.show()
''')

md(r"""
# Part 1 · Forecast (Tue Nov 24)
**Forecast value added (FVA)** asks one question of every step in a forecasting process: *did this step make the forecast better than doing nothing smarter?* (Gilliland, SAS white paper in our library). The benchmark is the **naive forecast**: next week equals last week.

We hold back the last 12 weeks of history, let each model forecast them one week at a time, and compare errors.
""")

code(r'''
#@title 7 · Four forecasts, scored on the last 12 weeks
TEST_WEEKS = 12
H = X[X["week"] < THIS_WEEK].reset_index(drop=True)
train, test = H.iloc[:-TEST_WEEKS], H.iloc[-TEST_WEEKS:]
FEATS = {"Regression: trend + holidays": ["t", "holiday"],
         "Regression: + corn price + cold": ["t", "holiday", "corn_price_lag4", "tmean_sell"]}

def fit(cols, data):
    return LinearRegression().fit(data[cols], data["demand"])

preds = pd.DataFrame({"week": test["week"].values, "actual": test["demand"].values})
preds["Naive (last week)"] = H["demand"].shift(1).iloc[-TEST_WEEKS:].values
preds["4-week moving average"] = H["demand"].rolling(4).mean().shift(1).iloc[-TEST_WEEKS:].values
for name, cols in FEATS.items():
    out = []
    for i in range(len(H) - TEST_WEEKS, len(H)):   # refit each week on everything before it
        m = fit(cols, H.iloc[:i]); out.append(m.predict(H.iloc[[i]][cols])[0])
    preds[name] = out

models = [c for c in preds.columns if c not in ("week", "actual")]
def mape(a, f): return float(np.mean(np.abs(f - a) / a) * 100)
def bias(a, f): return float(np.mean(f - a) / np.mean(a) * 100)
score = pd.DataFrame({"model": models,
                      "MAPE %": [mape(preds["actual"], preds[m]) for m in models],
                      "bias %": [bias(preds["actual"], preds[m]) for m in models]})
naive = score.loc[score["model"] == "Naive (last week)", "MAPE %"].iloc[0]
score["FVA vs naive (points)"] = naive - score["MAPE %"]
score = score.round(1)
print(score.to_string(index=False))
print("\nFVA > 0 means the model beat the naive forecast by that many percentage points of MAPE.")

ax = preds.plot(x="week", y="actual", figsize=(11, 3.6), color="#1D2B23", linewidth=3, title="Held-back weeks: actual vs each forecast")
for m, col in zip(models, ["#9AA5A0", "#D9A441", "#2E6449", "#A84A26"]):
    preds.plot(x="week", y=m, ax=ax, color=col)
plt.ylabel("bags"); plt.tight_layout(); plt.show()
''')

md(r"""
### 🟡 YOUR CALL · which forecast do you send?
Pick the model your firm will use. The lowest MAPE isn't automatically the answer: look at **bias** (does it always run high or low?) and whether the inputs will exist next week. Then answer these in your memo:
1. Which model did you pick, and what is its FVA versus naive?
2. Which input added the most value? Remove it from the list in cell 7, rerun, and say what happened.
3. One way this test could flatter the model.
""")

code(r'''
#@title 8 · Forecast the next 8 weeks and translate it into your link's units { display-mode: "form" }
CHOSEN_MODEL = "best by MAPE"  #@param ["best by MAPE", "Naive (last week)", "4-week moving average", "Regression: trend + holidays", "Regression: + corn price + cold"]
LAUNCH_MULTIPLIER = 1.0  #@param {type:"number"}
#@markdown Bob says a launch is coming on Dec 3. Set LAUNCH_MULTIPLIER to what you believe it does to that week's demand (1.0 = no effect).

chosen = score.sort_values("MAPE %").iloc[0]["model"] if CHOSEN_MODEL == "best by MAPE" else CHOSEN_MODEL
F = X[X["week"] >= THIS_WEEK].copy()
if chosen in FEATS:
    F["forecast"] = fit(FEATS[chosen], H).predict(F[FEATS[chosen]])
elif chosen.startswith("4-week"):
    F["forecast"] = H["demand"].tail(4).mean()
else:
    F["forecast"] = H["demand"].iloc[-1]
launch = pd.Timestamp("2026-12-03")
F.loc[(F["week"] <= launch) & (launch < F["week"] + pd.Timedelta(days=7)), "forecast"] *= LAUNCH_MULTIPLIER
F["forecast"] = F["forecast"].round()

my = nodes[nodes["team"] == TEAM]
MY_LINK = my["link"].iloc[0] if len(my) else "Sell"
if not len(my): print(f'Team "{TEAM}" has no live capability yet, so this shows the Sell link. Fix cell 1 or add capabilities.')
F[f"{MY_LINK} units ({nodes.set_index('link').loc[MY_LINK,'unit']})"] = (F["forecast"] * UNITS_PER_BAG[MY_LINK]).round(1)
print(f"Model: {chosen}\n"); print(F[["week", "holiday", "forecast", F.columns[-1]]].to_string(index=False))
FORECAST = F[["week", "forecast"]].copy()
''')

code(r'''
#@title 9 · Turn your forecast into signal files for your supplier
def first(df, **eq):
    if df is None or not len(df): return None
    m = df
    for k, v in eq.items(): m = m[m[k] == v]
    return m.iloc[0] if len(m) else None

up_link = LINKS[LINKS.index(MY_LINK) - 1] if MY_LINK != "Source" else None
my_party = first(parties, team=TEAM)
sup_team = nodes.set_index("link").loc[up_link, "team"] if up_link else None
sup_party = first(parties, team=sup_team) if sup_team else None
sup_prod = first(products, team=sup_team) if sup_team else None
sup_unit = nodes.set_index("link").loc[up_link, "unit"] if up_link else None

if up_link is None:
    print("Source has no supplier upstream. Share your forecast as an alert or a note to Deliver instead.")
else:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for i, r in FORECAST.head(4).iterrows():
            need_by = (r["week"] + pd.Timedelta(days=6)).date().isoformat()
            sig = {"type": "forecast",
                   "from_gln": my_party["gln"] if my_party is not None else "YOUR-GLN",
                   "to_gln": sup_party["gln"] if sup_party is not None else "SUPPLIER-GLN",
                   "gtin": sup_prod["gtin"] if sup_prod is not None else "SUPPLIER-GTIN",
                   "quantity": round(float(r["forecast"]) * UNITS_PER_BAG[up_link], 1),
                   "uom": sup_unit,
                   "need_by": need_by,
                   "note": f"Forecast for the week ending {need_by}: {int(r['forecast'])} consumer bags × {UNITS_PER_BAG[up_link]:.4f} {sup_unit}/bag. Model: {chosen}."}
            z.writestr(f"signals/forecast-{r['week'].date()}.json", json.dumps(sig, indent=2))
    path = f"{TEAM}-forecast-signals.zip"; open(path, "wb").write(buf.getvalue())
    print(f"Wrote {path}: 4 forecast signals for {up_link} ({sup_team}).")
    print("Upload the four .json files to your repo's signals/ folder (Add file → Upload files) and commit.")
    print(json.dumps(json.loads(zipfile.ZipFile(buf).read(zipfile.ZipFile(buf).namelist()[0])), indent=2))
    try:
        from google.colab import files; files.download(path)
    except Exception:
        pass
''')

md(r"""
# Part 2 · Chain (Tue Dec 1)
A forecast is only half a plan. Now we push it through the four links, each with its own capacity, lead time and weather, and see where orders pile up.

**How the model works, in words:**
- Each week, each link is asked to process what the link downstream of it will need (the forecast, shifted by the lead times between them).
- It processes as much as it can, limited by three things: its capacity × share × that week's weather factor, the input that has actually arrived, and what it still owes.
- Whatever it can't do carries over as backlog.
- The shelf then sells to the consumer's **actual** orders. A shopper who finds the shelf empty buys elsewhere, so that's a lost sale. The lab measures **fill rate**: the share of demand the shelf filled that week.

The model runs over the whole history first, so the chain starts the future in a realistic state. It also gives us 18 months of simulated fulfillment to learn from.
""")

code(r'''
#@title 10 · Simulate the chain, then learn how weather and load drive fill rate
def simulate(weeks, demand_actual, demand_plan, cap_factor, node_tab, safety_weeks=0.5):
    """Each link orders up to: forecast demand until its goods reach the shelf + a safety buffer,
    minus everything already downstream of it. Then it processes what it can: capacity × weather, and input on hand."""
    n, W = len(node_tab), len(weeks)
    lead = node_tab["lead_weeks"].values.astype(int)
    offset = [int(sum(lead[j] for j in range(i, n))) for i in range(n)]   # weeks from this link's work to the shelf
    cap = node_tab["cap_bags_week"].values[:, None] * cap_factor
    pipe = np.zeros((n + 1, W + int(lead.max()) + 2))   # pipe[i+1, t] = arriving at link i+1 (or the shelf) in week t
    stock = np.zeros(n); owed = np.zeros(n)
    plan = lambda a, b: float(np.sum(demand_plan[min(a, W - 1):min(b, W - 1) + 1])) if b >= a else 0.0
    for i in range(n):   # start like a running chain: goods already on the way
        for t in range(lead[i]):
            pipe[i + 1, t] += demand_plan[min(t, W - 1)]
    shelf = float(demand_plan[0]) * (1 + safety_weeks)
    rows = []
    for t in range(W):
        shelf += pipe[n, t]
        for i in range(1, n): stock[i] += pipe[i, t]
        done = np.zeros(n)
        for i in range(n):
            downstream = shelf + sum(stock[j] for j in range(i + 1, n)) + pipe[i + 1:, t + 1:].sum()
            target = plan(t, t + offset[i]) + safety_weeks * demand_plan[min(t, W - 1)]
            owed[i] += max(0.0, target - downstream - owed[i])
            avail = np.inf if i == 0 else stock[i]
            done[i] = min(owed[i], cap[i, t], avail)
            owed[i] -= done[i]
            if i > 0: stock[i] -= done[i]
            pipe[i + 1, t + lead[i]] += done[i]
            if lead[i] == 0 and i == n - 1:
                shelf += done[i]; pipe[n, t] -= done[i]
        asked = demand_actual[t]                 # a shopper who finds an empty shelf buys elsewhere: a lost sale
        sold = min(shelf, asked); shelf -= sold
        rows.append({"week": weeks[t], "demand": demand_actual[t], "sold": sold,
                     "fill_rate": sold / asked if asked else 1.0, "lost_bags": asked - sold, "shelf_stock": shelf,
                     **{f"util {node_tab['link'].iloc[i]}": done[i] / cap[i, t] if cap[i, t] else 1 for i in range(n)},
                     **{f"owed {node_tab['link'].iloc[i]}": owed[i] for i in range(n)},
                     **{f"done {node_tab['link'].iloc[i]}": done[i] for i in range(n)}})
    return pd.DataFrame(rows)

def factors(weeks, scenario_shift=None):
    f = np.ones((len(nodes), len(weeks)))
    for i, link in enumerate(nodes["link"]):
        s = wk_wx[wk_wx["link"] == link].set_index("week")["factor"]
        v = s.reindex(weeks)
        if v.isna().any():   # future weeks: same weeks last year
            v = v.fillna(pd.Series(s.reindex(weeks - pd.Timedelta(weeks=52)).values, index=weeks))
        f[i] = v.fillna(1.0).values
    return f

hist = X[X["week"] < THIS_WEEK]
d_hist = hist["demand"].values
plan_hist = pd.Series(d_hist).shift(1).bfill().rolling(4, min_periods=1).mean().values   # how a simple firm would have planned
SAFETY_WEEKS = 0.5   # weeks of forecast each link keeps as a buffer; you can change it in cell 11
sim_hist = simulate(hist["week"].values, d_hist, plan_hist, factors(hist["week"]), nodes, SAFETY_WEEKS)

# Combine the public data with the chain's record. Where does bad weather show up first?
road = wk_wx[wk_wx["link"] == "Deliver"].set_index("week")["bad_days"]
D = sim_hist.copy()
D["road_bad_days"] = road.reindex(pd.to_datetime(D["week"])).fillna(0).values
D["load"] = D["demand"] / nodes["cap_bags_week"].min()
D = D.iloc[4:]   # skip the first weeks while the model settles
FEATS2 = ["road_bad_days", "load"]
for target, label in [("owed Deliver", "Deliver backlog (bags owed)"), ("fill_rate", "shelf fill rate")]:
    m = LinearRegression().fit(D[FEATS2], D[target])
    k = 100 if target == "fill_rate" else 1
    unit = "points" if target == "fill_rate" else "bags"
    print(f"{label}:  each bad road day {m.coef_[0]*k:+.1f} {unit} · demand at 100% of the smallest capacity {m.coef_[1]*k:+.1f} {unit}"
          f" · R² {m.score(D[FEATS2], D[target]):.2f}")
wx_kind = next(x["kind"] for x in SOURCES if x["data"].startswith("weather"))
print(f"\nWeather source: {wx_kind}. Over {len(D)} weeks the shelf filled {D['fill_rate'].mean()*100:.1f}% of demand.")
print("Bad weather hits the elevator's backlog first. The shelf only feels it once the buffers between them run out.")
util_cols = [c for c in sim_hist.columns if c.startswith("util ")]
print("\nAverage utilization by link over history:")
print((sim_hist[util_cols].iloc[4:].mean() * 100).round(0).to_string())
''')

md(r"""
### 🟡 YOUR CALL · scenarios for the launch
A **forecast** says what we expect. A **scenario** asks *what if*. Run all three, and add your own if you have reason to.
""")

code(r'''
#@title 11 · Run the launch scenarios { display-mode: "form" }
STORM_WEEK = 2   #@param {type:"integer"}
SAFETY_WEEKS = 0.5   #@param {type:"number"}
FUEL_GAL_PER_BU = 0.02   #@param {type:"number"}
#@markdown STORM_WEEK = which future week (1–8) gets a blizzard that closes the roads for 3 days in the snowstorm scenario. SAFETY_WEEKS = how many weeks of forecast each link holds as a buffer. FUEL_GAL_PER_BU = diesel burned hauling one bushel from elevator to mill (an assumption: find your own).

fut = X[X["week"] >= THIS_WEEK]
d_plan_fut = FORECAST["forecast"].values
both_weeks = np.concatenate([hist["week"].values, fut["week"].values])
plan_all = np.concatenate([plan_hist, d_plan_fut])
base_f = factors(pd.DatetimeIndex(both_weeks))

scen = {}
def run(name, actual_mult=None, storm=False):
    f = base_f.copy()
    if storm:
        k = len(hist) + STORM_WEEK - 1
        for i, link in enumerate(nodes["link"]):
            if link in weather_links: f[i, k] = min(f[i, k], 4 / 7)
    actual = np.concatenate([d_hist, d_plan_fut * (actual_mult if actual_mult is not None else 1.0)])
    s = simulate(both_weeks, actual, plan_all, f, nodes, SAFETY_WEEKS).iloc[len(hist):].reset_index(drop=True)
    s["scenario"] = name; scen[name] = s
    return s

run("1 · As forecast (weather like last year)")
run("2 · Snowstorm", storm=True)
launch_mult = np.where((fut["week"].values <= np.datetime64("2026-12-03")) & (np.datetime64("2026-12-03") < fut["week"].values + np.timedelta64(7, "D")), 2.0, 1.0)
run("3 · Launch doubles demand, plan doesn't know", actual_mult=launch_mult)

S = pd.concat(scen.values())
summary = S.groupby("scenario").agg(fill_rate=("fill_rate", "mean"), worst_week=("fill_rate", "min"), lost_bags=("lost_bags", "sum")).round(3)
summary["bottleneck"] = [S[S["scenario"] == k][util_cols].mean().idxmax().replace("util ", "") for k in summary.index]
for k, s in scen.items():
    hauled_bu = s["done Deliver"] * UNITS_PER_BAG["Deliver"]
    summary.loc[k, "haul fuel $ (8 wk)"] = round(float((hauled_bu * FUEL_GAL_PER_BU * X.loc[X["week"] >= THIS_WEEK, "diesel"].values).sum()), 2)
print(summary.to_string())
print(f"Fuel cost uses the latest diesel price, ${X['diesel'].iloc[-1]:.2f}/gal, carried forward.")

fig, ax = plt.subplots(figsize=(11, 3.6))
for (k, s), col in zip(scen.items(), ["#204E37", "#4A7FA8", "#A84A26"]):
    ax.plot(s["week"], s["fill_rate"] * 100, marker="o", color=col, label=k)
ax.axhline(95, color="#9AA5A0", linestyle="--", label="95% target"); ax.set_ylabel("fill rate %")
ax.set_title("Projected weekly fill rate at the shelf"); ax.legend(fontsize=8); plt.tight_layout(); plt.show()
''')

code(r'''
#@title 12 · Readiness check: red, yellow or green for every link in launch week
LW = scen["3 · Launch doubles demand, plan doesn't know"]
li = int(np.argmax(launch_mult)) if launch_mult.max() > 1 else 0
rows = []
for link in LINKS:
    u = max(s.loc[li, f"util {link}"] for s in scen.values())
    owed = max(s.loc[li, f"owed {link}"] for s in scen.values())
    status = "RED" if (u >= 0.999 and owed > 0) else ("YELLOW" if u >= 0.85 else "GREEN")
    rows.append({"link": link, "firm": nodes.set_index("link").loc[link, "site"], "peak utilization %": round(u * 100),
                 "backlog (bags)": round(owed), "status": status})
READY = pd.DataFrame(rows)
print(f"Launch week starting {LW.loc[li, 'week'].date()}:\n"); print(READY.to_string(index=False))
print("\nRED = at capacity with orders left over · YELLOW = above 85% · GREEN = room to spare")

mine = READY[READY["link"] == MY_LINK].iloc[0]
out = {"team": TEAM, "link": MY_LINK, "model": chosen, "launch_week": str(LW.loc[li, "week"].date()),
       "readiness": READY.to_dict("records"), "scenarios": summary.reset_index().to_dict("records"),
       "assumptions": {"BU_PER_BAG": BU_PER_BAG, "MILL_YIELD": MILL_YIELD, "SHARE": SHARE, "SNOW_FACTOR": SNOW_FACTOR,
                       "RAIN_FACTOR": RAIN_FACTOR, "COLD_FACTOR": COLD_FACTOR, "LAUNCH_MULTIPLIER": LAUNCH_MULTIPLIER},
       "sources": SOURCES}
open(f"{TEAM}-readiness.json", "w").write(json.dumps(out, indent=2, default=str))
print(f"\nWrote {TEAM}-readiness.json (attach it to the Canvas assignment).")
if mine["status"] == "RED" and my_party is not None:
    down = LINKS[LINKS.index(MY_LINK) + 1] if MY_LINK != "Sell" else None
    to = first(parties, team=nodes.set_index("link").loc[down, "team"]) if down else first(parties, team="consumer")
    alert = {"type": "alert", "from_gln": my_party["gln"], "to_gln": to["gln"] if to is not None else "PARTNER-GLN",
             "note": f"Launch-week readiness RED at {MY_LINK}: peak utilization {mine['peak utilization %']}%, "
                     f"projected backlog {mine['backlog (bags)']} bags. Model: {chosen}."}
    open(f"{TEAM}-alert.json", "w").write(json.dumps(alert, indent=2))
    print(f"Your link is RED. Wrote {TEAM}-alert.json: commit it to signals/ to warn {down or 'the consumer'}.")
try:
    from google.colab import files
    files.download(f"{TEAM}-readiness.json")
except Exception:
    pass
''')

md(r"""
### 🟡 YOUR CALL · before you hand in Part 2
1. Which link is the bottleneck in each scenario? Did it **move** between scenarios? (Constraints shift, they don't disappear.)
2. Which single assumption, changed by a defensible amount, flips your link's color? Name the number, the change, and your evidence.
3. What will your team change before Thursday's launch: a capability, a share, an order or a signal? Commit it.
""")

code(r'''
#@title 13 · Where every number came from
print(pd.DataFrame(SOURCES).to_string(index=False))
print("\nPublic data: Open-Meteo Historical Weather API (ERA5, Copernicus Climate Change Service); FRED PMAIZMTUSDM (IMF);"
      " FRED GASDESW (U.S. EIA). Prototype orders are synthetic and seeded; live orders come from the class chain database.")
''')

nb = nbf.v4.new_notebook(cells=cells, metadata={
    "colab": {"name": "OPMT375_Ag_Model_Lab.ipynb", "provenance": [], "toc_visible": True},
    "kernelspec": {"display_name": "Python 3", "name": "python3"},
    "language_info": {"name": "python"}})
nbf.write(nb, "OPMT375_Ag_Model_Lab.ipynb")
print("wrote", len(cells), "cells")
