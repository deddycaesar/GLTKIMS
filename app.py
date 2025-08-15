import streamlit as st
import json
import os
from datetime import datetime
import pandas as pd
import base64

# ====== Konfigurasi Multi-Brand ======
DATA_FILES = {
    "gulavit": "gulavit_data.json",
    "takokak": "takokak_data.json"
}
UPLOADS_DIR = "uploads"
# Perubahan: Ganti URL banner dengan yang dapat diakses secara permanen
BANNER_URL = "https://media.licdn.com/dms/image/v2/D563DAQFDri8xlKNIvg/image-scale_191_1128/image-scale_191_1128/0/1678337293506/pesona_inti_rasa_cover?e=2147483647&v=beta&t=vHi0xtyAZsT9clHb0yBYPE8M9IaO2dNY6Cb_Vs3Ddlo" # Contoh URL publik
ICON_URL = "https://i.ibb.co/7C96T9y/favicon.png"

# Pastikan folder uploads ada
if not os.path.exists(UPLOADS_DIR):
    os.makedirs(UPLOADS_DIR)

# ====== Styling & Branding ======
st.set_page_config(page_title="Inventory System", page_icon=ICON_URL, layout="wide")

st.markdown("""
    <style>
    .main {
        background-color: #F5F5F5;
    }
    h1, h2, h3 {
        color: #FF781F;
    }
    .stButton>button {
        background-color: #34A853;
        color: white;
        border-radius: 8px;
        height: 3em;
        width: 100%;
        border: none;
    }
    .stButton>button:hover {
        background-color: #4CAF50;
        color: white;
    }
    .sidebar .sidebar-content {
        background-color: #FFFFFF;
    }
    .stRadio [role=radio] {
        margin: 10px 0px;
        transition: all 0.2s ease-in-out;
    }
    .stRadio [role=radio] > div {
        color: #555555;
        font-weight: 500;
        font-size: 16px;
    }
    .stRadio [role=radio]:hover {
        background-color: #E0F2F7;
        border-radius: 8px;
    }
    .stRadio [aria-selected="true"] {
        background-color: #E0F2F7;
        border-radius: 8px;
        color: #FF781F !important;
        font-weight: 700;
    }
    .stRadio label > div:first-child {
        display: none;
    }
    .stAlert {
        background-color: #FFCC80 !important;
        color: #333333 !important;
        border-radius: 8px;
        border: none;
    }
    </style>
""", unsafe_allow_html=True)

# ====== Utilitas ======
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
    
    # Mengambil kredensial dari secrets
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
if "notification" not in st.session_state:
    st.session_state.notification = None

# ====== LOGIN PAGE ======
if not st.session_state.logged_in:
    # Baris ini yang menampilkan banner di halaman login
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
    # ====== Main App (Setelah Login) ======
    role = st.session_state.role

    # Banner di halaman utama (hanya setelah login)
    st.image(BANNER_URL, use_container_width=True)
    
    # ===== Sidebar =====
    st.sidebar.markdown(f"### 👋 Halo, {st.session_state.username}")
    st.sidebar.caption(f"Role: **{role.upper()}**")
    st.sidebar.divider()

    # --- DROPDOWN PEMILIHAN BRAND ---
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

    if role == "admin":
        admin_options = [
            "Lihat Stok Barang",
            "Stock Card",
            "Tambah Master Barang",
            "Approve Request",
            "Riwayat Lengkap",
            "Export Laporan ke Excel",
            "Reset Database"
        ]
        menu = st.sidebar.radio("📌 Menu Admin", admin_options)

        if menu == "Lihat Stok Barang":
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
                                transaction_in = h["qty"]
                                current_balance += transaction_in
                                keterangan = "Initial Stock"
                            elif h["action"] == "APPROVE_IN":
                                transaction_in = h["qty"]
                                current_balance += transaction_in
                                keterangan = f"Request IN by {h['user']}"
                                do_number = h.get('do_number', '-')
                                if do_number != '-':
                                    keterangan += f" (No. DO: {do_number})"
                            elif h["action"] == "APPROVE_OUT":
                                transaction_out = h["qty"]
                                current_balance -= transaction_out
                                keterangan = f"Request OUT by {h['user']} for event: {h.get('event', '-')}"
                            else:
                                continue

                            stock_card_data.append({
                                "Tanggal": h["timestamp"],
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
                name = st.text_input("Nama Barang")
                unit = st.text_input("Satuan (misal: pcs, box, liter)")
                qty = st.number_input("Jumlah Stok Awal", min_value=0, step=1)
                category = st.text_input("Kategori Barang", placeholder="Misal: Minuman, Makanan")

                if st.button("Tambah Barang Manual"):
                    if name:
                        data["item_counter"] += 1
                        code = f"ITM-{data['item_counter']:04d}"
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
                        save_data(data, st.session_state.current_brand)
                        st.session_state.notification = {"type": "success", "message": f"Barang '{name}' berhasil ditambahkan dengan kode {code}"}
                        st.rerun()
                    else:
                        st.session_state.notification = {"type": "error", "message": "Nama barang tidak boleh kosong!"}
                        st.rerun()

            with tab2:
                st.info("Format Excel: **Nama Barang | Qty | Satuan | Kategori**")
                file_upload = st.file_uploader("Upload File Excel", type=["xlsx"])
                if file_upload:
                    # Perbaikan: Tambahkan engine='openpyxl'
                    df_new = pd.read_excel(file_upload, engine='openpyxl')
                    required_cols = ["Nama Barang", "Qty", "Satuan", "Kategori"]

                    if all(col in df_new.columns for col in required_cols):
                        if st.button("Tambah dari Excel"):
                            for _, row in df_new.iterrows():
                                name = str(row["Nama Barang"])
                                qty = int(row["Qty"])
                                unit = str(row["Satuan"])
                                category = str(row["Kategori"])

                                data["item_counter"] += 1
                                code = f"ITM-{data['item_counter']:04d}"
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

                            save_data(data, st.session_state.current_brand)
                            st.session_state.notification = {"type": "success", "message": "Semua barang dari Excel berhasil ditambahkan!"}
                            st.rerun()
                    else:
                        st.error("Format Excel salah! Pastikan kolom: Nama Barang | Qty | Satuan | Kategori")

        elif menu == "Approve Request":
            st.markdown(f"## Approve / Reject Request Barang - Brand {st.session_state.current_brand.capitalize()}")
            st.divider()
            if data["pending_requests"]:
                # --- PERBAIKAN SCRIPT INI ---
                # Memproses data pending_requests untuk memastikan setiap item memiliki kunci 'attachment'
                processed_requests = []
                for req in data["pending_requests"]:
                    temp_req = req.copy()
                    if 'attachment' not in temp_req:
                        temp_req['attachment'] = None
                    processed_requests.append(temp_req)

                df_pending = pd.DataFrame(processed_requests)
                df_pending["Lampiran"] = df_pending["attachment"].apply(
                    lambda x: "Ada" if x else "Tidak Ada"
                )
                # --- AKHIR PERBAIKAN SCRIPT ---
                
                df_pending["Pilih"] = False
                edited_df = st.data_editor(df_pending, use_container_width=True, hide_index=True)
                
                selected_requests = edited_df.loc[(edited_df['Pilih']), :]

                col1, col2 = st.columns(2)
                
                if col1.button("Approve Selected"):
                    if not selected_requests.empty:
                        for index, req in selected_requests.iterrows():
                            match_idx = next((i for i, r in enumerate(data["pending_requests"])
                                              if r["item"] == req["item"]
                                              and r["qty"] == req["qty"]
                                              and r["user"] == req["user"]
                                              and r["type"] == req["type"]
                                              and r["timestamp"] == req["timestamp"]), None)
                            if match_idx is not None:
                                approved_req = data["pending_requests"].pop(match_idx)
                                for code, item in data["inventory"].items():
                                    if item["name"] == approved_req["item"]:
                                        if approved_req["type"] == "IN":
                                            item["qty"] += approved_req["qty"]
                                        else:
                                            item["qty"] -= approved_req["qty"]

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
                                            "timestamp": timestamp()
                                        })
                        save_data(data, st.session_state.current_brand)
                        st.session_state.notification = {"type": "success", "message": "Request terpilih berhasil di-approve."}
                        st.rerun()
                    else:
                        st.session_state.notification = {"type": "warning", "message": "Pilih setidaknya satu item untuk di-approve."}
                        st.rerun()
                
                if col2.button("Reject Selected"):
                    if not selected_requests.empty:
                        original_pending_requests = data["pending_requests"].copy()
                        new_pending_requests = []
                        rejected_count = 0
                        for original_req in original_pending_requests:
                            is_selected_for_rejection = False
                            for _, selected_req in selected_requests.iterrows():
                                if original_req["timestamp"] == selected_req["timestamp"] and original_req["user"] == selected_req["user"] and original_req["item"] == selected_req["item"]:
                                    is_selected_for_rejection = True
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
                                        "timestamp": timestamp()
                                    })
                                    break
                            if not is_selected_for_rejection:
                                new_pending_requests.append(original_req)
                        
                        data["pending_requests"] = new_pending_requests
                        save_data(data, st.session_state.current_brand)
                        st.session_state.notification = {"type": "success", "message": f"{rejected_count} request terpilih berhasil di-reject."}
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
                all_keys = ["action", "item", "qty", "stock", "unit", "user", "event", "do_number", "attachment", "timestamp"]
                processed_history = []
                for entry in data["history"]:
                    new_entry = {key: entry.get(key, None) for key in all_keys}
                    if new_entry.get("do_number") is None: new_entry["do_number"] = "-"
                    if new_entry.get("event") is None: new_entry["event"] = "-"
                    if new_entry.get("unit") is None: new_entry["unit"] = "-"
                    processed_history.append(new_entry)

                df_history_full = pd.DataFrame(processed_history)
                df_history_full['date'] = pd.to_datetime(df_history_full['timestamp']).dt.date

                def get_download_link(path):
                    if path and os.path.exists(path):
                        with open(path, "rb") as f:
                            bytes_data = f.read()
                        b64 = base64.b64encode(bytes_data).decode()
                        return f'<a href="data:application/pdf;base64,{b64}" download="{os.path.basename(path)}">Unduh</a>'
                    return 'Tidak Ada'
                
                df_history_full['Lampiran'] = df_history_full['attachment'].apply(get_download_link)

                col1, col2 = st.columns(2)
                start_date = col1.date_input("Tanggal Mulai", value=df_history_full['date'].min())
                end_date = col2.date_input("Tanggal Akhir", value=df_history_full['date'].max())
                
                col3, col4, col5 = st.columns(3)
                unique_users = ["Semua Pengguna"] + sorted(df_history_full["user"].unique())
                selected_user = col3.selectbox("Filter Pengguna", unique_users)

                unique_actions = ["Semua Tipe"] + sorted(df_history_full["action"].unique())
                selected_action = col4.selectbox("Filter Tipe Aksi", unique_actions)

                search_item = col5.text_input("Cari Nama Barang")

                df_filtered = df_history_full.copy()
                
                df_filtered = df_filtered[(df_filtered['date'] >= start_date) & (df_filtered['date'] <= end_date)]

                if selected_user != "Semua Pengguna":
                    df_filtered = df_filtered[df_filtered["user"] == selected_user]
                
                if selected_action != "Semua Tipe":
                    df_filtered = df_filtered[df_filtered["action"] == selected_action]

                if search_item:
                    df_filtered = df_filtered[df_filtered["item"].str.contains(search_item, case=False)]

                st.markdown(df_filtered[["action", "item", "qty", "unit", "stock", "user", "do_number", "event", "timestamp", "Lampiran"]].to_html(escape=False), unsafe_allow_html=True)
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

    elif role == "user":
        user_options = [
            "Request Barang IN",
            "Request Barang OUT",
            "Lihat Riwayat"
        ]
        menu = st.sidebar.radio("📌 Menu User", user_options)

        items = list(data["inventory"].values())

        if menu == "Request Barang IN":
            st.markdown(f"## Request Barang Masuk (Multi Item) - Brand {st.session_state.current_brand.capitalize()}")
            st.divider()
            
            if items:
                tab1, tab2 = st.tabs(["Input Manual", "Upload Excel"])
                
                with tab1:
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
                
                with tab2:
                    st.info("Format Excel: **Nama Barang | Qty | Satuan**")
                    file_upload = st.file_uploader("Upload File Excel", type=["xlsx"], key="in_excel_uploader")
                    if file_upload:
                        # Perbaikan: Tambahkan engine='openpyxl'
                        df_new = pd.read_excel(file_upload, engine='openpyxl')
                        required_cols = ["Nama Barang", "Qty", "Satuan"]
                        
                        if all(col in df_new.columns for col in required_cols):
                            if st.button("Tambah dari Excel", key="add_from_excel_in"):
                                for _, row in df_new.iterrows():
                                    item_name = str(row["Nama Barang"])
                                    item_exists = any(item['name'] == item_name for item in data['inventory'].values())
                                    if item_exists:
                                        st.session_state.req_in_items.append({
                                            "item": item_name,
                                            "qty": int(row["Qty"]),
                                            "unit": str(row["Satuan"]),
                                            "event": "-"
                                        })
                                st.session_state.notification = {"type": "success", "message": "Item dari Excel berhasil ditambahkan ke daftar request."}
                                st.rerun()
                        else:
                            st.error("Format Excel salah! Pastikan kolom: Nama Barang | Qty | Satuan")


                if st.session_state.req_in_items:
                    st.subheader("Daftar Item Request IN")
                    df_in = pd.DataFrame(st.session_state.req_in_items)
                    df_in["Pilih"] = False
                    edited_df_in = st.data_editor(df_in, use_container_width=True, hide_index=True)

                    selected_to_delete = edited_df_in.loc[(edited_df_in['Pilih']), :]
                    if st.button("Hapus Item Terpilih") and not selected_to_delete.empty:
                        st.session_state.req_in_items = [
                            req for i, req in enumerate(st.session_state.req_in_items)
                            if not edited_df_in.loc[i, "Pilih"]
                        ]
                        st.rerun()

                    st.divider()
                    st.subheader("Informasi Tambahan")
                    do_number = st.text_input("Nomor Surat Jalan", placeholder="Masukkan Nomor Surat Jalan")
                    uploaded_file = st.file_uploader("Upload PDF Delivery Order / Surat Jalan", type=["pdf"])
                    
                    if st.button("Ajukan Request IN Terpilih"):
                        selected_in = edited_df_in.loc[(edited_df_in['Pilih']), :]
                        if not selected_in.empty:
                            
                            attachment_path = None
                            if uploaded_file:
                                timestamp_str = datetime.now().strftime("%Y%m%d%H%M%S")
                                file_ext = uploaded_file.name.split(".")[-1]
                                attachment_path = os.path.join(UPLOADS_DIR, f"{st.session_state.username}_{timestamp_str}.{file_ext}")
                                with open(attachment_path, "wb") as f:
                                    f.write(uploaded_file.getbuffer())

                            for _, req in selected_in.iterrows():
                                request_data = {
                                    "type": "IN",
                                    "item": req["item"],
                                    "qty": int(req["qty"]),
                                    "unit": req.get("unit", "-"),
                                    "user": st.session_state.username,
                                    "event": "-",
                                    "do_number": do_number,
                                    "attachment": attachment_path,
                                    "timestamp": timestamp()
                                }
                                data["pending_requests"].append(request_data)
                                
                            save_data(data, st.session_state.current_brand)
                            st.session_state.req_in_items = [
                                req for i, req in enumerate(st.session_state.req_in_items)
                                if not edited_df_in.loc[i, "Pilih"]
                            ]
                            st.session_state.notification = {"type": "success", "message": f"{len(selected_in)} request IN berhasil diajukan dan menunggu approval."}
                            st.rerun()
                        else:
                            st.session_state.notification = {"type": "warning", "message": "Pilih setidaknya satu item untuk diajukan."}
                            st.rerun()
            else:
                st.info("Belum ada master barang. Silakan hubungi admin.")

        elif menu == "Request Barang OUT":
            st.markdown(f"## Request Barang Keluar (Multi Item) - Brand {st.session_state.current_brand.capitalize()}")
            st.divider()
            
            if items:
                col1, col2 = st.columns(2)
                idx = col1.selectbox(
                    "Pilih Barang", range(len(items)),
                    format_func=lambda x: f"{items[x]['name']} (Stok: {items[x]['qty']} {items[x].get('unit', '-')})"
                )
                
                max_qty = items[idx]["qty"]
                qty = col2.number_input("Jumlah", min_value=1, max_value=max_qty, step=1)

                if st.button("Tambah Item OUT"):
                    st.session_state.req_out_items.append({
                        "item": items[idx]["name"],
                        "qty": qty,
                        "unit": items[idx].get("unit", "-"),
                        "event": "-"
                    })

                if st.session_state.req_out_items:
                    st.subheader("Daftar Item Request OUT")
                    df_out = pd.DataFrame(st.session_state.req_out_items)
                    df_out["Pilih"] = False
                    edited_df_out = st.data_editor(df_out, use_container_width=True, hide_index=True)

                    selected_to_delete = edited_df_out.loc[(edited_df_out['Pilih']), :]
                    if st.button("Hapus Item Terpilih", key="delete_out") and not selected_to_delete.empty:
                        st.session_state.req_out_items = [
                            req for i, req in enumerate(st.session_state.req_out_items)
                            if not edited_df_out.loc[i, "Pilih"]
                        ]
                        st.rerun()

                    st.divider()
                    event_name = st.text_input("Nama Event", placeholder="Misal: Pameran, Acara Kantor")
                    if st.button("Ajukan Request OUT Terpilih"):
                        selected_out = edited_df_out.loc[(edited_df_out['Pilih']), :]
                        if not selected_out.empty:
                            for _, req in selected_out.iterrows():
                                request_data = {
                                    "type": "OUT",
                                    "item": req["item"],
                                    "qty": int(req["qty"]),
                                    "unit": req.get("unit", "-"),
                                    "user": st.session_state.username,
                                    "event": event_name,
                                    "do_number": "-",
                                    "attachment": None,
                                    "timestamp": timestamp()
                                }
                                data["pending_requests"].append(request_data)

                            save_data(data, st.session_state.current_brand)
                            st.session_state.req_out_items = [
                                req for i, req in enumerate(st.session_state.req_out_items)
                                if not edited_df_out.loc[i, "Pilih"]
                            ]
                            st.session_state.notification = {"type": "success", "message": f"{len(selected_out)} request OUT berhasil diajukan dan menunggu approval."}
                            st.rerun()
                        else:
                            st.session_state.notification = {"type": "warning", "message": "Pilih setidaknya satu item untuk diajukan."}
                            st.rerun()
            else:
                st.info("Belum ada master barang. Silakan hubungi admin.")

        elif menu == "Lihat Riwayat":
            st.markdown(f"## Riwayat Saya - Brand {st.session_state.current_brand.capitalize()}")
            st.divider()

            if data["history"]:
                my_history = [h for h in data["history"] if h["user"] == st.session_state.username]
                if my_history:
                    df_my_history = pd.DataFrame(my_history)
                    st.dataframe(df_my_history, use_container_width=True, hide_index=True)
                else:
                    st.info("Anda belum memiliki riwayat transaksi.")
            else:
                st.info("Tidak ada riwayat transaksi.")
