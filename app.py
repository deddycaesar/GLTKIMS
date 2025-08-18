import streamlit as st
import json
import os
from datetime import datetime
import pandas as pd
import base64
from io import BytesIO

# Optional untuk grafik yang lebih menarik
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

# Pastikan folder uploads ada
if not os.path.exists(UPLOADS_DIR):
    os.makedirs(UPLOADS_DIR)

# ====== Styling & Branding ======
st.set_page_config(page_title="Inventory System", page_icon=ICON_URL, layout="wide")
st.markdown("""
    <style>
    .main { background-color: #F5F5F5; }
    h1, h2, h3 { color: #FF781F; }
    .stButton>button {
        background-color: #34A853; color: white; border-radius: 8px; height: 3em; width: 100%; border: none;
    }
    .stButton>button:hover { background-color: #4CAF50; color: white; }
    .sidebar .sidebar-content { background-color: #FFFFFF; }
    .stRadio [role=radio] { margin: 10px 0px; transition: all 0.2s ease-in-out; }
    .stRadio [role=radio] > div { color: #555555; font-weight: 500; font-size: 16px; }
    .stRadio [role=radio]:hover { background-color: #E0F2F7; border-radius: 8px; }
    .stRadio [aria-selected="true"] { background-color: #E0F2F7; border-radius: 8px; color: #FF781F !important; font-weight: 700; }
    .stRadio label > div:first-child { display: none; }
    .stAlert { background-color: #FFCC80 !important; color: #333333 !important; border-radius: 8px; border: none; }
    </style>
""", unsafe_allow_html=True)

# ====== Utilitas ======
ID_MONTHS = ["Januari","Februari","Maret","April","Mei","Juni","Juli","Agustus","September","Oktober","November","Desember"]

def timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def load_data(brand_key):
    data_file = DATA_FILES[brand_key]
    if os.path.exists(data_file):
        try:
            with open(data_file, "r") as f:
                data = json.load(f)
                for code, item in data.get("inventory", {}).items():
                    if "category" not in item:
                        item["category"] = "Uncategorized"
                return data
        except (json.JSONDecodeError, FileNotFoundError) as e:
            st.error(f"Error reading data file: {e}. Starting with empty data.")
    return {
        "users": {
            "admin": {"password": st.secrets.get("passwords", {}).get("admin"), "role": "admin"},
            "user": {"password": st.secrets.get("passwords", {}).get("user"), "role": "user"},
        },
        "inventory": {},
        "item_counter": 0,
        "pending_requests": [],
        "history": [],
    }

def save_data(data, brand_key):
    data_file = DATA_FILES[brand_key]
    with open(data_file, "w") as f:
        json.dump(data, f, indent=4)

def month_label(dt: pd.Timestamp) -> str:
    return f"{ID_MONTHS[dt.month-1]} {dt.year}"

def build_dashboard_3months_tables(data) -> tuple:
    inv_records = [
        {"Kode": code, "Nama Barang": item.get("name", "-"), "Current Stock": int(item.get("qty", 0))}
        for code, item in data.get("inventory", {}).items()
    ]
    df_inv = pd.DataFrame(inv_records) if inv_records else pd.DataFrame(columns=["Kode","Nama Barang","Current Stock"])

    hist = data.get("history", [])
    df_hist = pd.DataFrame(hist) if hist else pd.DataFrame(columns=["action","item","qty","timestamp"])

    now = pd.Timestamp.now()
    this_month_start = pd.Timestamp(year=now.year, month=now.month, day=1)
    month_starts = [this_month_start, this_month_start - pd.DateOffset(months=1), this_month_start - pd.DateOffset(months=2)]
    month_labels = [month_label(ms) for ms in month_starts]

    all_items = set(df_inv["Nama Barang"].tolist()) if not df_inv.empty else set()
    if not df_hist.empty:
        all_items |= set(df_hist.get("item", pd.Series([], dtype=str)).dropna().astype(str).tolist())
    all_items = sorted(list(all_items))

    if len(all_items) == 0:
        empty_cols = []
        for lbl in month_labels:
            empty_cols += [f"{lbl} IN", f"{lbl} OUT", f"{lbl} Retur"]
        df_dash = pd.DataFrame(columns=["Nama Barang"] + empty_cols + ["Current Stock"])
        return df_inv, df_dash, month_labels

    if not df_hist.empty:
        df_hist["qty"] = pd.to_numeric(df_hist.get("qty", 0), errors="coerce").fillna(0).astype(int)
        df_hist["timestamp"] = pd.to_datetime(df_hist.get("timestamp", pd.NaT), errors="coerce")
        df_hist["ACTION_UP"] = df_hist["action"].astype(str).str.upper()
    else:
        df_hist = pd.DataFrame(columns=["item","qty","timestamp","ACTION_UP"])

    df_dash = pd.DataFrame({"Nama Barang": all_items})

    for ms in month_starts:
        next_ms = ms + pd.offsets.MonthBegin(1)
        lbl = month_label(ms)
        m = df_hist[(df_hist["timestamp"] >= ms) & (df_hist["timestamp"] < next_ms)].copy()
        if not m.empty:
            m["IN_QTY"]   = m.apply(lambda r: r["qty"] if "APPROVE_IN" in r["ACTION_UP"] else 0, axis=1)
            m["OUT_QTY"]  = m.apply(lambda r: r["qty"] if "APPROVE_OUT" in r["ACTION_UP"] else 0, axis=1)
            m["RET_QTY"]  = m.apply(lambda r: r["qty"] if "APPROVE_RETURN" in r["ACTION_UP"] or "RETURN" in r["ACTION_UP"] else 0, axis=1)
            g = (m.groupby("item", dropna=False)[["IN_QTY","OUT_QTY","RET_QTY"]]
                   .sum()
                   .reset_index()
                   .rename(columns={"item":"Nama Barang"}))
        else:
            g = pd.DataFrame(columns=["Nama Barang","IN_QTY","OUT_QTY","RET_QTY"])

        df_dash = df_dash.merge(g, on="Nama Barang", how="left")
        df_dash.rename(columns={
            "IN_QTY":  f"{lbl} IN",
            "OUT_QTY": f"{lbl} OUT",
            "RET_QTY": f"{lbl} Retur"
        }, inplace=True)

    if not df_inv.empty:
        df_dash = df_dash.merge(df_inv[["Nama Barang","Current Stock"]], on="Nama Barang", how="left")
    else:
        df_dash["Current Stock"] = 0

    for c in df_dash.columns:
        if c != "Nama Barang":
            df_dash[c] = pd.to_numeric(df_dash[c], errors="coerce").fillna(0).astype(int)

    return df_inv, df_dash, month_labels

def dataframe_to_excel_bytes(df: pd.DataFrame, sheet_name="Sheet1") -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
    output.seek(0)
    return output.read()

def make_out_template_bytes(data) -> bytes:
    """
    Template Excel untuk Request OUT:
    Kolom: Tanggal | Kode Barang | Nama Barang | Qty | Event | Tipe
    """
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
                "Tipe": "Support"  # atau "Penjualan"
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
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df_tmpl.to_excel(writer, sheet_name="Template OUT", index=False)
    output.seek(0)
    return output.read()

def make_master_template_bytes() -> bytes:
    """
    Template Excel Master Barang:
    Kolom: Kode Barang | Nama Barang | Qty | Satuan | Kategori
    """
    cols = ["Kode Barang", "Nama Barang", "Qty", "Satuan", "Kategori"]
    df_tmpl = pd.DataFrame([{
        "Kode Barang": "ITM-0001",
        "Nama Barang": "Contoh Produk",
        "Qty": 10,
        "Satuan": "pcs",
        "Kategori": "Umum"
    }], columns=cols)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df_tmpl.to_excel(writer, sheet_name="Template Master", index=False)
    output.seek(0)
    return output.read()

def dashboard_charts(df_dash: pd.DataFrame, month_labels: list, df_inv: pd.DataFrame):
    """Tampilkan grafik-grafik dashboard (total IN/OUT/Retur per bulan + Top 5 current stock)."""
    # Total per bulan
    totals = []
    for lbl in month_labels:
        totals.append({
            "Bulan": lbl,
            "IN":  int(df_dash.get(f"{lbl} IN", pd.Series()).sum()) if f"{lbl} IN" in df_dash.columns else 0,
            "OUT": int(df_dash.get(f"{lbl} OUT", pd.Series()).sum()) if f"{lbl} OUT" in df_dash.columns else 0,
            "Retur": int(df_dash.get(f"{lbl} Retur", pd.Series()).sum()) if f"{lbl} Retur" in df_dash.columns else 0,
        })
    df_tot = pd.DataFrame(totals)
    c1, c2 = st.columns(2)

    with c1:
        st.subheader("Total IN/OUT/Retur (3 Bulan)")
        if _ALT_OK and not df_tot.empty:
            df_long = df_tot.melt("Bulan", var_name="Tipe", value_name="Jumlah")
            chart = (
                alt.Chart(df_long)
                .mark_bar()
                .encode(
                    x=alt.X("Bulan:N", title="Bulan"),
                    y=alt.Y("Jumlah:Q", title="Jumlah"),
                    color=alt.Color("Tipe:N"),
                    xOffset="Tipe:N",
                    tooltip=["Bulan","Tipe","Jumlah"]
                )
                .properties(height=300)
            )
            st.altair_chart(chart, use_container_width=True)
        else:
            st.bar_chart(df_tot.set_index("Bulan"))

    with c2:
        st.subheader("Top 5 Current Stock")
        if df_inv.empty:
            st.info("Inventory kosong.")
        else:
            df_top5 = df_inv.sort_values("Current Stock", ascending=False).head(5).copy()
            if _ALT_OK:
                chart2 = (
                    alt.Chart(df_top5)
                    .mark_bar()
                    .encode(
                        y=alt.Y("Nama Barang:N", sort="-x", title="Item"),
                        x=alt.X("Current Stock:Q", title="Qty"),
                        tooltip=["Nama Barang","Current Stock"]
                    )
                    .properties(height=300)
                )
                st.altair_chart(chart2, use_container_width=True)
            else:
                st.bar_chart(df_top5.set_index("Nama Barang")["Current Stock"])

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
            <h1 style='margin-top:10px; color: #FF781F;'>Inventory Management System</h1>
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
        if st.session_state.notification["type"] == "success":
            st.success(st.session_state.notification["message"])
        elif st.session_state.notification["type"] == "warning":
            st.warning(st.session_state.notification["message"])
        elif st.session_state.notification["type"] == "error":
            st.error(st.session_state.notification["message"])
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
            st.markdown(f"## Dashboard - Brand {st.session_state.current_brand.capitalize()}")
            st.caption("Menampilkan total **IN / OUT / Retur** (approved) 3 bulan terakhir + grafik.")
            st.divider()

            df_inv, df_dash, month_labels = build_dashboard_3months_tables(data)

            cols = st.columns(3)
            for idx, lbl in enumerate(month_labels):
                in_col = f"{lbl} IN"; out_col = f"{lbl} OUT"; ret_col = f"{lbl} Retur"
                total_in = int(df_dash[in_col].sum()) if in_col in df_dash else 0
                total_out = int(df_dash[out_col].sum()) if out_col in df_dash else 0
                total_ret = int(df_dash[ret_col].sum()) if ret_col in df_dash else 0
                with cols[idx]:
                    st.metric(f"{lbl} • IN", f"{total_in}")
                    st.metric(f"{lbl} • OUT", f"{total_out}")
                    st.metric(f"{lbl} • Retur", f"{total_ret}")

            st.markdown("### Grafik")
            dashboard_charts(df_dash, month_labels, df_inv)

            st.markdown("### Rekap Per Barang (3 Bulan Terakhir + Current Stock)")
            if df_dash.empty:
                st.info("Belum ada data.")
            else:
                ordered_cols = ["Nama Barang"]
                for lbl in month_labels:
                    ordered_cols += [f"{lbl} IN", f"{lbl} OUT", f"{lbl} Retur"]
                ordered_cols += ["Current Stock"]
                st.dataframe(
                    df_dash[ordered_cols].sort_values("Current Stock", ascending=False),
                    use_container_width=True, hide_index=True
                )

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
                # download template
                tmpl_master = make_master_template_bytes()
                st.download_button(
                    label="📥 Unduh Template Master Excel",
                    data=tmpl_master,
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
                                    qty = int(row["Qty"]) if pd.notna(row["Qty"]) else 0
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
                                if added:
                                    st.success(f"{added} item master berhasil ditambahkan.")
                                if errors:
                                    st.warning("Beberapa baris dilewati:\n- " + "\n- ".join(errors))
                                st.rerun()

        elif menu == "Approve Request":
            st.markdown(f"## Approve / Reject Request Barang - Brand {st.session_state.current_brand.capitalize()}")
            st.divider()
            if data["pending_requests"]:
                processed_requests = []
                for req in data["pending_requests"]:
                    temp_req = req.copy()
                    if 'attachment' not in temp_req: temp_req['attachment'] = None
                    if 'trans_type' not in temp_req: temp_req['trans_type'] = None
                    processed_requests.append(temp_req)

                df_pending = pd.DataFrame(processed_requests)
                df_pending["Lampiran"] = df_pending["attachment"].apply(lambda x: "Ada" if x else "Tidak Ada")

                # ==== SELECT ALL STATE ====
                if "approve_select_flags" not in st.session_state or len(st.session_state.approve_select_flags) != len(df_pending):
                    st.session_state.approve_select_flags = [False] * len(df_pending)

                csel1, csel2 = st.columns([1,1])
                if csel1.button("Pilih semua"):
                    st.session_state.approve_select_flags = [True]*len(df_pending)
                if csel2.button("Kosongkan pilihan"):
                    st.session_state.approve_select_flags = [False]*len(df_pending)

                df_pending["Pilih"] = st.session_state.approve_select_flags

                # Editor: hanya kolom "Pilih" yang boleh diubah
                col_cfg = {"Pilih": st.column_config.CheckboxColumn("Pilih", default=False)}
                for c in df_pending.columns:
                    if c != "Pilih":
                        col_cfg[c] = st.column_config.TextColumn(c, disabled=True)
                edited_df = st.data_editor(df_pending, key="editor_admin_approve", use_container_width=True, hide_index=True, column_config=col_cfg)

                # commit flags
                st.session_state.approve_select_flags = edited_df["Pilih"].fillna(False).tolist()

                selected_indices = [i for i, v in enumerate(st.session_state.approve_select_flags) if v]

                col1, col2 = st.columns(2)
                if col1.button("Approve Selected"):
                    if selected_indices:
                        for i in selected_indices:
                            req = processed_requests[i]
                            # cari di pending_requests berdasar identifier yang aman
                            match_idx = next((ix for ix, r in enumerate(data["pending_requests"])
                                              if r.get("item")==req.get("item")
                                              and r.get("qty")==req.get("qty")
                                              and r.get("user")==req.get("user")
                                              and r.get("type")==req.get("type")
                                              and r.get("timestamp")==req.get("timestamp")), None)
                            if match_idx is not None:
                                approved_req = data["pending_requests"].pop(match_idx)
                                for code, item in data["inventory"].items():
                                    if item["name"] == approved_req["item"]:
                                        if approved_req["type"] == "IN":
                                            item["qty"] += approved_req["qty"]
                                        elif approved_req["type"] == "OUT":
                                            item["qty"] -= approved_req["qty"]
                                        elif approved_req["type"] == "RETURN":
                                            item["qty"] += approved_req["qty"]

                                        data["history"].append({
                                            "action": f"APPROVE_{approved_req['type']}",
                                            "item": approved_req["item"],
                                            "qty": approved_req["qty"],
                                            "stock": item["qty"],
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
                                    "qty": original_req["qty"],
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
                all_keys = ["action","item","qty","stock","unit","user","event","do_number","attachment","timestamp",
                            "date","code","trans_type"]
                processed_history = []
                for entry in data["history"]:
                    new_entry = {key: entry.get(key, None) for key in all_keys}
                    if new_entry.get("do_number") is None: new_entry["do_number"] = "-"
                    if new_entry.get("event") is None: new_entry["event"] = "-"
                    if new_entry.get("unit") is None: new_entry["unit"] = "-"
                    processed_history.append(new_entry)

                df_history_full = pd.DataFrame(processed_history)
                df_history_full['date_only'] = pd.to_datetime(df_history_full['timestamp'], errors="coerce").dt.date

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
            st.warning(f"Aksi ini akan menghapus seluruh data inventori, request, dan riwayat untuk brand **{st.session_state.current_brand.capitalize()}**.")
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
            st.markdown(f"## Dashboard - Brand {st.session_state.current_brand.capitalize()}")
            st.caption("Menampilkan total **IN / OUT / Retur** (approved) 3 bulan terakhir + grafik.")
            st.divider()

            df_inv, df_dash, month_labels = build_dashboard_3months_tables(data)
            cols = st.columns(3)
            for idx, lbl in enumerate(month_labels):
                in_col = f"{lbl} IN"; out_col = f"{lbl} OUT"; ret_col = f"{lbl} Retur"
                total_in = int(df_dash[in_col].sum()) if in_col in df_dash else 0
                total_out = int(df_dash[out_col].sum()) if out_col in df_dash else 0
                total_ret = int(df_dash[ret_col].sum()) if ret_col in df_dash else 0
                with cols[idx]:
                    st.metric(f"{lbl} • IN", f"{total_in}")
                    st.metric(f"{lbl} • OUT", f"{total_out}")
                    st.metric(f"{lbl} • Retur", f"{total_ret}")

            st.markdown("### Grafik")
            dashboard_charts(df_dash, month_labels, df_inv)

            st.markdown("### Rekap Per Barang (3 Bulan Terakhir + Current Stock)")
            if df_dash.empty:
                st.info("Belum ada data.")
            else:
                ordered_cols = ["Nama Barang"]
                for lbl in month_labels:
                    ordered_cols += [f"{lbl} IN", f"{lbl} OUT", f"{lbl} Retur"]
                ordered_cols += ["Current Stock"]
                st.dataframe(
                    df_dash[ordered_cols].sort_values("Current Stock", ascending=False),
                    use_container_width=True, hide_index=True
                )
                excel_bytes = dataframe_to_excel_bytes(df_dash[ordered_cols], sheet_name="Dashboard 3 Bulan")
                st.download_button(
                    label="Unduh Excel Dashboard",
                    data=excel_bytes,
                    file_name=f"Dashboard_3_Bulan_{st.session_state.current_brand.capitalize()}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

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

        # ----- Request Barang IN (User) – MANUAL SAJA & WAJIB ISI -----
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

                # ===== SELECT ALL UNTUK IN =====
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
                            # simpan attachment
                            timestamp_str = datetime.now().strftime("%Y%m%d%H%M%S")
                            file_ext = uploaded_file.name.split(".")[-1]
                            attachment_path = os.path.join(UPLOADS_DIR, f"{st.session_state.username}_{timestamp_str}.{file_ext}")
                            with open(attachment_path, "wb") as f:
                                f.write(uploaded_file.getbuffer())

                            submit_count = 0
                            new_state, new_flags = [], []
                            for selected, rec in zip(mask, st.session_state.req_in_items):
                                if selected:
                                    request_data = {
                                        "type": "IN",
                                        "item": rec["item"],
                                        "qty": int(rec["qty"]),
                                        "unit": rec.get("unit", "-"),
                                        "user": st.session_state.username,
                                        "event": "-",
                                        "do_number": do_number.strip(),
                                        "attachment": attachment_path,
                                        "timestamp": timestamp()
                                    }
                                    data["pending_requests"].append(request_data)
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

        # ----- Request Barang OUT (User) – WAJIB ISI + SELECT ALL -----
        elif menu == "Request Barang OUT":
            st.markdown(f"## Request Barang Keluar (Multi Item) - Brand {st.session_state.current_brand.capitalize()}")
            st.divider()

            if items:
                tab1, tab2 = st.tabs(["Input Manual", "Upload Excel"])

                # ===== TAB 1: INPUT MANUAL (WAJIB EVENT & TIPE) =====
                with tab1:
                    col1, col2 = st.columns(2)
                    idx = col1.selectbox(
                        "Pilih Barang", range(len(items)),
                        format_func=lambda x: f"{items[x]['name']} (Stok: {items[x]['qty']} {items[x].get('unit', '-')})"
                    )
                    max_qty = items[idx]["qty"]
                    qty = col2.number_input("Jumlah", min_value=1, max_value=max_qty, step=1)

                    tipe = st.selectbox("Tipe Transaksi (wajib)", TRANS_TYPES, index=0)
                    event_manual = st.text_input("Nama Event (wajib)", placeholder="Misal: Pameran, Acara Kantor")

                    if st.button("Tambah Item OUT (Manual)"):
                        if not event_manual.strip():
                            st.error("Event wajib diisi.")
                        else:
                            selected_name = items[idx]["name"]
                            found_code = next((code for code, it in data["inventory"].items() if it.get("name") == selected_name), None)
                            today_str = datetime.now().strftime("%Y-%m-%d")
                            st.session_state.req_out_items.append({
                                "date": today_str,
                                "code": found_code if found_code else "-",
                                "item": selected_name,
                                "qty": qty,
                                "unit": items[idx].get("unit", "-"),
                                "event": event_manual.strip(),
                                "trans_type": tipe
                            })
                            st.success("Item OUT (manual) ditambahkan ke daftar.")

                # ===== TAB 2: UPLOAD EXCEL =====
                with tab2:
                    st.info("Format kolom wajib: **Tanggal | Kode Barang | Nama Barang | Qty | Event | Tipe** (Tipe = Support atau Penjualan)")
                    tmpl_bytes = make_out_template_bytes(data)
                    st.download_button(
                        label="📥 Unduh Template Excel OUT",
                        data=tmpl_bytes,
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
                                    errors = []
                                    added = 0
                                    by_code = {code: (it.get("name"), it.get("unit", "-"), it.get("qty", 0)) for code, it in data["inventory"].items()}
                                    by_name = {it.get("name"): (code, it.get("unit", "-"), it.get("qty", 0)) for code, it in data["inventory"].items()}

                                    for idx_row, row in df_new.iterrows():
                                        try:
                                            dt = pd.to_datetime(row["Tanggal"], errors="coerce")
                                            date_str = dt.strftime("%Y-%m-%d") if pd.notna(dt) else datetime.now().strftime("%Y-%m-%d")

                                            code_xl = str(row["Kode Barang"]).strip() if pd.notna(row["Kode Barang"]) else ""
                                            name_xl = str(row["Nama Barang"]).strip() if pd.notna(row["Nama Barang"]) else ""
                                            qty_xl = int(row["Qty"])
                                            event_xl = str(row["Event"]).strip() if pd.notna(row["Event"]) else ""
                                            tipe_xl_raw = str(row["Tipe"]).strip().lower() if pd.notna(row["Tipe"]) else ""

                                            if not event_xl:
                                                errors.append(f"Baris {idx_row+2}: Event wajib diisi.")
                                                continue
                                            if tipe_xl_raw not in ["support","penjualan"]:
                                                errors.append(f"Baris {idx_row+2}: Tipe harus 'Support' atau 'Penjualan'.")
                                                continue
                                            tipe_xl = tipe_xl_raw.capitalize()

                                            inv_name, inv_unit, inv_stock = (None, None, None)
                                            inv_code = None
                                            if code_xl and code_xl in by_code:
                                                inv_name, inv_unit, inv_stock = by_code[code_xl]
                                                inv_code = code_xl
                                            elif name_xl and name_xl in by_name:
                                                inv_code, inv_unit, inv_stock = by_name[name_xl]
                                                inv_name = name_xl
                                            else:
                                                errors.append(f"Baris {idx_row+2}: Item tidak ditemukan (kode='{code_xl}', nama='{name_xl}').")
                                                continue

                                            if qty_xl <= 0:
                                                errors.append(f"Baris {idx_row+2}: Qty harus > 0.")
                                                continue

                                            if inv_stock is not None and qty_xl > inv_stock:
                                                errors.append(f"Baris {idx_row+2}: Qty ({qty_xl}) melebihi stok ({inv_stock}) untuk item '{inv_name}'.")
                                                continue

                                            st.session_state.req_out_items.append({
                                                "date": date_str,
                                                "code": inv_code if inv_code else "-",
                                                "item": inv_name,
                                                "qty": qty_xl,
                                                "unit": inv_unit if inv_unit else "-",
                                                "event": event_xl,
                                                "trans_type": tipe_xl
                                            })
                                            added += 1
                                        except Exception as e:
                                            errors.append(f"Baris {idx_row+2}: {e}")

                                    if added:
                                        st.success(f"{added} baris berhasil ditambahkan ke daftar request OUT.")
                                    if errors:
                                        st.warning("Beberapa baris dilewati:\n- " + "\n- ".join(errors))

                # ===== DAFTAR & SUBMIT OUT (dengan PILIH SEMUA) =====
                if st.session_state.req_out_items:
                    st.subheader("Daftar Item Request OUT")
                    df_out = pd.DataFrame(st.session_state.req_out_items)
                    pref_cols = [c for c in ["date","code","item","qty","unit","event","trans_type"] if c in df_out.columns]
                    df_out = df_out[pref_cols]

                    if "out_select_flags" not in st.session_state or len(st.session_state.out_select_flags) != len(st.session_state.req_out_items):
                        st.session_state.out_select_flags = [False] * len(st.session_state.req_out_items)

                    c1, c2 = st.columns([1,1])
                    if c1.button("Pilih semua", key="out_sel_all"):
                        st.session_state.out_select_flags = [True] * len(st.session_state.req_out_items)
                    if c2.button("Kosongkan pilihan", key="out_sel_none"):
                        st.session_state.out_select_flags = [False] * len(st.session_state.req_out_items)

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
                            st.info("Tidak ada baris yang dipilih untuk dihapus.")

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
                                    request_data = {
                                        "type": "OUT",
                                        "date": rec.get("date", datetime.now().strftime("%Y-%m-%d")),
                                        "code": rec.get("code", "-"),
                                        "item": rec["item"],
                                        "qty": int(rec["qty"]),
                                        "unit": rec.get("unit", "-"),
                                        "user": st.session_state.username,
                                        "event": rec.get("event", "-"),
                                        "trans_type": rec.get("trans_type", None),
                                        "do_number": "-",
                                        "attachment": None,
                                        "timestamp": timestamp()
                                    }
                                    data["pending_requests"].append(request_data)
                                    submitted += 1
                                else:
                                    new_state.append(rec); new_flags.append(False)

                            save_data(data, st.session_state.current_brand)
                            st.session_state.req_out_items = new_state
                            st.session_state.out_select_flags = new_flags
                            st.success(f"{submitted} request OUT diajukan & menunggu approval.")
                            st.rerun()
            else:
                st.info("Belum ada master barang. Silakan hubungi admin.")

        # ----- Request Retur (User) – SELECT ALL -----
        elif menu == "Request Retur":
            st.markdown(f"## Request Retur (Pengembalian ke Gudang) - Brand {st.session_state.current_brand.capitalize()}")
            st.divider()

            if items:
                col1, col2 = st.columns(2)
                idx = col1.selectbox(
                    "Pilih Barang", range(len(items)),
                    format_func=lambda x: f"{items[x]['name']} (Stok Gudang: {items[x]['qty']} {items[x].get('unit','-')})"
                )
                qty = col2.number_input("Jumlah Retur", min_value=1, step=1)

                item_name = items[idx]["name"]
                approved_out_events = sorted(list({
                    h.get("event","-") for h in data.get("history", [])
                    if h.get("action") == "APPROVE_OUT" and h.get("item") == item_name and h.get("event") not in [None, "-", ""]
                }))
                if not approved_out_events:
                    st.warning("Belum ada event OUT yang di-approve untuk item ini. Retur membutuhkan referensi event OUT.")
                    event_choice = None
                else:
                    event_choice = st.selectbox("Pilih Event (berdasarkan transaksi OUT yang sudah disetujui)", approved_out_events)

                if st.button("Tambah Item Retur"):
                    if event_choice:
                        st.session_state.req_ret_items.append({
                            "item": item_name,
                            "qty": qty,
                            "unit": items[idx].get("unit", "-"),
                            "event": event_choice
                        })
                        st.success("Item Retur ditambahkan ke daftar.")
                    else:
                        st.error("Pilih event terlebih dahulu (tidak boleh kosong).")

                if st.session_state.req_ret_items:
                    st.subheader("Daftar Item Request Retur")

                    if "ret_select_flags" not in st.session_state or len(st.session_state.ret_select_flags) != len(st.session_state.req_ret_items):
                        st.session_state.ret_select_flags = [False]*len(st.session_state.req_ret_items)

                    cR1, cR2 = st.columns([1,1])
                    if cR1.button("Pilih semua", key="ret_sel_all"):
                        st.session_state.ret_select_flags = [True]*len(st.session_state.req_ret_items)
                    if cR2.button("Kosongkan pilihan", key="ret_sel_none"):
                        st.session_state.ret_select_flags = [False]*len(st.session_state.req_ret_items)

                    df_ret = pd.DataFrame(st.session_state.req_ret_items)
                    df_ret["Pilih"] = st.session_state.ret_select_flags
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
                                    request_data = {
                                        "type": "RETURN",
                                        "item": rec["item"],
                                        "qty": int(rec["qty"]),
                                        "unit": rec.get("unit", "-"),
                                        "user": st.session_state.username,
                                        "event": rec.get("event", "-"),
                                        "do_number": "-",
                                        "attachment": None,
                                        "timestamp": timestamp()
                                    }
                                    data["pending_requests"].append(request_data)
                            save_data(data, st.session_state.current_brand)
                            st.session_state.req_ret_items = [rec for rec, keep in zip(st.session_state.req_ret_items, [not x for x in mask]) if keep]
                            st.session_state.ret_select_flags = [False]*len(st.session_state.req_ret_items)
                            st.success("Request RETUR diajukan & menunggu approval.")
                            st.rerun()
            else:
                st.info("Belum ada master barang. Silakan hubungi admin.")

        # ----- Lihat Riwayat (User) — DENGAN STATUS -----
        elif menu == "Lihat Riwayat":
            st.markdown(f"## Riwayat Saya (dengan Status) - Brand {st.session_state.current_brand.capitalize()}")
            st.divider()

            hist = data.get("history", [])
            my_hist = [h for h in hist if h.get("user") == st.session_state.username and isinstance(h.get("action",""), str)]
            rows = []
            for h in my_hist:
                act = h["action"].upper()
                status = "APPROVED" if act.startswith("APPROVE_") else ("REJECTED" if act.startswith("REJECT_") else "-")
                ttype = act.split("_")[-1] if "_" in act else "-"
                rows.append({
                    "Status": status,
                    "Type": ttype,  # IN/OUT/RETURN
                    "Date": h.get("date", None),
                    "Code": h.get("code","-"),
                    "Item": h.get("item","-"),
                    "Qty": h.get("qty","-"),
                    "Unit": h.get("unit","-"),
                    "Trans. Tipe": h.get("trans_type","-"),
                    "Event": h.get("event","-"),
                    "DO": h.get("do_number","-"),
                    "Timestamp": h.get("timestamp","-")
                })

            pend = data.get("pending_requests", [])
            my_pend = [p for p in pend if p.get("user") == st.session_state.username]
            for p in my_pend:
                rows.append({
                    "Status": "PENDING",
                    "Type": p.get("type","-"),
                    "Date": p.get("date", None),
                    "Code": p.get("code","-"),
                    "Item": p.get("item","-"),
                    "Qty": p.get("qty","-"),
                    "Unit": p.get("unit","-"),
                    "Trans. Tipe": p.get("trans_type","-"),
                    "Event": p.get("event","-"),
                    "DO": p.get("do_number","-"),
                    "Timestamp": p.get("timestamp","-")
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
