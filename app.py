# app.py
import streamlit as st
import json
import os
from datetime import datetime
import pandas as pd
import base64
from io import BytesIO

# Optional grafik
try:
    import altair as alt
    _ALT_OK = True
except Exception:
    _ALT_OK = False

# ====== Konfigurasi Multi-Brand ======
DATA_FILES = {
    "gulavit": "gulavit_data.json",
    "takokak": "takokak_data.json"
}
UPLOADS_DIR = "uploads"
BANNER_URL = "https://media.licdn.com/dms/image/v2/D563DAQFDri8xlKNIvg/image-scale_191_1128/image-scale_191_1128/0/1678337293506/pesona_inti_rasa_cover?e=2147483647&v=beta&t=vHi0xtyAZsT9clHb0yBYPE8M9IaO2dNY6Cb_Vs3Ddlo"
ICON_URL = "https://i.ibb.co/7C96T9y/favicon.png"

TRANS_TYPES = ["Support", "Penjualan"]  # tipe transaksi OUT

# ==== Storage backend (Google Sheets opsional) ====
USE_SHEETS = False  # True jika ingin pakai Sheets; jika belum siap, set False
SHEET_IDS = {
    "gulavit": "SPREADSHEET_ID_GULAVIT",  # ganti jika USE_SHEETS=True
    "takokak": "SPREADSHEET_ID_TAKOKAK",
}

# Pastikan folder uploads ada
if not os.path.exists(UPLOADS_DIR):
    os.makedirs(UPLOADS_DIR)

# ====== Styling & Branding ======
st.set_page_config(page_title="Inventory System", page_icon=ICON_URL, layout="wide")
st.markdown("""
    <style>
    .main { background-color: #F8FAFC; }
    h1, h2, h3 { color: #0F172A; }
    .kpi-card {
        background: #ffffff; border: 1px solid #E2E8F0; border-radius: 14px; padding: 18px 18px 12px 18px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }
    .kpi-title { font-size: 12px; color: #64748B; letter-spacing: .06em; text-transform: uppercase; }
    .kpi-value { font-size: 26px; font-weight: 700; color: #16A34A; margin-top: 6px; }
    .kpi-sub { font-size: 12px; color: #64748B; margin-top: 2px; }
    .stButton>button {
        background-color: #0EA5E9; color: white; border-radius: 8px; height: 2.6em; width: 100%; border: none;
    }
    .stButton>button:hover { background-color: #0284C7; color: white; }
    .smallcap{ font-size:12px; color:#64748B;}
    .card {
        background: #ffffff; border: 1px solid #E2E8F0; border-radius: 14px; padding: 14px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04); height: 100%;
    }
    </style>
""", unsafe_allow_html=True)

# ====== Utilitas ======
ID_MONTHS = ["Januari","Februari","Maret","April","Mei","Juni","Juli","Agustus","September","Oktober","November","Desember"]

def timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def dataframe_to_excel_bytes(df: pd.DataFrame, sheet_name="Sheet1") -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
    output.seek(0)
    return output.read()

def make_out_template_bytes(data) -> bytes:
    """Template Excel OUT: Tanggal | Kode Barang | Nama Barang | Qty | Event | Tipe"""
    today = pd.Timestamp.now().strftime("%Y-%m-%d")
    cols = ["Tanggal", "Kode Barang", "Nama Barang", "Qty", "Event", "Tipe"]
    rows = []
    inv_items = list(data.get("inventory", {}).items())
    if inv_items:
        for (code, item) in inv_items[:2]:
            rows.append({
                "Tanggal": today,
                "Kode Barang": code,
                "Nama Barang": item.get("name", ""),
                "Qty": 1,
                "Event": "Contoh event",
                "Tipe": "Support"
            })
    else:
        rows.append({
            "Tanggal": today,
            "Kode Barang": "ITM-0001",
            "Nama Barang": "Contoh Produk",
            "Qty": 1,
            "Event": "Contoh event",
            "Tipe": "Support"
        })
    df_tmpl = pd.DataFrame(rows, columns=cols)
    return dataframe_to_excel_bytes(df_tmpl, "Template OUT")

def make_return_template_bytes(data) -> bytes:
    """Template Excel Retur: Tanggal | Kode Barang | Nama Barang | Qty | Event"""
    today = pd.Timestamp.now().strftime("%Y-%m-%d")
    cols = ["Tanggal", "Kode Barang", "Nama Barang", "Qty", "Event"]
    rows = []
    inv_items = list(data.get("inventory", {}).items())
    if inv_items:
        for (code, item) in inv_items[:2]:
            rows.append({
                "Tanggal": today, "Kode Barang": code, "Nama Barang": item.get("name", ""),
                "Qty": 1, "Event": "Contoh event dari OUT"
            })
    else:
        rows.append({"Tanggal": today, "Kode Barang": "ITM-0001", "Nama Barang": "Contoh Produk", "Qty": 1, "Event": "Contoh event dari OUT"})
    df_tmpl = pd.DataFrame(rows, columns=cols)
    return dataframe_to_excel_bytes(df_tmpl, "Template Retur")

def make_master_template_bytes() -> bytes:
    """Template Excel Master: Kode Barang | Nama Barang | Qty | Satuan | Kategori"""
    cols = ["Kode Barang", "Nama Barang", "Qty", "Satuan", "Kategori"]
    df_tmpl = pd.DataFrame([{
        "Kode Barang": "ITM-0001", "Nama Barang": "Contoh Produk", "Qty": 10, "Satuan": "pcs", "Kategori": "Umum"
    }], columns=cols)
    return dataframe_to_excel_bytes(df_tmpl, "Template Master")

# ===== Normalisasi record agar kolom seragam =====
STD_REQ_COLS = ["date","code","item","qty","unit","event","trans_type","do_number","attachment","user","timestamp"]

def _to_date_str(val):
    if val is None or str(val).strip() == "":
        return datetime.now().strftime("%Y-%m-%d")
    try:
        return pd.to_datetime(val, errors="coerce").strftime("%Y-%m-%d")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d")

def _norm_event(s):
    return str(s).strip() if s is not None else "-"

def _norm_trans_type(s):
    s = "" if s is None else str(s).strip().lower()
    if s == "support": return "Support"
    if s == "penjualan": return "Penjualan"
    return None

def normalize_out_record(base: dict) -> dict:
    """Samakan kolom OUT, baik dari manual maupun Excel."""
    rec = {k: None for k in STD_REQ_COLS}
    rec.update({
        "date": _to_date_str(base.get("date")),
        "code": base.get("code", "-") or "-",
        "item": base.get("item", "-") or "-",
        "qty": int(pd.to_numeric(base.get("qty", 0), errors="coerce") or 0),
        "unit": base.get("unit", "-") or "-",
        "event": _norm_event(base.get("event", "-")),
        "trans_type": _norm_trans_type(base.get("trans_type")),
        "do_number": base.get("do_number", "-") or "-",
        "attachment": base.get("attachment"),
        "user": base.get("user", st.session_state.get("username", "-")),
        "timestamp": base.get("timestamp", timestamp()),
    })
    return rec

def normalize_return_record(base: dict) -> dict:
    """Samakan kolom RETURN (manual/Excel)."""
    rec = {k: None for k in STD_REQ_COLS}
    rec.update({
        "date": _to_date_str(base.get("date")),
        "code": base.get("code", "-") or "-",
        "item": base.get("item", "-") or "-",
        "qty": int(pd.to_numeric(base.get("qty", 0), errors="coerce") or 0),
        "unit": base.get("unit", "-") or "-",
        "event": _norm_event(base.get("event", "-")),
        "trans_type": None,
        "do_number": "-",
        "attachment": None,
        "user": base.get("user", st.session_state.get("username", "-")),
        "timestamp": base.get("timestamp", timestamp()),
    })
    return rec

# ========= Google Sheets adapter =========
def _gs_client():
    import gspread
    from google.oauth2.service_account import Credentials
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(
        dict(st.secrets.get("gcp_service_account", {})), scopes=scopes
    )
    return gspread.authorize(creds)

def _gs_open(brand_key):
    import gspread
    client = _gs_client()
    sid = SHEET_IDS.get(brand_key)
    if not sid:
        raise RuntimeError(f"Spreadsheet ID untuk brand '{brand_key}' belum diisi.")
    sh = client.open_by_key(sid)

    def ensure_ws(title, headers):
        try:
            ws = sh.worksheet(title)
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet(title=title, rows=1000, cols=max(10, len(headers)))
            ws.append_row(headers)
        # pastikan header
        values = ws.get_values("1:1")
        if not values or values[0] != headers:
            ws.clear()
            ws.append_row(headers)
        return ws

    ws_users   = ensure_ws("users",   ["username","password","role"])
    ws_inv     = ensure_ws("inventory", ["code","name","qty","unit","category"])
    ws_pending = ensure_ws("pending_requests", ["type"] + STD_REQ_COLS)
    ws_history = ensure_ws("history",
                           ["action","item","qty","stock","unit","user","event",
                            "do_number","attachment","timestamp","date","code","trans_type"])
    return sh, ws_users, ws_inv, ws_pending, ws_history

def _df_from_ws(ws):
    rows = ws.get_all_records()
    return pd.DataFrame(rows)

def _write_df(ws, df: pd.DataFrame, headers):
    df = df.copy()
    for h in headers:
        if h not in df.columns:
            df[h] = None
    df = df[headers]
    ws.clear()
    ws.append_row(headers)
    if len(df) > 0:
        ws.append_rows(df.astype(object).where(pd.notna(df), None).values.tolist())

def load_data_sheets(brand_key):
    _, ws_users, ws_inv, ws_pending, ws_history = _gs_open(brand_key)
    df_users   = _df_from_ws(ws_users)
    df_inv     = _df_from_ws(ws_inv)
    df_pending = _df_from_ws(ws_pending)
    df_history = _df_from_ws(ws_history)

    users = {}
    if not df_users.empty:
        for _, r in df_users.iterrows():
            users[str(r["username"])] = {"password": str(r["password"]), "role": str(r["role"])}

    if not users:
        users = {
            "admin": {"password": st.secrets.get("passwords", {}).get("admin"), "role": "admin"},
            "user":  {"password": st.secrets.get("passwords", {}).get("user"),  "role": "user"},
        }

    inventory = {}
    if not df_inv.empty:
        for _, r in df_inv.iterrows():
            code = str(r["code"])
            inventory[code] = {
                "name": str(r.get("name", "")),
                "qty": int(pd.to_numeric(r.get("qty", 0), errors="coerce") or 0),
                "unit": str(r.get("unit", "-")) if pd.notna(r.get("unit")) else "-",
                "category": str(r.get("category", "Uncategorized")) if pd.notna(r.get("category")) else "Uncategorized",
            }

    pending_requests = df_pending.to_dict(orient="records") if not df_pending.empty else []
    history = df_history.to_dict(orient="records") if not df_history.empty else []

    return {
        "users": users,
        "inventory": inventory,
        "item_counter": 0,
        "pending_requests": pending_requests,
        "history": history,
    }

def save_data_sheets(data, brand_key):
    _, ws_users, ws_inv, ws_pending, ws_history = _gs_open(brand_key)
    users_rows = []
    for uname, info in data.get("users", {}).items():
        users_rows.append({"username": uname, "password": info.get("password",""), "role": info.get("role","user")})
    _write_df(ws_users, pd.DataFrame(users_rows), ["username","password","role"])

    inv_rows = []
    for code, it in data.get("inventory", {}).items():
        inv_rows.append({
            "code": code, "name": it.get("name",""), "qty": int(it.get("qty",0)),
            "unit": it.get("unit","-"), "category": it.get("category","Uncategorized"),
        })
    _write_df(ws_inv, pd.DataFrame(inv_rows), ["code","name","qty","unit","category"])
    _write_df(ws_pending, pd.DataFrame(data.get("pending_requests", [])), ["type"] + STD_REQ_COLS)
    _write_df(ws_history, pd.DataFrame(data.get("history", [])),
              ["action","item","qty","stock","unit","user","event","do_number","attachment","timestamp","date","code","trans_type"])

# ====== Wrapper load/save (Sheets -> fallback JSON) ======
def load_data(brand_key):
    if USE_SHEETS:
        try:
            return load_data_sheets(brand_key)
        except Exception as e:
            st.warning(f"Gagal membaca Google Sheets: {e}. Pakai data lokal sementara.")
    # fallback JSON
    data_file = DATA_FILES[brand_key]
    if os.path.exists(data_file):
        try:
            with open(data_file, "r") as f:
                data = json.load(f)
                for code, item in data.get("inventory", {}).items():
                    if "category" not in item:
                        item["category"] = "Uncategorized"
                return data
        except (json.JSONDecodeError, FileNotFoundError):
            pass
    return {
        "users": {
            "admin": {"password": st.secrets.get("passwords", {}).get("admin"), "role": "admin"},
            "user":  {"password": st.secrets.get("passwords", {}).get("user"),  "role": "user"},
        },
        "inventory": {},
        "item_counter": 0,
        "pending_requests": [],
        "history": [],
    }

def save_data(data, brand_key):
    if USE_SHEETS:
        try:
            save_data_sheets(data, brand_key)
        except Exception as e:
            st.warning(f"Gagal menulis ke Google Sheets: {e}. Menyimpan cadangan lokal.")
    # simpan cadangan JSON lokal
    data_file = DATA_FILES[brand_key]
    with open(data_file, "w") as f:
        json.dump(data, f, indent=4)

# ===================== DATA PREP UNTUK DASHBOARD =====================
def _prepare_history_df(data: dict) -> pd.DataFrame:
    """History rapi: hanya APPROVE_* dengan tanggal efektif & tipe."""
    hist = data.get("history", [])
    df = pd.DataFrame(hist)
    if df.empty:
        return df

    df["qty"] = pd.to_numeric(df.get("qty", 0), errors="coerce").fillna(0).astype(int)
    s_date = pd.to_datetime(df["date"], errors="coerce") if "date" in df.columns else pd.Series(pd.NaT, index=df.index)
    s_ts = pd.to_datetime(df["timestamp"], errors="coerce") if "timestamp" in df.columns else pd.Series(pd.NaT, index=df.index)
    df["date_eff"] = s_date.fillna(s_ts).dt.floor("D")

    act = df.get("action", "").astype(str).str.upper()
    df["type_norm"] = "-"
    df.loc[act.str.contains("APPROVE_IN"), "type_norm"] = "IN"
    df.loc[act.str.contains("APPROVE_OUT"), "type_norm"] = "OUT"
    df.loc[act.str.contains("APPROVE_RETURN"), "type_norm"] = "RETURN"

    for col in ["item", "event", "trans_type", "unit"]:
        if col not in df.columns:
            df[col] = None
    df["event"] = df["event"].fillna("-").astype(str)
    df["trans_type"] = df["trans_type"].fillna("-").astype(str)

    df = df[df["type_norm"].isin(["IN","OUT","RETURN"])].copy()
    df = df.dropna(subset=["date_eff"])
    return df

def _calc_kpi(df_hist: pd.DataFrame, df_inv: pd.DataFrame, start_date, end_date):
    """KPI berbasis qty (bukan rupiah). Sales = OUT Penjualan."""
    total_units = int(df_inv["Current Stock"].sum()) if not df_inv.empty else 0
    total_skus  = int(len(df_inv)) if not df_inv.empty else 0

    mask = (df_hist["date_eff"] >= pd.Timestamp(start_date)) & (df_hist["date_eff"] <= pd.Timestamp(end_date)) if not df_hist.empty else pd.Series([], dtype=bool)
    df_cur = df_hist.loc[mask] if not df_hist.empty else pd.DataFrame(columns=df_hist.columns)
    df_prev = pd.DataFrame(columns=df_hist.columns)
    if not df_hist.empty:
        period_days = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days + 1
        prev_end = pd.Timestamp(start_date) - pd.Timedelta(days=1)
        prev_start = prev_end - pd.Timedelta(days=period_days-1)
        prev_mask = (df_hist["date_eff"] >= prev_start) & (df_hist["date_eff"] <= prev_end)
        df_prev = df_hist.loc[prev_mask]

    # Sales qty = OUT Penjualan
    cur_sales_qty  = int(df_cur[(df_cur["type_norm"]=="OUT") & (df_cur["trans_type"]=="Penjualan")]["qty"].sum()) if not df_cur.empty else 0
    prev_sales_qty = int(df_prev[(df_prev["type_norm"]=="OUT") & (df_prev["trans_type"]=="Penjualan")]["qty"].sum()) if not df_prev.empty else 0

    # Turnover ratio ~ sales / avg inventory (disederhanakan → sales / persediaan sekarang)
    turnover = (cur_sales_qty / total_units) if total_units > 0 else 0.0

    # Inventory to Sales ratio
    inv_to_sales = (total_units / cur_sales_qty) if cur_sales_qty > 0 else 0.0

    # Avg Days of Supply ≈ persediaan sekarang / rata-rata penjualan per hari (di periode)
    days = 0.0
    if cur_sales_qty > 0:
        days = total_units / (cur_sales_qty / max(1, (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days + 1))
    return {
        "total_units": total_units,
        "total_skus": total_skus,
        "cur_sales": cur_sales_qty,
        "prev_sales": prev_sales_qty,
        "turnover": turnover,
        "inv_to_sales": inv_to_sales,
        "days_supply": days
    }

# ===================== DASHBOARD PRO (mirip referensi) =====================
def _kpi_card(title, value, change_text=None):
    st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">{title}</div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-sub">{change_text or ""}</div>
        </div>
    """, unsafe_allow_html=True)

def _gauge(value, max_value, title):
    """Simple semi-donut gauge (Altair)."""
    try:
        if not _ALT_OK:
            st.metric(title, f"{value:.2f}")
            return
        v = float(value); vmax = max(float(max_value), 1.0)
        percent = max(0.0, min(1.0, v / vmax))
        df = pd.DataFrame({
            "label": ["filled", "rest"],
            "value": [percent, 1 - percent]
        })
        chart = alt.Chart(df).mark_arc(innerRadius=50, cornerRadius=4).encode(
            theta=alt.Theta("value:Q", stack=True),
            color=alt.Color("label:N", scale=alt.Scale(range=["#8B5CF6","#E5E7EB"]), legend=None)
        ).properties(height=160)
        st.markdown(f'<div class="smallcap">{title}</div>', unsafe_allow_html=True)
        st.altair_chart(chart, use_container_width=True)
        st.markdown(f'<div class="kpi-sub">Nilai: <b>{v:.2f}</b> (max {vmax:.0f})</div>', unsafe_allow_html=True)
    except Exception:
        st.metric(title, f"{value:.2f}")

def render_dashboard_pro(data: dict, brand_label: str, allow_download=True):
    """Dashboard interaktif:
       - 3 grafik sejajar: IN / OUT / RETURN per bulan (urut)
       - Top 10 Current Stock (nama item)
       - Top 5 Event OUT
       - Reorder insight berdasar OUT 3 bulan terakhir
    """
    df_hist = _prepare_history_df(data)
    inv_records = [
        {"Kode": code, "Nama Barang": it.get("name","-"), "Current Stock": int(it.get("qty",0)), "Unit": it.get("unit","-")}
        for code, it in data.get("inventory", {}).items()
    ]
    df_inv = pd.DataFrame(inv_records)

    st.markdown(f"## Dashboard — {brand_label}")
    st.caption("Semua metrik berbasis jumlah (qty). *Sales* = OUT dengan tipe **Penjualan**.")
    st.divider()

    # -------- Filter global (default 12 bulan terakhir) --------
    today = pd.Timestamp.today().normalize()
    default_start = (today - pd.DateOffset(months=11)).replace(day=1)
    colF1, colF2 = st.columns(2)
    start_date = colF1.date_input("Tanggal mulai", value=default_start.date())
    end_date   = colF2.date_input("Tanggal akhir", value=today.date())

    # Data pada rentang
    if not df_hist.empty:
        mask = (df_hist["date_eff"] >= pd.Timestamp(start_date)) & (df_hist["date_eff"] <= pd.Timestamp(end_date))
        df_range = df_hist.loc[mask].copy()
    else:
        df_range = pd.DataFrame(columns=["date_eff","type_norm","qty","item","event","trans_type"])

    # Helper agregasi bulanan (urut)
    def month_agg(df, tipe):
        d = df[df["type_norm"]==tipe].copy()
        if d.empty:
            return pd.DataFrame({"month": [], "qty": []})
        d["month"] = d["date_eff"].dt.to_period("M").dt.to_timestamp()  # Awal bulan
        g = d.groupby("month", as_index=False)["qty"].sum().sort_values("month")
        return g

    g_in  = month_agg(df_range, "IN")
    g_out = month_agg(df_range, "OUT")
    g_ret = month_agg(df_range, "RETURN")

    # -------- Row 1: IN/OUT/RETURN per month --------
    c1, c2, c3 = st.columns(3)
    def _month_bar(container, dfm, title, color="#0EA5E9"):
        with container:
            st.markdown(f'<div class="card"><div class="smallcap">{title}</div>', unsafe_allow_html=True)
            if _ALT_OK and not dfm.empty:
                chart = (
                    alt.Chart(dfm)
                    .mark_bar()
                    .encode(
                        x=alt.X("month:T", title="Periode", axis=alt.Axis(format="%b %Y")),
                        y=alt.Y("qty:Q", title="Qty"),
                        tooltip=[alt.Tooltip("month:T", title="Periode", format="%b %Y"), "qty:Q"],
                        color=alt.value(color)
                    )
                    .properties(height=260)
                )
                st.altair_chart(chart, use_container_width=True)
            else:
                if dfm.empty: st.info("Belum ada data.")
                else: st.bar_chart(dfm.set_index("month")["qty"])
            st.markdown("</div>", unsafe_allow_html=True)

    _month_bar(c1, g_in,  "IN per Month",    "#22C55E")
    _month_bar(c2, g_out, "OUT per Month",   "#EF4444")
    _month_bar(c3, g_ret, "RETUR per Month", "#0EA5E9")

    st.divider()

    # -------- Row 2: Top 10 current stock & Top 5 event OUT --------
    t1, t2 = st.columns([1,1])
    with t1:
        st.markdown('<div class="card"><div class="smallcap">Top 10 Items (Current Stock)</div>', unsafe_allow_html=True)
        if _ALT_OK and not df_inv.empty:
            top10 = df_inv.sort_values("Current Stock", ascending=False).head(10)
            chart = (
                alt.Chart(top10)
                .mark_bar()
                .encode(
                    y=alt.Y("Nama Barang:N", sort="-x", title=None),
                    x=alt.X("Current Stock:Q", title="Qty"),
                    tooltip=["Nama Barang","Current Stock"]
                )
                .properties(height=300)
            )
            st.altair_chart(chart, use_container_width=True)
        else:
            if df_inv.empty: st.info("Inventory kosong.")
            else: st.dataframe(df_inv.sort_values("Current Stock", ascending=False).head(10), use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with t2:
        st.markdown('<div class="card"><div class="smallcap">Top 5 Event by OUT Qty</div>', unsafe_allow_html=True)
        df_ev = df_range[(df_range["type_norm"]=="OUT") & (df_range["event"].notna())].copy()
        df_ev = df_ev[df_ev["event"].astype(str).str.strip().ne("-")]
        ev_top = (df_ev.groupby("event", as_index=False)["qty"].sum()
                  .sort_values("qty", ascending=False).head(5))
        if _ALT_OK and not ev_top.empty:
            chart = (
                alt.Chart(ev_top)
                .mark_bar()
                .encode(
                    y=alt.Y("event:N", sort="-x", title="Event"),
                    x=alt.X("qty:Q", title="Qty"),
                    tooltip=["event","qty"]
                )
                .properties(height=300)
            )
            st.altair_chart(chart, use_container_width=True)
        else:
            if ev_top.empty: st.info("Belum ada OUT pada rentang ini.")
            else: st.dataframe(ev_top.rename(columns={"event":"Event","qty":"Qty"}), use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

    st.divider()

    # -------- Row 3: Reorder insight (OUT 3 bulan terakhir) --------
    st.subheader("Reorder Insight (berdasarkan OUT 3 bulan terakhir)")
    st.caption("Menghitung *Days of Cover* ≈ stok saat ini / rata-rata pemakaian harian (dari OUT 3 bulan terakhir).")
    tgt_days = st.slider("Target Days of Cover", min_value=30, max_value=120, step=15, value=60)

    if df_inv.empty:
        st.info("Inventory kosong.")
        return

    ref_end = pd.Timestamp(end_date)
    last3_start = (ref_end - pd.DateOffset(months=3)).normalize() + pd.Timedelta(days=1)
    out3 = df_hist[(df_hist["type_norm"]=="OUT") & (df_hist["date_eff"] >= last3_start) & (df_hist["date_eff"] <= ref_end)]
    out3_item = out3.groupby("item")["qty"].sum().to_dict()

    rows = []
    for _, r in df_inv.iterrows():
        name = r["Nama Barang"]; stock = int(r["Current Stock"]); unit = r.get("Unit","-")
        last3 = int(out3_item.get(name, 0))
        avg_m = last3 / 3.0
        avg_daily = (avg_m / 30.0) if avg_m > 0 else 0.0
        if avg_daily > 0:
            doc = stock / avg_daily  # days of cover
        else:
            doc = float("inf")

        # rekomendasi
        if doc == float("inf"):
            reco, urgency = "OK (tidak ada pemakaian)", 5
        elif doc < 15:
            reco, urgency = "Order NOW (Urgent)", 1
        elif doc < 30:
            reco, urgency = "Order bulan ini", 2
        elif doc < 60:
            reco, urgency = "Order bulan depan", 3
        elif doc < 90:
            reco, urgency = "Order 2 bulan lagi", 4
        else:
            reco, urgency = "OK (stok aman)", 5

        target_qty = int(max(0, (avg_daily * tgt_days) - stock)) if avg_daily > 0 else 0

        rows.append({
            "Nama Barang": name,
            "Unit": unit,
            "Current Stock": stock,
            "OUT 3 Bulan": last3,
            "Avg OUT / Bulan": round(avg_m, 1),
            "Days of Cover": ("∞" if doc==float("inf") else int(round(doc))),
            "Rekomendasi": reco,
            "Saran Order (Qty)": target_qty,
            "_urgency": urgency
        })

    df_reorder = pd.DataFrame(rows).sort_values(["_urgency","Days of Cover"], ascending=[True, True]).drop(columns=["_urgency"])
    st.dataframe(df_reorder, use_container_width=True, hide_index=True)

    if allow_download:
        xls = BytesIO()
        with pd.ExcelWriter(xls, engine="xlsxwriter") as wr:
            df_reorder.to_excel(wr, sheet_name="Reorder Insight", index=False)
        xls.seek(0)
        st.download_button(
            "Unduh Excel Reorder Insight",
            data=xls.read(),
            file_name=f"Reorder_{brand_label.replace(' ','_')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


# ====== Session State ======
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.role = ""
    st.session_state.current_brand = "gulavit"
if "req_in_items" not in st.session_state:
    st.session_state.req_in_items = []
if "req_out_items" not in st.session_state:
    st.session_state.req_out_items = []
if "req_ret_items" not in st.session_state:
    st.session_state.req_ret_items = []
if "notification" not in st.session_state:
    st.session_state.notification = None

# ====== LOGIN PAGE ======
if not st.session_state.logged_in:
    st.image(BANNER_URL, use_container_width=True)
    st.markdown(
        f"""
        <div style="text-align:center;">
            <h1 style='margin-top:10px;'>Inventory Management System</h1>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.subheader("Silakan Login untuk Mengakses Sistem")
    username = st.text_input("Username", placeholder="Masukkan username")
    password = st.text_input("Password", type="password", placeholder="Masukkan password")
    if st.button("Login"):
        data_login = load_data("gulavit")
        user = data_login["users"].get(username)
        if user and user["password"] == password:
            st.session_state.logged_in = True
            st.session_state.username = username
            st.session_state.role = user["role"]
            st.success(f"Login berhasil sebagai {user['role'].upper()}")
            st.rerun()
        else:
            st.error("❌ Username atau password salah.")
else:
    # ====== Main App ======
    role = st.session_state.role
    st.image(BANNER_URL, use_container_width=True)
    
    # ===== Sidebar =====
    st.sidebar.markdown(f"### 👋 Halo, {st.session_state.username}")
    st.sidebar.caption(f"Role: **{role.upper()}**")
    st.sidebar.divider()

    brand_choice = st.sidebar.selectbox("Pilih Brand", list(DATA_FILES.keys()), format_func=lambda x: x.capitalize())
    st.session_state.current_brand = brand_choice
    data = load_data(st.session_state.current_brand)

    if st.sidebar.button("🚪 Logout"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.role = ""
        st.session_state.current_brand = "gulavit"
        st.rerun()

    st.sidebar.divider()

    if st.session_state.notification:
        nt = st.session_state.notification
        (st.success if nt["type"]=="success" else st.warning if nt["type"]=="warning" else st.error)(nt["message"])
        st.session_state.notification = None

    # =================== ADMIN ===================
    if role == "admin":
        admin_options = [
            "Dashboard",
            "Lihat Stok Barang",
            "Stock Card",
            "Tambah Master Barang",
            "Approve Request",
            "Riwayat Lengkap",
            "Export Laporan ke Excel",
            "Reset Database"
        ]
        menu = st.sidebar.radio("📌 Menu Admin", admin_options)

        # ===== Dashboard (Admin) =====
        if menu == "Dashboard":
            render_dashboard_pro(data, brand_label=st.session_state.current_brand.capitalize(), allow_download=False)

        elif menu == "Lihat Stok Barang":
            st.markdown(f"## Stok Barang - Brand {st.session_state.current_brand.capitalize()}")
            st.divider()
            if data["inventory"]:
                df_inventory_full = pd.DataFrame([
                    {"Kode": code, "Nama Barang": item["name"], "Qty": item["qty"], "Satuan": item.get("unit", "-"), "Kategori": item.get("category", "Uncategorized")}
                    for code, item in data["inventory"].items()
                ])
                unique_categories = ["Semua Kategori"] + sorted(df_inventory_full["Kategori"].unique())
                selected_category = st.selectbox("Pilih Kategori", unique_categories)
                search_query = st.text_input("Cari berdasarkan Nama atau Kode")
                df_filtered = df_inventory_full.copy()
                if selected_category != "Semua Kategori":
                    df_filtered = df_filtered[df_filtered["Kategori"] == selected_category]
                if search_query:
                    df_filtered = df_filtered[
                        df_filtered["Nama Barang"].str.contains(search_query, case=False) |
                        df_filtered["Kode"].str.contains(search_query, case=False)
                    ]
                st.dataframe(df_filtered, use_container_width=True, hide_index=True)
            else:
                st.info("Belum ada barang di inventory.")

        elif menu == "Stock Card":
            st.markdown(f"## Stock Card Barang - Brand {st.session_state.current_brand.capitalize()}")
            st.divider()
            if not data["history"]:
                st.info("Belum ada riwayat transaksi.")
            else:
                item_names = sorted(list({item["name"] for item in data["inventory"].values()}))
                if not item_names:
                    st.info("Belum ada master barang.")
                else:
                    selected_item_name = st.selectbox("Pilih Barang", item_names)
                    if selected_item_name:
                        filtered_history = [
                            h for h in data["history"]
                            if h["item"] == selected_item_name and (h["action"].startswith("APPROVE") or h["action"].startswith("ADD"))
                        ]
                        if filtered_history:
                            stock_card_data = []
                            current_balance = 0
                            sorted_history = sorted(filtered_history, key=lambda x: x["timestamp"])
                            for h in sorted_history:
                                transaction_in = 0
                                transaction_out = 0
                                keterangan = "N/A"
                                if h["action"] == "ADD_ITEM":
                                    transaction_in = h["qty"]; current_balance += transaction_in
                                    keterangan = "Initial Stock"
                                elif h["action"] == "APPROVE_IN":
                                    transaction_in = h["qty"]; current_balance += transaction_in
                                    keterangan = f"Request IN by {h['user']}"
                                    do_number = h.get('do_number', '-')
                                    if do_number != '-': keterangan += f" (No. DO: {do_number})"
                                elif h["action"] == "APPROVE_OUT":
                                    transaction_out = h["qty"]; current_balance -= transaction_out
                                    tipe = h.get("trans_type","-")
                                    keterangan = f"Request OUT ({tipe}) by {h['user']} for event: {h.get('event', '-')}"
                                elif h["action"] == "APPROVE_RETURN":
                                    transaction_in = h["qty"]; current_balance += transaction_in
                                    keterangan = f"Retur by {h['user']} for event: {h.get('event', '-')}"
                                else:
                                    continue
                                stock_card_data.append({
                                    "Tanggal": h.get("date", h["timestamp"]),
                                    "Keterangan": keterangan,
                                    "Masuk (IN)": transaction_in if transaction_in > 0 else "-",
                                    "Keluar (OUT)": transaction_out if transaction_out > 0 else "-",
                                    "Saldo Akhir": current_balance
                                })
                            df_stock_card = pd.DataFrame(stock_card_data)
                            st.dataframe(df_stock_card, use_container_width=True, hide_index=True)
                        else:
                            st.info("Tidak ada riwayat transaksi yang disetujui untuk barang ini.")

        elif menu == "Tambah Master Barang":
            st.markdown(f"## Tambah Master Barang - Brand {st.session_state.current_brand.capitalize()}")
            st.divider()
            tab1, tab2 = st.tabs(["Input Manual", "Upload Excel"])

            with tab1:
                code_input = st.text_input("Kode Barang (unik & wajib)", placeholder="Misal: ITM-0001")
                name = st.text_input("Nama Barang")
                unit = st.text_input("Satuan (misal: pcs, box, liter)")
                qty = st.number_input("Jumlah Stok Awal", min_value=0, step=1)
                category = st.text_input("Kategori Barang", placeholder="Misal: Minuman, Makanan")

                if st.button("Tambah Barang Manual"):
                    if not code_input.strip():
                        st.error("Kode Barang wajib diisi.")
                    elif code_input in data["inventory"]:
                        st.error(f"Kode Barang '{code_input}' sudah ada.")
                    elif not name.strip():
                        st.error("Nama barang wajib diisi.")
                    else:
                        data["inventory"][code_input] = {"name": name.strip(), "qty": int(qty), "unit": unit.strip() if unit else "-", "category": category.strip() if category else "Uncategorized"}
                        data["history"].append({
                            "action": "ADD_ITEM",
                            "item": name.strip(),
                            "qty": int(qty),
                            "stock": int(qty),
                            "unit": unit.strip() if unit else "-",
                            "user": st.session_state.username,
                            "event": "-",
                            "timestamp": timestamp()
                        })
                        save_data(data, st.session_state.current_brand)
                        st.success(f"Barang '{name}' berhasil ditambahkan dengan kode {code_input}")
                        st.rerun()

            with tab2:
                st.info("Format Excel: **Kode Barang | Nama Barang | Qty | Satuan | Kategori**")
                st.download_button(
                    label="📥 Unduh Template Master Excel",
                    data=make_master_template_bytes(),
                    file_name=f"Template_Master_{st.session_state.current_brand.capitalize()}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                file_upload = st.file_uploader("Upload File Excel Master", type=["xlsx"])
                if file_upload:
                    try:
                        df_new = pd.read_excel(file_upload, engine='openpyxl')
                    except Exception as e:
                        st.error(f"Gagal membaca file Excel: {e}")
                        df_new = None

                    required_cols = ["Kode Barang","Nama Barang","Qty","Satuan","Kategori"]
                    if df_new is not None:
                        missing = [c for c in required_cols if c not in df_new.columns]
                        if missing:
                            st.error(f"Kolom berikut belum ada di Excel: {', '.join(missing)}")
                        else:
                            if st.button("Tambah dari Excel (Master)"):
                                errors, added = [], 0
                                for idx_row, row in df_new.iterrows():
                                    code = str(row["Kode Barang"]).strip() if pd.notna(row["Kode Barang"]) else ""
                                    name = str(row["Nama Barang"]).strip() if pd.notna(row["Nama Barang"]) else ""
                                    if not code or not name:
                                        errors.append(f"Baris {idx_row+2}: Kode/Nama wajib.")
                                        continue
                                    if code in data["inventory"]:
                                        errors.append(f"Baris {idx_row+2}: Kode '{code}' sudah ada, dilewati.")
                                        continue
                                    qty = int(pd.to_numeric(row["Qty"], errors="coerce") or 0)
                                    unit = str(row["Satuan"]).strip() if pd.notna(row["Satuan"]) else "-"
                                    category = str(row["Kategori"]).strip() if pd.notna(row["Kategori"]) else "Uncategorized"
                                    data["inventory"][code] = {"name": name, "qty": qty, "unit": unit, "category": category}
                                    data["history"].append({
                                        "action": "ADD_ITEM",
                                        "item": name,
                                        "qty": qty,
                                        "stock": qty,
                                        "unit": unit,
                                        "user": st.session_state.username,
                                        "event": "-",
                                        "timestamp": timestamp()
                                    })
                                    added += 1
                                save_data(data, st.session_state.current_brand)
                                if added: st.success(f"{added} item master berhasil ditambahkan.")
                                if errors: st.warning("Beberapa baris dilewati:\n- " + "\n- ".join(errors))
                                st.rerun()

        elif menu == "Approve Request":
            st.markdown(f"## Approve / Reject Request Barang - Brand {st.session_state.current_brand.capitalize()}")
            st.divider()
            if data["pending_requests"]:
                processed_requests = []
                for req in data["pending_requests"]:
                    temp_req = req.copy()
                    for k in STD_REQ_COLS: temp_req.setdefault(k, None)
                    temp_req.setdefault('attachment', None)
                    temp_req.setdefault('trans_type', None)
                    processed_requests.append(temp_req)

                df_pending = pd.DataFrame(processed_requests)
                df_pending["Lampiran"] = df_pending["attachment"].apply(lambda x: "Ada" if x else "Tidak Ada")

                if "approve_select_flags" not in st.session_state or len(st.session_state.approve_select_flags) != len(df_pending):
                    st.session_state.approve_select_flags = [False] * len(df_pending)

                csel1, csel2 = st.columns([1,1])
                if csel1.button("Pilih semua"): st.session_state.approve_select_flags = [True]*len(df_pending)
                if csel2.button("Kosongkan pilihan"): st.session_state.approve_select_flags = [False]*len(df_pending)

                df_pending["Pilih"] = st.session_state.approve_select_flags
                col_cfg = {"Pilih": st.column_config.CheckboxColumn("Pilih", default=False)}
                for c in df_pending.columns:
                    if c != "Pilih": col_cfg[c] = st.column_config.TextColumn(c, disabled=True)
                edited_df = st.data_editor(df_pending, key="editor_admin_approve", use_container_width=True, hide_index=True, column_config=col_cfg)
                st.session_state.approve_select_flags = edited_df["Pilih"].fillna(False).tolist()
                selected_indices = [i for i, v in enumerate(st.session_state.approve_select_flags) if v]

                col1, col2 = st.columns(2)
                if col1.button("Approve Selected"):
                    if selected_indices:
                        for i in selected_indices:
                            req = processed_requests[i]
                            match_idx = next((ix for ix, r in enumerate(data["pending_requests"])
                                              if all(r.get(k)==req.get(k) for k in ["item","qty","user","type","timestamp"])), None)
                            if match_idx is not None:
                                approved_req = data["pending_requests"].pop(match_idx)
                                for code, item in data["inventory"].items():
                                    if item["name"] == approved_req["item"]:
                                        if approved_req["type"] == "IN": item["qty"] += int(approved_req["qty"])
                                        elif approved_req["type"] == "OUT": item["qty"] -= int(approved_req["qty"])
                                        elif approved_req["type"] == "RETURN": item["qty"] += int(approved_req["qty"])
                                        data["history"].append({
                                            "action": f"APPROVE_{approved_req['type']}",
                                            "item": approved_req["item"],
                                            "qty": int(approved_req["qty"]),
                                            "stock": int(item["qty"]),
                                            "unit": item.get("unit", "-"),
                                            "user": approved_req["user"],
                                            "event": approved_req.get("event", "-"),
                                            "do_number": approved_req.get("do_number", "-"),
                                            "attachment": approved_req.get("attachment"),
                                            "date": approved_req.get("date", None),
                                            "code": approved_req.get("code", None),
                                            "trans_type": approved_req.get("trans_type", None),
                                            "timestamp": timestamp()
                                        })
                        save_data(data, st.session_state.current_brand)
                        st.session_state.notification = {"type": "success", "message": f"{len(selected_indices)} request di-approve."}
                        st.rerun()
                    else:
                        st.session_state.notification = {"type": "warning", "message": "Pilih setidaknya satu item untuk di-approve."}
                        st.rerun()
                
                if col2.button("Reject Selected"):
                    if selected_indices:
                        new_pending_requests = []
                        rejected_count = 0
                        for ix, original_req in enumerate(data["pending_requests"]):
                            if ix in selected_indices:
                                rejected_count += 1
                                data["history"].append({
                                    "action": f"REJECT_{original_req['type']}",
                                    "item": original_req["item"],
                                    "qty": int(original_req["qty"]),
                                    "stock": "-",
                                    "unit": original_req.get("unit", "-"),
                                    "user": original_req["user"],
                                    "event": original_req.get("event", "-"),
                                    "do_number": original_req.get("do_number", "-"),
                                    "attachment": original_req.get("attachment"),
                                    "date": original_req.get("date", None),
                                    "code": original_req.get("code", None),
                                    "trans_type": original_req.get("trans_type", None),
                                    "timestamp": timestamp()
                                })
                            else:
                                new_pending_requests.append(original_req)
                        data["pending_requests"] = new_pending_requests
                        save_data(data, st.session_state.current_brand)
                        st.session_state.notification = {"type": "success", "message": f"{rejected_count} request di-reject."}
                        st.rerun()
                    else:
                        st.session_state.notification = {"type": "warning", "message": "Pilih setidaknya satu item untuk di-reject."}
                        st.rerun()
            else:
                st.info("Tidak ada pending request.")

        elif menu == "Riwayat Lengkap":
            st.markdown(f"## Riwayat Lengkap - Brand {st.session_state.current_brand.capitalize()}")
            st.divider()
            if data["history"]:
                all_keys = ["action","item","qty","stock","unit","user","event","do_number","attachment","timestamp","date","code","trans_type"]
                processed_history = []
                for entry in data["history"]:
                    new_entry = {key: entry.get(key, None) for key in all_keys}
                    for k, default in [("do_number","-"),("event","-"),("unit","-")]:
                        if new_entry.get(k) is None: new_entry[k] = default
                    processed_history.append(new_entry)

                df_history_full = pd.DataFrame(processed_history)
                df_history_full['date_only'] = pd.to_datetime(df_history_full['date'].fillna(df_history_full['timestamp']), errors="coerce").dt.date

                def get_download_link(path):
                    if path and os.path.exists(path):
                        with open(path, "rb") as f:
                            bytes_data = f.read()
                        b64 = base64.b64encode(bytes_data).decode()
                        return f'<a href="data:application/pdf;base64,{b64}" download="{os.path.basename(path)}">Unduh</a>'
                    return 'Tidak Ada'
                
                df_history_full['Lampiran'] = df_history_full['attachment'].apply(get_download_link)

                col1, col2 = st.columns(2)
                start_date = col1.date_input("Tanggal Mulai", value=df_history_full['date_only'].min())
                end_date = col2.date_input("Tanggal Akhir", value=df_history_full['date_only'].max())
                
                col3, col4, col5 = st.columns(3)
                unique_users = ["Semua Pengguna"] + sorted(df_history_full["user"].dropna().unique())
                selected_user = col3.selectbox("Filter Pengguna", unique_users)
                unique_actions = ["Semua Tipe"] + sorted(df_history_full["action"].dropna().unique())
                selected_action = col4.selectbox("Filter Tipe Aksi", unique_actions)
                search_item = col5.text_input("Cari Nama Barang")

                df_filtered = df_history_full.copy()
                df_filtered = df_filtered[(df_filtered['date_only'] >= start_date) & (df_filtered['date_only'] <= end_date)]
                if selected_user != "Semua Pengguna":
                    df_filtered = df_filtered[df_filtered["user"] == selected_user]
                if selected_action != "Semua Tipe":
                    df_filtered = df_filtered[df_filtered["action"] == selected_action]
                if search_item:
                    df_filtered = df_filtered[df_filtered["item"].str.contains(search_item, case=False, na=False)]

                show_cols = ["action","date","code","item","qty","unit","stock","trans_type","user","event","do_number","timestamp","Lampiran"]
                show_cols = [c for c in show_cols if c in df_filtered.columns]
                st.markdown(df_filtered[show_cols].to_html(escape=False, index=False), unsafe_allow_html=True)
            else:
                st.info("Belum ada riwayat.")

        elif menu == "Export Laporan ke Excel":
            st.markdown(f"## Filter dan Unduh Laporan - Brand {st.session_state.current_brand.capitalize()}")
            st.divider()
            if data["inventory"]:
                df_inventory_full = pd.DataFrame([
                    {"Kode": code, "Nama Barang": item["name"], "Qty": item["qty"], "Satuan": item.get("unit", "-"), "Kategori": item.get("category", "Uncategorized")}
                    for code, item in data["inventory"].items()
                ])
                unique_categories = ["Semua Kategori"] + sorted(df_inventory_full["Kategori"].unique())
                selected_category = st.selectbox("Pilih Kategori", unique_categories)
                search_query = st.text_input("Cari berdasarkan Nama atau Kode")
                df_filtered = df_inventory_full.copy()
                if selected_category != "Semua Kategori":
                    df_filtered = df_filtered[df_filtered["Kategori"] == selected_category]
                if search_query:
                    df_filtered = df_filtered[
                        df_filtered["Nama Barang"].str.contains(search_query, case=False) |
                        df_filtered["Kode"].str.contains(search_query, case=False)
                    ]
                st.markdown("### Preview Laporan")
                st.dataframe(df_filtered, use_container_width=True, hide_index=True)
                if not df_filtered.empty:
                    @st.cache_data
                    def convert_df_to_excel(df):
                        output = pd.ExcelWriter(f"{st.session_state.current_brand}_report_filtered.xlsx", engine='xlsxwriter')
                        df.to_excel(output, sheet_name='Stok Barang Filtered', index=False)
                        output.close()
                        with open(f"{st.session_state.current_brand}_report_filtered.xlsx", "rb") as f:
                            return f.read()
                    excel_data = convert_df_to_excel(df_filtered)
                    st.download_button(
                        label="Unduh Laporan Excel",
                        data=excel_data,
                        file_name=f"Laporan_Inventori_{st.session_state.current_brand.capitalize()}_Filter.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    st.warning("Tidak ada data yang cocok dengan filter yang dipilih.")
            else:
                st.info("Tidak ada data untuk diexport.")

        elif menu == "Reset Database":
            st.markdown(f"## Reset Database - Brand {st.session_state.current_brand.capitalize()}")
            st.divider()
            st.warning(f"Aksi ini akan menghapus seluruh data inventori, pending, dan riwayat untuk brand **{st.session_state.current_brand.capitalize()}**.")
            confirm = st.text_input("Ketik RESET untuk konfirmasi")
            if st.button("Reset Database") and confirm == "RESET":
                data["inventory"] = {}
                data["item_counter"] = 0
                data["pending_requests"] = []
                data["history"] = []
                save_data(data, st.session_state.current_brand)
                st.session_state.notification = {"type": "success", "message": f"✅ Database untuk {st.session_state.current_brand.capitalize()} berhasil direset!"}
                st.rerun()

    # =================== USER ===================
    elif role == "user":
        user_options = [
            "Dashboard",
            "Stock Card",
            "Request Barang IN",
            "Request Barang OUT",
            "Request Retur",
            "Lihat Riwayat"
        ]
        menu = st.sidebar.radio("📌 Menu User", user_options)
        items = list(data["inventory"].values())

        # ----- Dashboard (User) -----
        if menu == "Dashboard":
            render_dashboard_pro(data, brand_label=st.session_state.current_brand.capitalize(), allow_download=True)

        # ----- Stock Card (User) -----
        elif menu == "Stock Card":
            st.markdown(f"## Stock Card Barang - Brand {st.session_state.current_brand.capitalize()}")
            st.divider()
            if not data["history"]:
                st.info("Belum ada riwayat transaksi.")
            else:
                item_names = sorted(list({item["name"] for item in data["inventory"].values()}))
                if not item_names:
                    st.info("Belum ada master barang.")
                else:
                    selected_item_name = st.selectbox("Pilih Barang", item_names)
                    if selected_item_name:
                        filtered_history = [
                            h for h in data["history"]
                            if h["item"] == selected_item_name and (h["action"].startswith("APPROVE") or h["action"].startswith("ADD"))
                        ]
                        if filtered_history:
                            stock_card_data = []
                            current_balance = 0
                            sorted_history = sorted(filtered_history, key=lambda x: x["timestamp"])
                            for h in sorted_history:
                                transaction_in = 0
                                transaction_out = 0
                                keterangan = "N/A"
                                if h["action"] == "ADD_ITEM":
                                    transaction_in = h["qty"]; current_balance += transaction_in
                                    keterangan = "Initial Stock"
                                elif h["action"] == "APPROVE_IN":
                                    transaction_in = h["qty"]; current_balance += transaction_in
                                    keterangan = f"Request IN by {h['user']}"
                                    do_number = h.get('do_number', '-')
                                    if do_number != '-': keterangan += f" (No. DO: {do_number})"
                                elif h["action"] == "APPROVE_OUT":
                                    transaction_out = h["qty"]; current_balance -= transaction_out
                                    tipe = h.get("trans_type","-")
                                    keterangan = f"Request OUT ({tipe}) by {h['user']} for event: {h.get('event', '-')}"
                                elif h["action"] == "APPROVE_RETURN":
                                    transaction_in = h["qty"]; current_balance += transaction_in
                                    keterangan = f"Retur by {h['user']} for event: {h.get('event', '-')}"
                                else:
                                    continue
                                stock_card_data.append({
                                    "Tanggal": h.get("date", h["timestamp"]),
                                    "Keterangan": keterangan,
                                    "Masuk (IN)": transaction_in if transaction_in > 0 else "-",
                                    "Keluar (OUT)": transaction_out if transaction_out > 0 else "-",
                                    "Saldo Akhir": current_balance
                                })
                            df_stock_card = pd.DataFrame(stock_card_data)
                            st.dataframe(df_stock_card, use_container_width=True, hide_index=True)
                        else:
                            st.info("Tidak ada riwayat transaksi yang disetujui untuk barang ini.")

        # ----- Request Barang IN (Manual; semua wajib) -----
        elif menu == "Request Barang IN":
            st.markdown(f"## Request Barang Masuk (Manual) - Brand {st.session_state.current_brand.capitalize()}")
            st.divider()
            if items:
                col1, col2 = st.columns(2)
                idx = col1.selectbox(
                    "Pilih Barang", range(len(items)),
                    format_func=lambda x: f"{items[x]['name']} ({items[x]['qty']} {items[x].get('unit', '-')})"
                )
                qty = col2.number_input("Jumlah", min_value=1, step=1)

                if st.button("Tambah Item IN"):
                    st.session_state.req_in_items.append({
                        "item": items[idx]["name"],
                        "qty": qty,
                        "unit": items[idx].get("unit", "-"),
                        "event": "-"
                    })
                    st.success("Item IN ditambahkan ke daftar.")

                if st.session_state.req_in_items:
                    st.subheader("Daftar Item Request IN")

                    if "in_select_flags" not in st.session_state or len(st.session_state.in_select_flags) != len(st.session_state.req_in_items):
                        st.session_state.in_select_flags = [False]*len(st.session_state.req_in_items)

                    cA, cB = st.columns([1,1])
                    if cA.button("Pilih semua", key="in_sel_all"):
                        st.session_state.in_select_flags = [True]*len(st.session_state.req_in_items)
                    if cB.button("Kosongkan pilihan", key="in_sel_none"):
                        st.session_state.in_select_flags = [False]*len(st.session_state.req_in_items)

                    df_in = pd.DataFrame(st.session_state.req_in_items)
                    df_in["Pilih"] = st.session_state.in_select_flags
                    edited_df_in = st.data_editor(df_in, key="editor_in", use_container_width=True, hide_index=True)
                    st.session_state.in_select_flags = edited_df_in["Pilih"].fillna(False).tolist()

                    if st.button("Hapus Item Terpilih", key="delete_in"):
                        mask = st.session_state.in_select_flags
                        if any(mask):
                            st.session_state.req_in_items = [rec for rec, keep in zip(st.session_state.req_in_items, [not x for x in mask]) if keep]
                            st.session_state.in_select_flags = [False]*len(st.session_state.req_in_items)
                            st.rerun()
                        else:
                            st.info("Tidak ada baris yang dipilih.")

                    st.divider()
                    st.subheader("Informasi Wajib")
                    do_number = st.text_input("Nomor Surat Jalan (wajib)", placeholder="Masukkan Nomor Surat Jalan")
                    uploaded_file = st.file_uploader("Upload PDF Delivery Order / Surat Jalan (wajib)", type=["pdf"])
                    
                    if st.button("Ajukan Request IN Terpilih"):
                        mask = st.session_state.in_select_flags
                        if not any(mask):
                            st.warning("Pilih setidaknya satu item untuk diajukan.")
                        elif not do_number.strip():
                            st.error("Nomor Surat Jalan wajib diisi.")
                        elif not uploaded_file:
                            st.error("PDF Surat Jalan wajib diupload.")
                        else:
                            timestamp_str = datetime.now().strftime("%Y%m%d%H%M%S")
                            file_ext = uploaded_file.name.split(".")[-1]
                            attachment_path = os.path.join(UPLOADS_DIR, f"{st.session_state.username}_{timestamp_str}.{file_ext}")
                            with open(attachment_path, "wb") as f:
                                f.write(uploaded_file.getbuffer())

                            submit_count = 0
                            new_state, new_flags = [], []
                            for selected, rec in zip(mask, st.session_state.req_in_items):
                                if selected:
                                    base = {
                                        "date": None,
                                        "code": next((c for c, it in data["inventory"].items() if it.get("name")==rec["item"]), "-"),
                                        "item": rec["item"],
                                        "qty": int(rec["qty"]),
                                        "unit": rec.get("unit", "-"),
                                        "event": "-",
                                        "trans_type": None,
                                        "do_number": do_number.strip(),
                                        "attachment": attachment_path,
                                        "user": st.session_state.username,
                                        "timestamp": timestamp(),
                                    }
                                    norm = normalize_out_record(base)
                                    norm["type"] = "IN"
                                    data["pending_requests"].append(norm)
                                    submit_count += 1
                                else:
                                    new_state.append(rec); new_flags.append(False)
                            save_data(data, st.session_state.current_brand)
                            st.session_state.req_in_items = new_state
                            st.session_state.in_select_flags = new_flags
                            st.success(f"{submit_count} request IN diajukan & menunggu approval.")
                            st.rerun()
            else:
                st.info("Belum ada master barang. Silakan hubungi admin.")

        # ----- Request Barang OUT -----
        elif menu == "Request Barang OUT":
            st.markdown(f"## Request Barang Keluar (Multi Item) - Brand {st.session_state.current_brand.capitalize()}")
            st.divider()

            if items:
                tab1, tab2 = st.tabs(["Input Manual", "Upload Excel"])

                # INPUT MANUAL (wajib event & tipe)
                with tab1:
                    col1, col2 = st.columns(2)
                    idx = col1.selectbox(
                        "Pilih Barang", range(len(items)),
                        format_func=lambda x: f"{items[x]['name']} (Stok: {items[x]['qty']} {items[x].get('unit', '-')})"
                    )

                    # handle stok 0 -> kunci input
                    max_qty = int(pd.to_numeric(items[idx].get("qty", 0), errors="coerce") or 0)
                    if max_qty < 1:
                        qty = 0
                        col2.number_input("Jumlah", min_value=0, max_value=0, step=1, value=0, disabled=True)
                        st.warning("Stok item ini 0. Tidak bisa menambah request OUT.")
                    else:
                        qty = col2.number_input("Jumlah", min_value=1, max_value=max_qty, step=1)

                    tipe = st.selectbox("Tipe Transaksi (wajib)", TRANS_TYPES, index=0)
                    event_manual = st.text_input("Nama Event (wajib)", placeholder="Misal: Pameran, Acara Kantor")

                    if st.button("Tambah Item OUT (Manual)"):
                        if max_qty < 1:
                            st.error("Stok 0 — tidak bisa menambah OUT untuk item ini.")
                        elif not event_manual.strip():
                            st.error("Event wajib diisi.")
                        elif qty < 1:
                            st.error("Jumlah harus minimal 1.")
                        else:
                            selected_name = items[idx]["name"]
                            found_code = next((code for code, it in data["inventory"].items() if it.get("name") == selected_name), None)
                            base = {
                                "date": datetime.now().strftime("%Y-%m-%d"),
                                "code": found_code if found_code else "-",
                                "item": selected_name,
                                "qty": qty,
                                "unit": items[idx].get("unit", "-"),
                                "event": event_manual.strip(),
                                "trans_type": tipe,
                                "user": st.session_state.username,
                            }
                            st.session_state.req_out_items.append(normalize_out_record(base))
                            st.success("Item OUT (manual) ditambahkan ke daftar.")

                # UPLOAD EXCEL
                with tab2:
                    st.info("Format kolom: **Tanggal | Kode Barang | Nama Barang | Qty | Event | Tipe** (Tipe = Support atau Penjualan)")
                    st.download_button(
                        label="📥 Unduh Template Excel OUT",
                        data=make_out_template_bytes(data),
                        file_name=f"Template_OUT_{st.session_state.current_brand.capitalize()}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

                    file_upload = st.file_uploader("Upload File Excel OUT", type=["xlsx"], key="out_excel_uploader")
                    if file_upload:
                        try:
                            df_new = pd.read_excel(file_upload, engine='openpyxl')
                        except Exception as e:
                            st.error(f"Gagal membaca file Excel: {e}")
                            df_new = None

                        required_cols = ["Tanggal", "Kode Barang", "Nama Barang", "Qty", "Event", "Tipe"]
                        if df_new is not None:
                            missing = [c for c in required_cols if c not in df_new.columns]
                            if missing:
                                st.error(f"Kolom berikut belum ada di Excel: {', '.join(missing)}")
                            else:
                                if st.button("Tambah dari Excel (OUT)"):
                                    errors, added = [], 0
                                    by_code = {code: (it.get("name"), it.get("unit", "-"), it.get("qty", 0)) for code, it in data["inventory"].items()}
                                    by_name = {it.get("name"): (code, it.get("unit", "-"), it.get("qty", 0)) for code, it in data["inventory"].items()}

                                    for idx_row, row in df_new.iterrows():
                                        try:
                                            dt = pd.to_datetime(row["Tanggal"], errors="coerce")
                                            date_str = dt.strftime("%Y-%m-%d") if pd.notna(dt) else datetime.now().strftime("%Y-%m-%d")

                                            code_xl = str(row["Kode Barang"]).strip() if pd.notna(row["Kode Barang"]) else ""
                                            name_xl = str(row["Nama Barang"]).strip() if pd.notna(row["Nama Barang"]) else ""
                                            qty_xl = int(pd.to_numeric(row["Qty"], errors="coerce") or 0)
                                            event_xl_raw = str(row["Event"]).strip() if pd.notna(row["Event"]) else ""
                                            tipe_xl_raw = str(row["Tipe"]).strip().lower() if pd.notna(row["Tipe"]) else ""

                                            if not event_xl_raw:
                                                errors.append(f"Baris {idx_row+2}: Event wajib diisi."); continue
                                            if tipe_xl_raw not in ["support","penjualan"]:
                                                errors.append(f"Baris {idx_row+2}: Tipe harus 'Support' atau 'Penjualan'."); continue
                                            tipe_xl = "Support" if tipe_xl_raw=="support" else "Penjualan"

                                            inv_name, inv_unit, inv_stock = (None, None, None)
                                            inv_code = None
                                            if code_xl and code_xl in by_code:
                                                inv_name, inv_unit, inv_stock = by_code[code_xl]; inv_code = code_xl
                                            elif name_xl and name_xl in by_name:
                                                inv_code, inv_unit, inv_stock = by_name[name_xl]; inv_name = name_xl
                                            else:
                                                errors.append(f"Baris {idx_row+2}: Item tidak ditemukan (kode='{code_xl}', nama='{name_xl}')."); continue
                                            if qty_xl <= 0:
                                                errors.append(f"Baris {idx_row+2}: Qty harus > 0."); continue
                                            if inv_stock is not None and qty_xl > inv_stock:
                                                errors.append(f"Baris {idx_row+2}: Qty ({qty_xl}) melebihi stok ({inv_stock}) untuk '{inv_name}'."); continue

                                            base = {
                                                "date": date_str, "code": inv_code if inv_code else "-", "item": inv_name,
                                                "qty": qty_xl, "unit": inv_unit if inv_unit else "-",
                                                "event": event_xl_raw, "trans_type": tipe_xl, "user": st.session_state.username,
                                            }
                                            st.session_state.req_out_items.append(normalize_out_record(base))
                                            added += 1
                                        except Exception as e:
                                            errors.append(f"Baris {idx_row+2}: {e}")

                                    if added: st.success(f"{added} baris ditambahkan ke daftar OUT.")
                                    if errors: st.warning("Beberapa baris dilewati:\n- " + "\n- ".join(errors))

                # DAFTAR & SUBMIT OUT
                if st.session_state.req_out_items:
                    st.subheader("Daftar Item Request OUT")
                    df_out = pd.DataFrame(st.session_state.req_out_items)
                    pref_cols = [c for c in ["date","code","item","qty","unit","event","trans_type"] if c in df_out.columns]
                    df_out = df_out[pref_cols]

                    if "out_select_flags" not in st.session_state or len(st.session_state.out_select_flags) != len(st.session_state.req_out_items):
                        st.session_state.out_select_flags = [False] * len(st.session_state.req_out_items)

                    c1, c2 = st.columns([1,1])
                    if c1.button("Pilih semua", key="out_sel_all"): st.session_state.out_select_flags = [True] * len(st.session_state.req_out_items)
                    if c2.button("Kosongkan pilihan", key="out_sel_none"): st.session_state.out_select_flags = [False] * len(st.session_state.req_out_items)

                    df_out["Pilih"] = st.session_state.out_select_flags
                    edited_df_out = st.data_editor(df_out, key="editor_out", use_container_width=True, hide_index=True)
                    st.session_state.out_select_flags = edited_df_out["Pilih"].fillna(False).tolist()

                    if st.button("Hapus Item Terpilih", key="delete_out"):
                        mask = st.session_state.out_select_flags
                        if any(mask):
                            st.session_state.req_out_items = [rec for rec, keep in zip(st.session_state.req_out_items, [not x for x in mask]) if keep]
                            st.session_state.out_select_flags = [False]*len(st.session_state.req_out_items)
                            st.rerun()
                        else:
                            st.info("Tidak ada baris yang dipilih.")

                    st.divider()
                    if st.button("Ajukan Request OUT Terpilih"):
                        mask = st.session_state.out_select_flags
                        if not any(mask):
                            st.warning("Pilih setidaknya satu item untuk diajukan.")
                        else:
                            submitted = 0
                            new_state, new_flags = [], []
                            for selected, rec in zip(mask, st.session_state.req_out_items):
                                if selected:
                                    base = rec.copy(); base["user"] = st.session_state.username
                                    norm = normalize_out_record(base); norm["type"] = "OUT"
                                    data["pending_requests"].append(norm); submitted += 1
                                else:
                                    new_state.append(rec); new_flags.append(False)
                            save_data(data, st.session_state.current_brand)
                            st.session_state.req_out_items = new_state
                            st.session_state.out_select_flags = new_flags
                            st.success(f"{submitted} request OUT diajukan & menunggu approval.")
                            st.rerun()
            else:
                st.info("Belum ada master barang. Silakan hubungi admin.")

        # ----- Request Retur -----
        elif menu == "Request Retur":
            st.markdown(f"## Request Retur (Pengembalian ke Gudang) - Brand {st.session_state.current_brand.capitalize()}")
            st.divider()

            if items:
                # Peta event OUT approved per item
                hist = data.get("history", [])
                approved_out_map = {}
                for h in hist:
                    if h.get("action") == "APPROVE_OUT":
                        it = h.get("item"); ev = h.get("event")
                        if it and ev and ev not in ["-", None, ""]:
                            approved_out_map.setdefault(it, set()).add(ev)

                tab1, tab2 = st.tabs(["Input Manual", "Upload Excel"])

                with tab1:
                    col1, col2 = st.columns(2)
                    idx = col1.selectbox(
                        "Pilih Barang", range(len(items)),
                        format_func=lambda x: f"{items[x]['name']} (Stok Gudang: {items[x]['qty']} {items[x].get('unit','-')})"
                    )
                    qty = col2.number_input("Jumlah Retur", min_value=1, step=1)
                    item_name = items[idx]["name"]; unit_name = items[idx].get("unit", "-")
                    approved_events = sorted(list(approved_out_map.get(item_name, set())))
                    if not approved_events:
                        st.warning("Belum ada event OUT yang di-approve untuk item ini.")
                        event_choice = None
                    else:
                        event_choice = st.selectbox("Pilih Event (berdasarkan OUT yang disetujui)", approved_events)
                    if st.button("Tambah Item Retur (Manual)"):
                        if not event_choice:
                            st.error("Pilih event terlebih dahulu.")
                        else:
                            base = {"date": datetime.now().strftime("%Y-%m-%d"),
                                    "code": next((c for c, it in data["inventory"].items() if it.get("name")==item_name), "-"),
                                    "item": item_name, "qty": qty, "unit": unit_name,
                                    "event": event_choice, "user": st.session_state.username}
                            st.session_state.req_ret_items.append(normalize_return_record(base))
                            st.success("Item Retur ditambahkan ke daftar.")

                with tab2:
                    st.info("Format: **Tanggal | Kode Barang | Nama Barang | Qty | Event**")
                    st.download_button(
                        label="📥 Unduh Template Excel Retur",
                        data=make_return_template_bytes(data),
                        file_name=f"Template_Retur_{st.session_state.current_brand.capitalize()}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    file_upload = st.file_uploader("Upload File Excel Retur", type=["xlsx"], key="ret_excel_uploader")
                    if file_upload:
                        try:
                            df_new = pd.read_excel(file_upload, engine='openpyxl')
                        except Exception as e:
                            st.error(f"Gagal membaca file Excel: {e}")
                            df_new = None

                        required_cols = ["Tanggal", "Kode Barang", "Nama Barang", "Qty", "Event"]
                        if df_new is not None:
                            missing = [c for c in required_cols if c not in df_new.columns]
                            if missing:
                                st.error(f"Kolom berikut belum ada di Excel: {', '.join(missing)}")
                            else:
                                if st.button("Tambah dari Excel (Retur)"):
                                    errors, added = [], 0
                                    by_code = {code: (it.get("name"), it.get("unit", "-")) for code, it in data["inventory"].items()}
                                    by_name = {it.get("name"): (code, it.get("unit", "-")) for code, it in data["inventory"].items()}
                                    for idx_row, row in df_new.iterrows():
                                        try:
                                            dt = pd.to_datetime(row["Tanggal"], errors="coerce")
                                            date_str = dt.strftime("%Y-%m-%d") if pd.notna(dt) else datetime.now().strftime("%Y-%m-%d")
                                            code_xl = str(row["Kode Barang"]).strip() if pd.notna(row["Kode Barang"]) else ""
                                            name_xl = str(row["Nama Barang"]).strip() if pd.notna(row["Nama Barang"]) else ""
                                            qty_xl = int(pd.to_numeric(row["Qty"], errors="coerce") or 0)
                                            event_xl_raw = str(row["Event"]).strip() if pd.notna(row["Event"]) else ""
                                            if qty_xl <= 0: errors.append(f"Baris {idx_row+2}: Qty harus > 0."); continue
                                            if not event_xl_raw: errors.append(f"Baris {idx_row+2}: Event wajib diisi."); continue

                                            inv_name, inv_unit = (None, None); inv_code = None
                                            if code_xl and code_xl in by_code: inv_name, inv_unit = by_code[code_xl]; inv_code = code_xl
                                            elif name_xl and name_xl in by_name: inv_code, inv_unit = by_name[name_xl]; inv_name = name_xl
                                            else: errors.append(f"Baris {idx_row+2}: Item tidak ditemukan."); continue

                                            valid_events = approved_out_map.get(inv_name, set())
                                            exists = any(e.strip().lower() == event_xl_raw.strip().lower() for e in valid_events)
                                            if not exists:
                                                if not valid_events:
                                                    errors.append(f"Baris {idx_row+2}: Belum ada event OUT yang di-approve untuk '{inv_name}'.")
                                                else:
                                                    errors.append(f"Baris {idx_row+2}: Event '{event_xl_raw}' tidak cocok. Tersedia: {', '.join(sorted(valid_events))}.")
                                                continue

                                            base = {"date": date_str, "code": inv_code if inv_code else "-",
                                                    "item": inv_name, "qty": qty_xl, "unit": inv_unit if inv_unit else "-",
                                                    "event": next((e for e in valid_events if e.strip().lower()==event_xl_raw.strip().lower()), event_xl_raw),
                                                    "user": st.session_state.username}
                                            st.session_state.req_ret_items.append(normalize_return_record(base)); added += 1
                                        except Exception as e:
                                            errors.append(f"Baris {idx_row+2}: {e}")
                                    if added: st.success(f"{added} baris retur ditambahkan.")
                                    if errors: st.warning("Beberapa baris gagal:\n- " + "\n- ".join(errors))

                if st.session_state.req_ret_items:
                    st.subheader("Daftar Item Request Retur")
                    if "ret_select_flags" not in st.session_state or len(st.session_state.ret_select_flags) != len(st.session_state.req_ret_items):
                        st.session_state.ret_select_flags = [False]*len(st.session_state.req_ret_items)

                    cR1, cR2 = st.columns([1,1])
                    if cR1.button("Pilih semua", key="ret_sel_all"): st.session_state.ret_select_flags = [True]*len(st.session_state.req_ret_items)
                    if cR2.button("Kosongkan pilihan", key="ret_sel_none"): st.session_state.ret_select_flags = [False]*len(st.session_state.req_ret_items)

                    df_ret = pd.DataFrame(st.session_state.req_ret_items)
                    pref_cols = [c for c in ["date","code","item","qty","unit","event"] if c in df_ret.columns]
                    df_ret = df_ret[pref_cols]; df_ret["Pilih"] = st.session_state.ret_select_flags
                    edited_df_ret = st.data_editor(df_ret, key="editor_ret", use_container_width=True, hide_index=True)
                    st.session_state.ret_select_flags = edited_df_ret["Pilih"].fillna(False).tolist()

                    if st.button("Hapus Item Terpilih", key="delete_ret"):
                        mask = st.session_state.ret_select_flags
                        if any(mask):
                            st.session_state.req_ret_items = [rec for rec, keep in zip(st.session_state.req_ret_items, [not x for x in mask]) if keep]
                            st.session_state.ret_select_flags = [False]*len(st.session_state.req_ret_items)
                            st.rerun()
                        else:
                            st.info("Tidak ada baris yang dipilih.")

                    st.divider()
                    if st.button("Ajukan Request Retur Terpilih"):
                        mask = st.session_state.ret_select_flags
                        if not any(mask):
                            st.warning("Pilih setidaknya satu item untuk diajukan.")
                        else:
                            for selected, rec in zip(mask, st.session_state.req_ret_items):
                                if selected:
                                    base = rec.copy(); base["user"] = st.session_state.username
                                    norm = normalize_return_record(base); norm["type"] = "RETURN"
                                    data["pending_requests"].append(norm)
                            save_data(data, st.session_state.current_brand)
                            st.session_state.req_ret_items = [rec for rec, keep in zip(st.session_state.req_ret_items, [not x for x in mask]) if keep]
                            st.session_state.ret_select_flags = [False]*len(st.session_state.req_ret_items)
                            st.success("Request RETUR diajukan & menunggu approval.")
                            st.rerun()
            else:
                st.info("Belum ada master barang. Silakan hubungi admin.")

        # ----- Lihat Riwayat (User) dengan Status -----
        elif menu == "Lihat Riwayat":
            st.markdown(f"## Riwayat Saya (dengan Status) - Brand {st.session_state.current_brand.capitalize()}")
            st.divider()

            hist = data.get("history", [])
            my_hist = [h for h in hist if h.get("user") == st.session_state.username and isinstance(h.get("action",""), str)]
            rows = []
            for h in my_hist:
                act = h["action"].upper()
                if act.startswith("APPROVE_"):
                    status = "APPROVED"; ttype = act.split("_", 1)[-1]
                elif act.startswith("REJECT_"):
                    status = "REJECTED"; ttype = act.split("_", 1)[-1]
                elif act.startswith("ADD_"):
                    status = "-"; ttype = "ADD"
                else:
                    status = "-"; ttype = "-"
                rows.append({
                    "Status": status, "Type": ttype, "Date": h.get("date", None), "Code": h.get("code","-"),
                    "Item": h.get("item","-"), "Qty": h.get("qty","-"), "Unit": h.get("unit","-"),
                    "Trans. Tipe": h.get("trans_type","-"), "Event": h.get("event","-"),
                    "DO": h.get("do_number","-"), "Timestamp": h.get("timestamp","-")
                })

            pend = data.get("pending_requests", [])
            my_pend = [p for p in pend if p.get("user") == st.session_state.username]
            for p in my_pend:
                rows.append({
                    "Status": "PENDING", "Type": p.get("type","-"), "Date": p.get("date", None), "Code": p.get("code","-"),
                    "Item": p.get("item","-"), "Qty": p.get("qty","-"), "Unit": p.get("unit","-"),
                    "Trans. Tipe": p.get("trans_type","-"), "Event": p.get("event","-"),
                    "DO": p.get("do_number","-"), "Timestamp": p.get("timestamp","-")
                })

            if rows:
                df_rows = pd.DataFrame(rows)
                try:
                    df_rows["ts"] = pd.to_datetime(df_rows["Timestamp"], errors="coerce")
                    df_rows = df_rows.sort_values("ts", ascending=False).drop(columns=["ts"])
                except Exception:
                    pass
                st.dataframe(df_rows, use_container_width=True, hide_index=True)
            else:
                st.info("Anda belum memiliki riwayat transaksi.")

