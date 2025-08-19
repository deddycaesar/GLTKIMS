# app.py
import streamlit as st
import json, os, base64, requests, shutil
from io import BytesIO
from datetime import datetime, date
import pandas as pd

# ====== Konfigurasi dasar ======
DATA_FILES = {
    "gulavit": "gulavit_data.json",
    "takokak": "takokak_data.json"
}
UPLOADS_DIR = "uploads"
BANNER_URL = "https://media.licdn.com/dms/image/v2/D563DAQFDri8xlKNIvg/image-scale_191_1128/image-scale_191_1128/0/1678337293506/pesona_inti_rasa_cover?e=2147483647&v=beta&t=vHi0xtyAZsT9clHb0yBYPE8M9IaO2dNY6Cb_Vs3Ddlo"
ICON_URL = "https://i.ibb.co/7C96T9y/favicon.png"

os.makedirs(UPLOADS_DIR, exist_ok=True)

# ==== Storage via Google Apps Script (tanpa Google Cloud) ====
USE_APPS_SCRIPT = FALSE  # aktifkan mode GAS
GAS_TOKEN = st.secrets.get("apps_script", {}).get("token", "CHANGE_ME")

# Opsi 1 (2 URL terpisah): isi gulavit_url & takokak_url di Secrets
# Opsi 2 (1 URL multi-brand): isi 'url' di Secrets (lihat fungsi load/save untuk kirim param brand)
GAS_ENDPOINTS = {
    "gulavit": st.secrets.get("apps_script", {}).get("gulavit_url") or st.secrets.get("apps_script", {}).get("url", "PASTE_URL"),
    "takokak": st.secrets.get("apps_script", {}).get("takokak_url") or st.secrets.get("apps_script", {}).get("url", "PASTE_URL"),
}

# ====== UI ======
st.set_page_config(page_title="Inventory System", page_icon=ICON_URL, layout="wide")
st.markdown("""
<style>
.main { background-color: #F5F5F5; }
h1, h2, h3 { color: #FF781F; }
.stButton>button {
  background-color: #34A853; color: white; border-radius: 8px; height: 3em; width: 100%; border: none;
}
.stButton>button:hover { background-color: #4CAF50; color: white; }
.smallcap { font-size: 12px; color:#6b7280; text-transform: uppercase; letter-spacing:.08em; margin-bottom:6px; }
.card { background:#fff; padding:14px 14px 8px; border-radius:12px; box-shadow: 0 1px 3px rgba(0,0,0,.08); margin-bottom:12px;}
.kpi {
  background:linear-gradient(180deg,#fff, #f8fafc);
  border:1px solid #e5e7eb; border-radius:12px; padding:14px 16px; margin-bottom:12px;
}
.kpi .title { font-size:12px; color:#6b7280; text-transform:uppercase; letter-spacing:.08em; }
.kpi .value { font-size:24px; font-weight:700; color:#111827; }
</style>
""", unsafe_allow_html=True)

# ====== Utilities ======
def timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def today_str():
    return datetime.now().strftime("%Y-%m-%d")

def _ensure_defaults(data: dict) -> dict:
    data.setdefault("users", {})
    data.setdefault("inventory", {})
    data.setdefault("item_counter", 0)
    data.setdefault("pending_requests", [])
    data.setdefault("history", [])
    for _, it in data["inventory"].items():
        it.setdefault("unit", "-")
        it.setdefault("category", "Uncategorized")
        it["qty"] = int(pd.to_numeric(it.get("qty", 0), errors="coerce") or 0)
    return data

def _kpi_card(title, value, caption=None):
    st.markdown(f"""<div class="kpi">
      <div class="title">{title}</div>
      <div class="value">{value}</div>
      {"<div class='smallcap'>"+caption+"</div>" if caption else ""}
    </div>""", unsafe_allow_html=True)

def _prepare_history_df(data: dict):
    """Normalisasi riwayat -> kolom:
       date_eff (datetime), type_norm (IN/OUT/RETURN), qty, item, event, trans_type
    """
    hist = data.get("history", [])
    if not hist:
        return pd.DataFrame(columns=["date_eff","type_norm","qty","item","event","trans_type"])

    df = pd.DataFrame(hist)
    # tanggal efektif
    if "date" in df.columns:
        df["date_eff"] = pd.to_datetime(df["date"], errors="coerce")
    else:
        df["date_eff"] = pd.NaT

    if "timestamp" in df.columns:
        ts = pd.to_datetime(df["timestamp"], errors="coerce")
        df["date_eff"] = df["date_eff"].fillna(ts.dt.date.astype("datetime64[ns]"))

    # type_norm
    df["action"] = df["action"].fillna("")
    def _tn(a):
        if str(a).startswith("APPROVE_IN") or a == "ADD_ITEM": return "IN"
        if str(a).startswith("APPROVE_OUT"): return "OUT"
        if str(a).startswith("APPROVE_RETURN"): return "RETURN"
        return None
    df["type_norm"] = df["action"].apply(_tn)

    # angka
    df["qty"] = pd.to_numeric(df.get("qty", 0), errors="coerce").fillna(0).astype(int)
    # kolom lain
    for col in ["item","event","trans_type"]:
        if col not in df.columns: df[col] = None
    return df

def _unique_out_events(data: dict):
    """Ambil daftar event dari OUT (yang sudah APPROVE) untuk dropdown retur & validasi excel"""
    hist = data.get("history", [])
    events = []
    for h in hist:
        if str(h.get("action","")).startswith("APPROVE_OUT"):
            ev = (h.get("event") or "").strip()
            if ev and ev != "-":
                events.append(ev)
    # unik, pertahankan urutan
    seen = set(); uniq=[]
    for e in events:
        k=e.lower()
        if k not in seen:
            uniq.append(e); seen.add(k)
    return uniq

# ====== Apps Script IO ======
def load_data_apps_script(brand_key):
    url = GAS_ENDPOINTS.get(brand_key)
    if not url or "http" not in url:
        raise RuntimeError(f"GAS endpoint brand '{brand_key}' belum diisi.")
    try:
        # Jika endpoint-mu multi-brand, backend membaca param brand; kalau per-brand, param brand diabaikan (nggak masalah)
        r = requests.get(url, params={"token": GAS_TOKEN, "brand": brand_key}, timeout=20)
        r.raise_for_status()
        resp = r.json()
        if not resp.get("ok"):
            raise RuntimeError(resp.get("error","unknown error"))
        data = resp.get("data", {})
        return _ensure_defaults(data)
    except Exception as e:
        st.warning(f"Gagal load dari Sheets (Apps Script): {e}")
        raise

def save_data_apps_script(data, brand_key):
    url = GAS_ENDPOINTS.get(brand_key)
    if not url or "http" not in url:
        st.warning(f"GAS endpoint brand '{brand_key}' belum diisi.")
        return
    try:
        payload = {"token": GAS_TOKEN, "brand": brand_key, "data": data}
        r = requests.post(url, json=payload, timeout=25)
        if r.status_code != 200:
            st.warning(f"GAS HTTP {r.status_code}: {r.text[:200]}")
        else:
            resp = r.json()
            if not resp.get("ok", False):
                st.warning(f"GAS error: {resp.get('error')}")
    except Exception as e:
        st.warning(f"Gagal push ke Sheets (Apps Script): {e}")

def load_data(brand_key):
    # 1) Utama: Apps Script (persisten)
    if USE_APPS_SCRIPT:
        try:
            data = load_data_apps_script(brand_key)
            if not data.get("users"):
                # default users jika sheet kosong
                data["users"] = {
                    "admin": {"password": st.secrets.get("passwords", {}).get("admin"), "role": "admin"},
                    "user":  {"password": st.secrets.get("passwords", {}).get("user"),  "role": "user"},
                }
            return _ensure_defaults(data)
        except Exception:
            pass
    # 2) Fallback lokal
    data_file = DATA_FILES[brand_key]
    if os.path.exists(data_file):
        try:
            with open(data_file, "r") as f:
                data = json.load(f)
            return _ensure_defaults(data)
        except Exception:
            pass
    # 3) default baru
    return _ensure_defaults({
        "users": {
            "admin": {"password": st.secrets.get("passwords", {}).get("admin"), "role": "admin"},
            "user":  {"password": st.secrets.get("passwords", {}).get("user"),  "role": "user"},
        },
        "inventory": {},
        "item_counter": 0,
        "pending_requests": [],
        "history": [],
    })

def save_data(data, brand_key):
    data = _ensure_defaults(data)
    # simpan lokal (cache)
    try:
        with open(DATA_FILES[brand_key], "w") as f:
            json.dump(data, f, indent=4)
    except Exception:
        pass
    # sinkron ke Sheets
    if USE_APPS_SCRIPT:
        save_data_apps_script(data, brand_key)

# ====== Template Excel ======
def make_excel_bytes(df_dict: dict, filename="export.xlsx"):
    xls = BytesIO()
    with pd.ExcelWriter(xls, engine="xlsxwriter") as wr:
        for sheetname, df in df_dict.items():
            df.to_excel(wr, index=False, sheet_name=sheetname)
    xls.seek(0)
    return xls

def download_template_button(label, df, filename):
    data = make_excel_bytes({"Template": df}).read()
    st.download_button(label, data=data, file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ====== Dashboard ======
try:
    import altair as alt
    _ALT_OK = True
except Exception:
    _ALT_OK = False

def render_dashboard_pro(data: dict, brand_label: str, allow_download=True):
    df_hist = _prepare_history_df(data)
    inv_records = [
        {"Kode": code, "Nama Barang": it.get("name","-"), "Current Stock": int(it.get("qty",0)), "Unit": it.get("unit","-")}
        for code, it in data.get("inventory", {}).items()
    ]
    df_inv = pd.DataFrame(inv_records)

    st.markdown(f"## Dashboard — {brand_label}")
    st.caption("Semua metrik berbasis jumlah (qty). *Sales* = OUT tipe **Penjualan**.")
    st.divider()

    today = pd.Timestamp.today().normalize()
    default_start = (today - pd.DateOffset(months=11)).replace(day=1)
    colF1, colF2 = st.columns(2)
    start_date = colF1.date_input("Tanggal mulai", value=default_start.date())
    end_date   = colF2.date_input("Tanggal akhir", value=today.date())

    if not df_hist.empty:
        mask = (df_hist["date_eff"] >= pd.Timestamp(start_date)) & (df_hist["date_eff"] <= pd.Timestamp(end_date))
        df_range = df_hist.loc[mask].copy()
    else:
        df_range = pd.DataFrame(columns=["date_eff","type_norm","qty","item","event","trans_type"])

    # KPI
    total_sku = int(len(df_inv)) if not df_inv.empty else 0
    total_qty = int(df_inv["Current Stock"].sum()) if not df_inv.empty else 0
    tot_in  = int(df_range.loc[df_range["type_norm"]=="IN", "qty"].sum()) if not df_range.empty else 0
    tot_out = int(df_range.loc[df_range["type_norm"]=="OUT", "qty"].sum()) if not df_range.empty else 0
    tot_ret = int(df_range.loc[df_range["type_norm"]=="RETURN", "qty"].sum()) if not df_range.empty else 0

    k1, k2, k3, k4 = st.columns(4)
    with k1: _kpi_card("Total SKU", f"{total_sku:,}", f"Brand {brand_label}")
    with k2: _kpi_card("Total Qty (Stock)", f"{total_qty:,}", f"Per {pd.Timestamp(end_date).strftime('%d %b %Y')}")
    with k3: _kpi_card("Total IN (periode)", f"{tot_in:,}")
    with k4: _kpi_card("Total OUT / Retur", f"{tot_out:,} / {tot_ret:,}")

    st.divider()

    def month_agg(df, tipe):
        d = df[df["type_norm"]==tipe].copy()
        if d.empty:
            return pd.DataFrame({"month": [], "qty": [], "Periode": [], "idx": []})
        d["month"] = d["date_eff"].dt.to_period("M").dt.to_timestamp()
        g = d.groupby("month", as_index=False)["qty"].sum().sort_values("month")
        g["Periode"] = g["month"].dt.strftime("%b %Y")
        g["idx"] = g["month"].dt.year.astype(int) * 12 + g["month"].dt.month.astype(int)
        return g

    g_in  = month_agg(df_range, "IN")
    g_out = month_agg(df_range, "OUT")
    g_ret = month_agg(df_range, "RETURN")

    c1, c2, c3 = st.columns(3)
    def _month_bar(container, dfm, title, color="#0EA5E9"):
        with container:
            st.markdown(f'<div class="card"><div class="smallcap">{title}</div>', unsafe_allow_html=True)
            if _ALT_OK and not dfm.empty:
                chart = (
                    alt.Chart(dfm)
                    .mark_bar(size=28)
                    .encode(
                        x=alt.X("Periode:O", sort=alt.SortField(field="idx", order="ascending"), title="Periode"),
                        y=alt.Y("qty:Q", title="Qty"),
                        tooltip=[alt.Tooltip("month:T", title="Periode", format="%b %Y"), "qty:Q"],
                        color=alt.value(color)
                    ).properties(height=320)
                )
                st.altair_chart(chart, use_container_width=True)
            else:
                if dfm.empty: st.info("Belum ada data.")
                else: st.bar_chart(dfm.set_index("Periode")["qty"])
            st.markdown("</div>", unsafe_allow_html=True)

    _month_bar(c1, g_in,  "IN per Month",    "#22C55E")
    _month_bar(c2, g_out, "OUT per Month",   "#EF4444")
    _month_bar(c3, g_ret, "RETUR per Month", "#0EA5E9")

    st.divider()

    t1, t2 = st.columns(2)
    with t1:
        st.markdown('<div class="card"><div class="smallcap">Top 10 Items (Current Stock)</div>', unsafe_allow_html=True)
        if not df_inv.empty:
            top10 = df_inv.sort_values("Current Stock", ascending=False).head(10)
            if _ALT_OK:
                import altair as alt
                chart = (
                    alt.Chart(top10)
                    .mark_bar(size=22)
                    .encode(
                        y=alt.Y("Nama Barang:N", sort="-x", title=None),
                        x=alt.X("Current Stock:Q", title="Qty"),
                        tooltip=["Nama Barang","Current Stock"]
                    ).properties(height=360)
                )
                st.altair_chart(chart, use_container_width=True)
            else:
                st.dataframe(top10, use_container_width=True, hide_index=True)
        else:
            st.info("Inventory kosong.")
        st.markdown("</div>", unsafe_allow_html=True)

    with t2:
        st.markdown('<div class="card"><div class="smallcap">Top 5 Event by OUT Qty</div>', unsafe_allow_html=True)
        df_ev = df_range[(df_range["type_norm"]=="OUT") & (df_range["event"].notna())].copy()
        df_ev = df_ev[df_ev["event"].astype(str).str.strip().ne("-")]
        ev_top = (df_ev.groupby("event", as_index=False)["qty"].sum()
                  .sort_values("qty", ascending=False).head(5))
        if not ev_top.empty and _ALT_OK:
            chart = (
                alt.Chart(ev_top)
                .mark_bar(size=22)
                .encode(
                    y=alt.Y("event:N", sort="-x", title="Event"),
                    x=alt.X("qty:Q", title="Qty"),
                    tooltip=["event","qty"]
                ).properties(height=360)
            )
            st.altair_chart(chart, use_container_width=True)
        elif ev_top.empty:
            st.info("Belum ada OUT pada rentang ini.")
        else:
            st.dataframe(ev_top.rename(columns={"event":"Event","qty":"Qty"}), use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

    st.divider()

    st.subheader("Reorder Insight (berdasarkan OUT 3 bulan terakhir)")
    st.caption("Days of Cover ≈ stok saat ini / rata-rata pemakaian harian (OUT 3 bulan terakhir).")
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
            doc = stock / avg_daily
        else:
            doc = float("inf")

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
        xbytes = make_excel_bytes({"Reorder Insight": df_reorder}).read()
        st.download_button("Unduh Excel Reorder Insight", data=xbytes,
                           file_name=f"Reorder_{brand_label.replace(' ','_')}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

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

# ====== LOGIN ======
if not st.session_state.logged_in:
    st.image(BANNER_URL, use_container_width=True)
    st.markdown("<div style='text-align:center;'><h1 style='margin-top:10px; color:#FF781F;'>Inventory Management System</h1></div>", unsafe_allow_html=True)
    st.subheader("Silakan Login")

    username = st.text_input("Username", placeholder="Masukkan username")
    password = st.text_input("Password", type="password", placeholder="Masukkan password")

    if st.button("Login"):
        data_login = load_data("gulavit")  # ambil user dari salah satu brand
        user = data_login["users"].get(username)
        if user and user["password"] == password:
            st.session_state.logged_in = True
            st.session_state.username = username
            st.session_state.role = user["role"]
            st.success(f"Login berhasil sebagai {user['role'].upper()}")
            st.rerun()
        else:
            st.error("❌ Username atau password salah.")
    st.stop()

# ====== MAIN APP ======
role = st.session_state.role
st.image(BANNER_URL, use_container_width=True)

# Sidebar
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

# Notification
if st.session_state.notification:
    nt = st.session_state.notification
    if nt["type"] == "success": st.success(nt["message"])
    elif nt["type"] == "warning": st.warning(nt["message"])
    elif nt["type"] == "error": st.error(nt["message"])
    st.session_state.notification = None

# ====== MENU ADMIN / USER ======
if role == "admin":
    admin_options = [
        "Dashboard",
        "Lihat Stok Barang",
        "Stock Card",
        "Tambah Master Barang",
        "Approve Request",
        "Riwayat Lengkap",
        "Export Laporan ke Excel",
        "Reset Database",
    ]
    menu = st.sidebar.radio("📌 Menu Admin", admin_options)

    if menu == "Dashboard":
        render_dashboard_pro(data, st.session_state.current_brand.capitalize(), allow_download=True)

    elif menu == "Lihat Stok Barang":
        st.markdown(f"## Stok Barang - Brand {st.session_state.current_brand.capitalize()}")
        st.divider()
        if data["inventory"]:
            df_inventory = pd.DataFrame([
                {"Kode": code, "Nama Barang": item["name"], "Qty": item["qty"], "Satuan": item.get("unit","-"), "Kategori": item.get("category","Uncategorized")}
                for code, item in data["inventory"].items()
            ])
            unique_categories = ["Semua Kategori"] + sorted(df_inventory["Kategori"].unique())
            selected_category = st.selectbox("Pilih Kategori", unique_categories)
            search_query = st.text_input("Cari Nama/Kode")
            df_filtered = df_inventory.copy()
            if selected_category != "Semua Kategori":
                df_filtered = df_filtered[df_filtered["Kategori"] == selected_category]
            if search_query:
                df_filtered = df_filtered[df_filtered["Nama Barang"].str.contains(search_query, case=False) | df_filtered["Kode"].str.contains(search_query, case=False)]
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
            selected_item_name = st.selectbox("Pilih Barang", item_names)
            if selected_item_name:
                filtered_history = [h for h in data["history"] if h.get("item")==selected_item_name and (h["action"].startswith("APPROVE") or h["action"]=="ADD_ITEM")]
                if filtered_history:
                    stock_card_data = []
                    current_balance = 0
                    sorted_history = sorted(filtered_history, key=lambda x: x.get("timestamp") or x.get("date") or "")
                    for h in sorted_history:
                        inn, out, ket = 0, 0, "N/A"
                        if h["action"] == "ADD_ITEM":
                            inn = h["qty"]; current_balance += inn; ket = "Initial Stock"
                        elif h["action"] == "APPROVE_IN":
                            inn = h["qty"]; current_balance += inn; ket = f"Request IN by {h['user']}"
                            do_number = h.get('do_number', '-')
                            if do_number and do_number!='-': ket += f" (DO: {do_number})"
                        elif h["action"] == "APPROVE_OUT":
                            out = h["qty"]; current_balance -= out; ket = f"Request OUT by {h['user']} (Event: {h.get('event','-')})"
                        elif h["action"] == "APPROVE_RETURN":
                            inn = h["qty"]; current_balance += inn; ket = f"RETUR by {h['user']} (Event: {h.get('event','-')})"
                        else:
                            continue
                        stock_card_data.append({
                            "Tanggal": h.get("date") or (h.get("timestamp","")[:10]),
                            "Keterangan": ket,
                            "Masuk (IN)": inn if inn>0 else "-",
                            "Keluar (OUT)": out if out>0 else "-",
                            "Saldo Akhir": current_balance
                        })
                    st.dataframe(pd.DataFrame(stock_card_data), use_container_width=True, hide_index=True)
                else:
                    st.info("Tidak ada riwayat transaksi disetujui untuk barang ini.")

    elif menu == "Tambah Master Barang":
        st.markdown(f"## Tambah Master Barang - Brand {st.session_state.current_brand.capitalize()}")
        st.divider()
        tab1, tab2 = st.tabs(["Input Manual", "Upload Excel"])
        with tab1:
            code = st.text_input("Kode Barang (unik)", placeholder="misal: ITM-0001")
            name = st.text_input("Nama Barang")
            unit = st.text_input("Satuan (pcs, box, liter, dst.)")
            qty = st.number_input("Jumlah Stok Awal", min_value=0, step=1)
            category = st.text_input("Kategori Barang", placeholder="Misal: Minuman, Makanan")

            if st.button("Tambah Barang Manual"):
                if not code or not name or not unit or category is None:
                    st.session_state.notification = {"type":"error","message":"Semua input wajib diisi."}
                    st.rerun()
                if code in data["inventory"]:
                    st.session_state.notification = {"type":"error","message":f"Kode {code} sudah ada."}
                    st.rerun()
                data["inventory"][code] = {"name": name, "qty": int(qty), "unit": unit, "category": category or "Uncategorized"}
                data["history"].append({
                    "action":"ADD_ITEM","item":name,"qty":int(qty),"stock":int(qty),"unit":unit,
                    "user": st.session_state.username,"event":"-","do_number":"-","attachment":None,
                    "timestamp": timestamp(),"date": today_str(),"code": code,"trans_type": None
                })
                save_data(data, st.session_state.current_brand)
                st.session_state.notification = {"type":"success","message": f"Barang '{name}' ({code}) berhasil ditambahkan."}
                st.rerun()

        with tab2:
            st.info("Format Excel: **Code | Nama Barang | Qty | Satuan | Kategori**")
            # Unduh template
            tpl = pd.DataFrame([{"Code":"ITM-0001","Nama Barang":"Contoh A","Qty":100,"Satuan":"pcs","Kategori":"Minuman"}])
            download_template_button("Unduh Template Master (Excel)", tpl, "Template_Master.xlsx")
            file_upload = st.file_uploader("Upload File Excel", type=["xlsx"])
            if file_upload and st.button("Tambah dari Excel"):
                df_new = pd.read_excel(file_upload, engine='openpyxl')
                required_cols = ["Code","Nama Barang","Qty","Satuan","Kategori"]
                if not all(col in df_new.columns for col in required_cols):
                    st.error("Format Excel salah! Pastikan kolom: Code | Nama Barang | Qty | Satuan | Kategori")
                else:
                    errors = []
                    for _, row in df_new.iterrows():
                        code = str(row["Code"]).strip()
                        name = str(row["Nama Barang"]).strip()
                        if not code or not name:
                            errors.append(f"Baris {int(_)+2}: Code/Nama kosong.")
                            continue
                        if code in data["inventory"]:
                            errors.append(f"Baris {int(_)+2}: Code {code} duplikat.")
                            continue
                        qty  = int(pd.to_numeric(row["Qty"], errors="coerce") or 0)
                        unit = str(row["Satuan"]).strip() or "-"
                        category = str(row["Kategori"]).strip() or "Uncategorized"
                        data["inventory"][code] = {"name": name, "qty": qty, "unit": unit, "category": category}
                        data["history"].append({
                            "action":"ADD_ITEM","item":name,"qty":qty,"stock":qty,"unit":unit,
                            "user": st.session_state.username,"event":"-","do_number":"-","attachment":None,
                            "timestamp": timestamp(),"date": today_str(),"code": code,"trans_type": None
                        })
                    save_data(data, st.session_state.current_brand)
                    if errors:
                        st.warning("Beberapa baris tidak diimport:\n- " + "\n- ".join(errors))
                    else:
                        st.success("Semua barang dari Excel berhasil ditambahkan.")

    elif menu == "Approve Request":
        st.markdown(f"## Approve / Reject Request - Brand {st.session_state.current_brand.capitalize()}")
        st.divider()
        if data["pending_requests"]:
            processed = []
            for req in data["pending_requests"]:
                tmp = req.copy()
                tmp.setdefault("attachment", None)
                processed.append(tmp)
            df_pending = pd.DataFrame(processed)
            if not df_pending.empty:
                df_display = df_pending.copy()
                df_display["Lampiran"] = df_display["attachment"].apply(lambda x: "Ada" if x else "Tidak Ada")
                # Select all
                select_all = st.checkbox("Pilih semua")
                df_display["Pilih"] = select_all
                edited = st.data_editor(df_display, use_container_width=True, hide_index=True)
                selected = edited.loc[(edited['Pilih']), :]

                col1, col2 = st.columns(2)
                if col1.button("Approve Selected"):
                    if selected.empty:
                        st.session_state.notification = {"type":"warning","message":"Pilih setidaknya satu item."}
                        st.rerun()
                    # Approve
                    for _, req in selected.iterrows():
                        # cari original by timestamp & user & item
                        match_idx = next((i for i, r in enumerate(data["pending_requests"])
                            if r["timestamp"]==req["timestamp"] and r["user"]==req["user"] and r["item"]==req["item"]), None)
                        if match_idx is None: continue
                        approved = data["pending_requests"].pop(match_idx)
                        # update stok
                        for code, item in data["inventory"].items():
                            if item["name"] == approved["item"]:
                                if approved["type"] == "IN":
                                    item["qty"] += approved["qty"]
                                elif approved["type"] == "OUT":
                                    item["qty"] -= approved["qty"]
                                elif approved["type"] == "RETURN":
                                    item["qty"] += approved["qty"]
                                # history
                                data["history"].append({
                                    "action": f"APPROVE_{approved['type']}",
                                    "item": approved["item"],
                                    "qty": approved["qty"],
                                    "stock": item["qty"],
                                    "unit": item.get("unit","-"),
                                    "user": approved["user"],
                                    "event": approved.get("event","-"),
                                    "do_number": approved.get("do_number","-"),
                                    "attachment": approved.get("attachment"),
                                    "timestamp": timestamp(),
                                    # penting: simpan 'date' dari request agar dashboard berbasis tanggal (bukan timestamp)
                                    "date": approved.get("date") or today_str(),
                                    "code": approved.get("code"),
                                    "trans_type": approved.get("trans_type")
                                })
                    save_data(data, st.session_state.current_brand)
                    st.session_state.notification = {"type":"success","message":"Request terpilih berhasil di-approve."}
                    st.rerun()

                if col2.button("Reject Selected"):
                    if selected.empty:
                        st.session_state.notification = {"type":"warning","message":"Pilih setidaknya satu item."}
                        st.rerun()
                    original = data["pending_requests"].copy()
                    newpend=[]; rejected=0
                    for r in original:
                        is_sel = any((r["timestamp"]==sel["timestamp"] and r["user"]==sel["user"] and r["item"]==sel["item"]) for _, sel in selected.iterrows())
                        if is_sel:
                            rejected+=1
                            data["history"].append({
                                "action": f"REJECT_{r['type']}",
                                "item": r["item"],
                                "qty": r["qty"],
                                "stock": "-",
                                "unit": r.get("unit","-"),
                                "user": r["user"],
                                "event": r.get("event","-"),
                                "do_number": r.get("do_number","-"),
                                "attachment": r.get("attachment"),
                                "timestamp": timestamp(),
                                "date": r.get("date") or today_str(),
                                "code": r.get("code"),
                                "trans_type": r.get("trans_type")
                            })
                        else:
                            newpend.append(r)
                    data["pending_requests"]=newpend
                    save_data(data, st.session_state.current_brand)
                    st.session_state.notification = {"type":"success","message":f"{rejected} request terpilih berhasil di-reject."}
                    st.rerun()
            else:
                st.info("Tidak ada pending request.")
        else:
            st.info("Tidak ada pending request.")

    elif menu == "Riwayat Lengkap":
        st.markdown(f"## Riwayat Lengkap - Brand {st.session_state.current_brand.capitalize()}")
        st.divider()
        if data["history"]:
            all_keys = ["action","item","qty","stock","unit","user","event","do_number","attachment","timestamp","date","code","trans_type"]
            processed=[]
            for entry in data["history"]:
                row={k: entry.get(k, None) for k in all_keys}
                row["do_number"] = row.get("do_number") or "-"
                row["event"]     = row.get("event") or "-"
                row["unit"]      = row.get("unit") or "-"
                processed.append(row)
            df = pd.DataFrame(processed)
            df['date_eff'] = pd.to_datetime(df['date'], errors="coerce").dt.date
            col1, col2 = st.columns(2)
            start_date = col1.date_input("Tanggal Mulai", value=df['date_eff'].min() or date.today())
            end_date   = col2.date_input("Tanggal Akhir", value=df['date_eff'].max() or date.today())
            col3, col4, col5 = st.columns(3)
            unique_users = ["Semua Pengguna"] + sorted(df["user"].dropna().unique().tolist())
            selected_user = col3.selectbox("Filter Pengguna", unique_users)
            unique_actions = ["Semua Tipe"] + sorted(df["action"].dropna().unique().tolist())
            selected_action = col4.selectbox("Filter Tipe Aksi", unique_actions)
            search_item = col5.text_input("Cari Nama Barang")

            dff = df.copy()
            dff = dff[(dff['date_eff']>=start_date) & (dff['date_eff']<=end_date)]
            if selected_user != "Semua Pengguna":
                dff = dff[dff["user"]==selected_user]
            if selected_action != "Semua Tipe":
                dff = dff[dff["action"]==selected_action]
            if search_item:
                dff = dff[dff["item"].str.contains(search_item, case=False, na=False)]

            # kolom lampiran download (jika path lokal ada)
            def get_download_link(path):
                if path and os.path.exists(path):
                    with open(path, "rb") as f: b64 = base64.b64encode(f.read()).decode()
                    return f'<a href="data:application/pdf;base64,{b64}" download="{os.path.basename(path)}">Unduh</a>'
                return 'Tidak Ada'
            dff["Lampiran"] = dff["attachment"].apply(get_download_link)
            st.markdown(dff[["action","item","qty","unit","stock","user","do_number","event","date","timestamp","Lampiran","trans_type"]].to_html(escape=False), unsafe_allow_html=True)
        else:
            st.info("Belum ada riwayat.")

    elif menu == "Export Laporan ke Excel":
        st.markdown(f"## Filter & Unduh Laporan - Brand {st.session_state.current_brand.capitalize()}")
        st.divider()
        if data["inventory"]:
            df_inv = pd.DataFrame([
                {"Kode": code, "Nama Barang": it["name"], "Qty": it["qty"], "Satuan": it.get("unit","-"), "Kategori": it.get("category","Uncategorized")}
                for code, it in data["inventory"].items()
            ])
            unique_categories = ["Semua Kategori"] + sorted(df_inv["Kategori"].unique())
            selected_category = st.selectbox("Pilih Kategori", unique_categories)
            search_q = st.text_input("Cari Nama/Kode")
            dff = df_inv.copy()
            if selected_category!="Semua Kategori":
                dff = dff[dff["Kategori"]==selected_category]
            if search_q:
                dff = dff[dff["Nama Barang"].str.contains(search_q, case=False) | dff["Kode"].str.contains(search_q, case=False)]
            st.markdown("### Preview")
            st.dataframe(dff, use_container_width=True, hide_index=True)
            if not dff.empty:
                xbytes = make_excel_bytes({"Stok Barang": dff}).read()
                st.download_button("Unduh Laporan Excel", data=xbytes,
                    file_name=f"Laporan_Inventori_{st.session_state.current_brand.capitalize()}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            else:
                st.warning("Tidak ada data sesuai filter.")
        else:
            st.info("Tidak ada data untuk diexport.")

    elif menu == "Reset Database":
        st.markdown(f"## Reset Database - Brand {st.session_state.current_brand.capitalize()}")
        st.divider()
        st.warning("Aksi ini akan menghapus seluruh data inventori, request, dan riwayat untuk brand ini.")
        confirm = st.text_input("Ketik RESET untuk konfirmasi")
        if st.button("Reset Database") and confirm=="RESET":
            data = _ensure_defaults({
                "users": data.get("users", {}),
                "inventory": {},
                "item_counter": 0,
                "pending_requests": [],
                "history": [],
            })
            save_data(data, st.session_state.current_brand)
            st.session_state.notification = {"type":"success","message":"✅ Database berhasil direset!"}
            st.rerun()

else:  # ==== USER ====
    user_options = [
        "Dashboard",
        "Request Barang IN",
        "Request Barang OUT",
        "Request Retur",
        "Stock Card",
        "Lihat Riwayat",
    ]
    menu = st.sidebar.radio("📌 Menu User", user_options)

    items = list(data["inventory"].values())
    code2item = {code: it for code, it in data["inventory"].items()}
    name2code = {it["name"]: code for code, it in data["inventory"].items()}

    if menu == "Dashboard":
        render_dashboard_pro(data, st.session_state.current_brand.capitalize(), allow_download=True)

    elif menu == "Request Barang IN":
        st.markdown(f"## Request Barang Masuk (Manual) - Brand {st.session_state.current_brand.capitalize()}")
        st.divider()
        if not items:
            st.info("Belum ada master barang. Silakan hubungi admin.")
        else:
            col1, col2 = st.columns(2)
            idx = col1.selectbox("Pilih Barang", range(len(items)),
                                 format_func=lambda x: f"{items[x]['name']} (Stok: {items[x]['qty']} {items[x].get('unit','-')})")
            qty = col2.number_input("Jumlah", min_value=1, step=1)
            do_number = st.text_input("Nomor Surat Jalan (wajib)")
            uploaded_file = st.file_uploader("Upload PDF Delivery Order / Surat Jalan", type=["pdf"])
            if st.button("Tambah Item IN ke Daftar"):
                if not do_number.strip():
                    st.session_state.notification = {"type":"error","message":"Nomor Surat Jalan wajib diisi."}
                    st.rerun()
                st.session_state.req_in_items.append({
                    "code": name2code.get(items[idx]["name"]),
                    "item": items[idx]["name"],
                    "qty": int(qty),
                    "unit": items[idx].get("unit","-"),
                    "event": "-",
                    "do_number": do_number,
                    "attachment_file": uploaded_file,  # simpan sementara
                })

            if st.session_state.req_in_items:
                st.subheader("Daftar Item Request IN")
                df_in = pd.DataFrame([{
                    "Code": r["code"], "Nama Barang": r["item"], "Qty": r["qty"], "Unit": r["unit"], "DO": r["do_number"]
                } for r in st.session_state.req_in_items])
                select_all = st.checkbox("Pilih semua", key="sel_in_all")
                df_in["Pilih"] = select_all
                edited_df_in = st.data_editor(df_in, use_container_width=True, hide_index=True)
                selected_idx = edited_df_in.index[edited_df_in["Pilih"]].tolist()

                c1, c2 = st.columns(2)
                if c1.button("Hapus Item Terpilih") and selected_idx:
                    st.session_state.req_in_items = [r for i, r in enumerate(st.session_state.req_in_items) if i not in selected_idx]
                    st.rerun()

                if c2.button("Ajukan Request IN Terpilih"):
                    if not selected_idx:
                        st.session_state.notification = {"type":"warning","message":"Pilih setidaknya satu item."}
                        st.rerun()
                    for i in selected_idx:
                        req = st.session_state.req_in_items[i]
                        # simpan attachment ke disk (opsional)
                        attachment_path = None
                        if req.get("attachment_file"):
                            ts_str = datetime.now().strftime("%Y%m%d%H%M%S")
                            attachment_path = os.path.join(UPLOADS_DIR, f"{st.session_state.username}_{ts_str}.pdf")
                            with open(attachment_path, "wb") as f:
                                f.write(req["attachment_file"].getbuffer())

                        data["pending_requests"].append({
                            "type":"IN",
                            "date": today_str(),  # tanggal manual default = hari ini
                            "code": req["code"],
                            "item": req["item"],
                            "qty": int(req["qty"]),
                            "unit": req.get("unit","-"),
                            "event": "-",
                            "trans_type": None,
                            "do_number": req["do_number"],
                            "attachment": attachment_path,
                            "user": st.session_state.username,
                            "timestamp": timestamp(),
                        })
                    save_data(data, st.session_state.current_brand)
                    # buang yang dipilih
                    st.session_state.req_in_items = [r for i, r in enumerate(st.session_state.req_in_items) if i not in selected_idx]
                    st.session_state.notification = {"type":"success","message": "Request IN diajukan dan menunggu approval."}
                    st.rerun()

    elif menu == "Request Barang OUT":
        st.markdown(f"## Request Barang Keluar - Brand {st.session_state.current_brand.capitalize()}")
        st.divider()
        if not items:
            st.info("Belum ada master barang. Silakan hubungi admin.")
        else:
            tab1, tab2 = st.tabs(["Input Manual", "Upload Excel"])
            with tab1:
                col1, col2 = st.columns(2)
                idx = col1.selectbox("Pilih Barang", range(len(items)),
                                     format_func=lambda x: f"{items[x]['name']} (Stok: {items[x]['qty']} {items[x].get('unit','-')})")
                max_qty = items[idx]["qty"]
                qty = col2.number_input("Jumlah", min_value=1, max_value=max_qty if max_qty>0 else 1, step=1)
                event_name = st.text_input("Nama Event (wajib, gunakan event konsisten)")
                trans_type = st.selectbox("Tipe Transaksi (wajib)", ["Support", "Penjualan"])
                if st.button("Tambah Item OUT ke Daftar"):
                    if not event_name.strip() or not trans_type:
                        st.session_state.notification = {"type":"error","message":"Event & Tipe Transaksi wajib diisi."}
                        st.rerun()
                    st.session_state.req_out_items.append({
                        "date": today_str(),  # manual -> tanggal hari ini
                        "code": name2code.get(items[idx]["name"]),
                        "item": items[idx]["name"],
                        "qty": int(qty),
                        "unit": items[idx].get("unit","-"),
                        "event": event_name.strip(),
                        "trans_type": trans_type,
                    })

            with tab2:
                st.info("Format Excel: **Date | Code | Nama Barang | Qty | Event | TransType** (Date: yyyy-mm-dd)")
                tpl = pd.DataFrame([{"Date": today_str(),"Code":"ITM-0001","Nama Barang":"Contoh A","Qty":5,"Event":"Promo Mall","TransType":"Penjualan"}])
                download_template_button("Unduh Template OUT (Excel)", tpl, "Template_OUT.xlsx")
                file_upload = st.file_uploader("Upload File Excel OUT", type=["xlsx"], key="out_excel")
                if file_upload and st.button("Tambah dari Excel (OUT)"):
                    df_new = pd.read_excel(file_upload, engine='openpyxl')
                    required = ["Date","Code","Nama Barang","Qty","Event","TransType"]
                    if not all(c in df_new.columns for c in required):
                        st.error("Kolom wajib: Date | Code | Nama Barang | Qty | Event | TransType")
                    else:
                        errors=[]
                        for ridx, row in df_new.iterrows():
                            code = str(row["Code"]).strip()
                            name = str(row["Nama Barang"]).strip()
                            if code not in data["inventory"]:
                                errors.append(f"Baris {ridx+2}: Code {code} tidak ditemukan.")
                                continue
                            qty = int(pd.to_numeric(row["Qty"], errors="coerce") or 0)
                            if qty<=0:
                                errors.append(f"Baris {ridx+2}: Qty harus > 0.")
                                continue
                            ev = str(row["Event"]).strip()
                            tt = str(row["TransType"]).strip()
                            if tt not in ["Support","Penjualan"]:
                                errors.append(f"Baris {ridx+2}: TransType harus 'Support' atau 'Penjualan'.")
                                continue
                            try:
                                d = pd.to_datetime(str(row["Date"])).strftime("%Y-%m-%d")
                            except Exception:
                                d = today_str()
                            st.session_state.req_out_items.append({
                                "date": d,
                                "code": code,
                                "item": data["inventory"][code]["name"],
                                "qty": qty,
                                "unit": data["inventory"][code].get("unit","-"),
                                "event": ev,
                                "trans_type": tt
                            })
                        if errors:
                            st.warning("Sebagian baris gagal ditambahkan:\n- " + "\n- ".join(errors))
                        else:
                            st.success("Item dari Excel berhasil ditambahkan ke daftar request.")

            # Tabel daftar OUT
            if st.session_state.req_out_items:
                st.subheader("Daftar Item Request OUT")
                df_out = pd.DataFrame([{
                    "Tanggal": r["date"], "Code": r["code"], "Nama Barang": r["item"], "Qty": r["qty"], "Unit": r["unit"],
                    "Event": r["event"], "TransType": r["trans_type"]
                } for r in st.session_state.req_out_items])
                select_all = st.checkbox("Pilih semua", key="sel_out_all")
                df_out["Pilih"] = select_all
                edited_df_out = st.data_editor(df_out, use_container_width=True, hide_index=True)
                selected_idx = edited_df_out.index[edited_df_out["Pilih"]].tolist()

                c1, c2 = st.columns(2)
                if c1.button("Hapus Item Terpilih (OUT)") and selected_idx:
                    st.session_state.req_out_items = [r for i, r in enumerate(st.session_state.req_out_items) if i not in selected_idx]
                    st.rerun()
                if c2.button("Ajukan Request OUT Terpilih"):
                    if not selected_idx:
                        st.session_state.notification = {"type":"warning","message":"Pilih setidaknya satu item."}
                        st.rerun()
                    for i in selected_idx:
                        r = st.session_state.req_out_items[i]
                        data["pending_requests"].append({
                            "type":"OUT",
                            "date": r["date"],   # pakai tanggal dari daftar (manual=hari ini, excel=kolom Date)
                            "code": r["code"],
                            "item": r["item"],
                            "qty": int(r["qty"]),
                            "unit": r.get("unit","-"),
                            "event": r.get("event","-"),
                            "trans_type": r.get("trans_type"),
                            "do_number": "-",
                            "attachment": None,
                            "user": st.session_state.username,
                            "timestamp": timestamp()
                        })
                    save_data(data, st.session_state.current_brand)
                    st.session_state.req_out_items = [r for i, r in enumerate(st.session_state.req_out_items) if i not in selected_idx]
                    st.session_state.notification = {"type":"success","message":"Request OUT diajukan dan menunggu approval."}
                    st.rerun()

    elif menu == "Request Retur":
        st.markdown(f"## Request Retur - Brand {st.session_state.current_brand.capitalize()}")
        st.divider()
        events_out = _unique_out_events(data)
        if not items:
            st.info("Belum ada master barang.")
        elif not events_out:
            st.info("Belum ada event OUT yang disetujui. Retur mengacu pada event OUT.")
        else:
            tab1, tab2 = st.tabs(["Input Manual", "Upload Excel"])
            with tab1:
                col1, col2 = st.columns(2)
                idx = col1.selectbox("Pilih Barang", range(len(items)),
                                     format_func=lambda x: f"{items[x]['name']} (Stok: {items[x]['qty']} {items[x].get('unit','-')})")
                qty = col2.number_input("Jumlah", min_value=1, step=1)
                event_name = st.selectbox("Pilih Event (dari OUT)", options=events_out)
                if st.button("Tambah Item RETUR ke Daftar"):
                    st.session_state.req_ret_items.append({
                        "date": today_str(),
                        "code": name2code.get(items[idx]["name"]),
                        "item": items[idx]["name"],
                        "qty": int(qty),
                        "unit": items[idx].get("unit","-"),
                        "event": event_name,
                    })

            with tab2:
                st.info("Format Excel: **Date | Code | Nama Barang | Qty | Event** (Event **harus** sesuai daftar event OUT).")
                tpl = pd.DataFrame([{"Date": today_str(),"Code":"ITM-0001","Nama Barang":"Contoh A","Qty":2,"Event":"Promo Mall"}])
                download_template_button("Unduh Template Retur (Excel)", tpl, "Template_Retur.xlsx")
                file_upload = st.file_uploader("Upload File Excel Retur", type=["xlsx"], key="ret_excel")
                if file_upload and st.button("Tambah dari Excel (Retur)"):
                    df_new = pd.read_excel(file_upload, engine='openpyxl')
                    required = ["Date","Code","Nama Barang","Qty","Event"]
                    if not all(c in df_new.columns for c in required):
                        st.error("Kolom wajib: Date | Code | Nama Barang | Qty | Event")
                    else:
                        errors=[]
                        lowerevents = {e.lower(): e for e in events_out}
                        for ridx, row in df_new.iterrows():
                            code = str(row["Code"]).strip()
                            name = str(row["Nama Barang"]).strip()
                            if code not in data["inventory"]:
                                errors.append(f"Baris {ridx+2}: Code {code} tidak ditemukan.")
                                continue
                            qty = int(pd.to_numeric(row["Qty"], errors="coerce") or 0)
                            if qty<=0:
                                errors.append(f"Baris {ridx+2}: Qty harus > 0.")
                                continue
                            ev = str(row["Event"]).strip()
                            if ev.lower() not in lowerevents:
                                errors.append(f"Baris {ridx+2}: Event '{ev}' tidak ditemukan pada OUT (retur harus refer ke event OUT).")
                                continue
                            try:
                                d = pd.to_datetime(str(row["Date"])).strftime("%Y-%m-%d")
                            except Exception:
                                d = today_str()
                            st.session_state.req_ret_items.append({
                                "date": d,
                                "code": code,
                                "item": data["inventory"][code]["name"],
                                "qty": qty,
                                "unit": data["inventory"][code].get("unit","-"),
                                "event": lowerevents[ev.lower()],
                            })
                        if errors:
                            st.warning("Sebagian baris gagal ditambahkan:\n- " + "\n- ".join(errors))
                        else:
                            st.success("Item dari Excel berhasil ditambahkan ke daftar retur.")

            if st.session_state.req_ret_items:
                st.subheader("Daftar Item Request RETUR")
                df_ret = pd.DataFrame([{
                    "Tanggal": r["date"], "Code": r["code"], "Nama Barang": r["item"], "Qty": r["qty"], "Unit": r["unit"], "Event": r["event"]
                } for r in st.session_state.req_ret_items])
                select_all = st.checkbox("Pilih semua", key="sel_ret_all")
                df_ret["Pilih"] = select_all
                edited = st.data_editor(df_ret, use_container_width=True, hide_index=True)
                selected_idx = edited.index[edited["Pilih"]].tolist()

                c1, c2 = st.columns(2)
                if c1.button("Hapus Item Terpilih (Retur)") and selected_idx:
                    st.session_state.req_ret_items = [r for i, r in enumerate(st.session_state.req_ret_items) if i not in selected_idx]
                    st.rerun()
                if c2.button("Ajukan Request RETUR Terpilih"):
                    if not selected_idx:
                        st.session_state.notification = {"type":"warning","message":"Pilih setidaknya satu item."}
                        st.rerun()
                    for i in selected_idx:
                        r = st.session_state.req_ret_items[i]
                        data["pending_requests"].append({
                            "type":"RETURN",
                            "date": r["date"],
                            "code": r["code"],
                            "item": r["item"],
                            "qty": int(r["qty"]),
                            "unit": r.get("unit","-"),
                            "event": r.get("event","-"),
                            "trans_type": None,
                            "do_number": "-",
                            "attachment": None,
                            "user": st.session_state.username,
                            "timestamp": timestamp()
                        })
                    save_data(data, st.session_state.current_brand)
                    st.session_state.req_ret_items = [r for i, r in enumerate(st.session_state.req_ret_items) if i not in selected_idx]
                    st.session_state.notification = {"type":"success","message":"Request Retur diajukan dan menunggu approval."}
                    st.rerun()

    elif menu == "Stock Card":
        # sama seperti admin (reuse)
        st.markdown(f"## Stock Card Barang - Brand {st.session_state.current_brand.capitalize()}")
        st.divider()
        if not data["history"]:
            st.info("Belum ada riwayat transaksi.")
        else:
            item_names = sorted(list({item["name"] for item in data["inventory"].values()}))
            selected_item_name = st.selectbox("Pilih Barang", item_names)
            if selected_item_name:
                filtered_history = [h for h in data["history"] if h.get("item")==selected_item_name and (h["action"].startswith("APPROVE") or h["action"]=="ADD_ITEM")]
                if filtered_history:
                    stock_card_data = []
                    current_balance = 0
                    sorted_history = sorted(filtered_history, key=lambda x: x.get("timestamp") or x.get("date") or "")
                    for h in sorted_history:
                        inn, out, ket = 0, 0, "N/A"
                        if h["action"] == "ADD_ITEM":
                            inn = h["qty"]; current_balance += inn; ket = "Initial Stock"
                        elif h["action"] == "APPROVE_IN":
                            inn = h["qty"]; current_balance += inn; ket = f"Request IN by {h['user']}"
                            do_number = h.get('do_number', '-')
                            if do_number and do_number!='-': ket += f" (DO: {do_number})"
                        elif h["action"] == "APPROVE_OUT":
                            out = h["qty"]; current_balance -= out; ket = f"Request OUT by {h['user']} (Event: {h.get('event','-')})"
                        elif h["action"] == "APPROVE_RETURN":
                            inn = h["qty"]; current_balance += inn; ket = f"RETUR by {h['user']} (Event: {h.get('event','-')})"
                        else:
                            continue
                        stock_card_data.append({
                            "Tanggal": h.get("date") or (h.get("timestamp","")[:10]),
                            "Keterangan": ket,
                            "Masuk (IN)": inn if inn>0 else "-",
                            "Keluar (OUT)": out if out>0 else "-",
                            "Saldo Akhir": current_balance
                        })
                    st.dataframe(pd.DataFrame(stock_card_data), use_container_width=True, hide_index=True)
                else:
                    st.info("Tidak ada riwayat transaksi disetujui untuk barang ini.")

    elif menu == "Lihat Riwayat":
        st.markdown(f"## Riwayat Saya - Brand {st.session_state.current_brand.capitalize()}")
        st.divider()
        my_user = st.session_state.username
        # satukan pending (status Pending) + history (Approved/Rejected)
        rows = []
        for p in data.get("pending_requests", []):
            if p.get("user")==my_user:
                rows.append({
                    "Tanggal": p.get("date") or (p.get("timestamp","")[:10]),
                    "Type": p.get("type"),
                    "Item": p.get("item"),
                    "Qty": p.get("qty"),
                    "Unit": p.get("unit","-"),
                    "Event": p.get("event","-"),
                    "TransType": p.get("trans_type"),
                    "Status": "Pending",
                })
        for h in data.get("history", []):
            if h.get("user")==my_user:
                act = h.get("action","")
                status = "Approved" if act.startswith("APPROVE") else ("Rejected" if act.startswith("REJECT") else "-")
                typ = "IN" if act.endswith("_IN") or act=="ADD_ITEM" else ("OUT" if act.endswith("_OUT") else ("RETURN" if act.endswith("_RETURN") else "-"))
                rows.append({
                    "Tanggal": h.get("date") or (h.get("timestamp","")[:10]),
                    "Type": typ,
                    "Item": h.get("item"),
                    "Qty": h.get("qty"),
                    "Unit": h.get("unit","-"),
                    "Event": h.get("event","-"),
                    "TransType": h.get("trans_type"),
                    "Status": status
                })
        if rows:
            df = pd.DataFrame(rows).sort_values("Tanggal")
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("Anda belum memiliki riwayat.")
