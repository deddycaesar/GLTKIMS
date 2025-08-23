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
    "gulavit": "YOUR_GULAVIT_SHEET_ID_HERE",  # Ganti dengan ID spreadsheet Gulavit Anda
    "takokak": "YOUR_TAKOKAK_SHEET_ID_HERE"   # Ganti dengan ID spreadsheet Takokak Anda
}
if USE_SHEETS:
    import gspread
    from gspread_pandas import Spread
    from google.oauth2.service_account import Credentials
    from gsheets_backend import load_from_sheets, save_to_sheets, update_sheet_with_new_data
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        gc = gspread.authorize(creds)
        st.session_state.gc = gc
    except Exception as e:
        st.error(f"Error: Gagal mengotentikasi ke Google Sheets. {e}")
        USE_SHEETS = False

# ==== Helper functions ====
def save_data(data, brand):
    if USE_SHEETS:
        save_to_sheets(st.session_state.gc, data, SHEET_IDS[brand], brand)
    else:
        file_path = DATA_FILES[brand]
        with open(file_path, 'w') as f:
            json.dump(data, f)

def load_data(brand):
    if USE_SHEETS:
        return load_from_sheets(st.session_state.gc, SHEET_IDS[brand], brand)
    else:
        file_path = DATA_FILES[brand]
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                return json.load(f)
        else:
            return {"inventory": [], "history": [], "pending_requests": []}

def get_base64_image(image_path):
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode("utf-8")

def create_download_link(df, filename):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    data = output.getvalue()
    b64 = base64.b64encode(data).decode('utf8')
    return f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="{filename}">Download as Excel</a>'

def login():
    st.markdown("## Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        # Dummy login, ganti dengan otentikasi nyata
        if username == "admin" and password == "admin":
            st.session_state.logged_in = True
            st.session_state.username = username
            st.success("Login berhasil!")
            st.experimental_rerun()
        else:
            st.error("Username atau password salah.")

def add_inventory():
    st.markdown("## Tambah Inventaris")
    data = st.session_state.data
    st.markdown(f"**Brand:** {st.session_state.current_brand.upper()}")

    item_name = st.text_input("Nama Item")
    quantity = st.number_input("Jumlah", min_value=0, step=1)
    unit = st.selectbox("Unit", ["Kilo", "Gram", "Liter", "Meter", "Buah", "Pcs"])

    if st.button("Tambahkan Item"):
        if item_name and quantity > 0:
            new_item = {
                "item": item_name,
                "quantity": quantity,
                "unit": unit
            }
            data["inventory"].append(new_item)
            save_data(data, st.session_state.current_brand) # Perubahan utama di sini
            st.success("Item berhasil ditambahkan!")
            st.experimental_rerun()
        else:
            st.error("Nama item dan jumlah tidak boleh kosong.")

def view_inventory():
    st.markdown("## Lihat Inventaris")
    data = st.session_state.data
    st.markdown(f"**Brand:** {st.session_state.current_brand.upper()}")

    if data["inventory"]:
        df = pd.DataFrame(data["inventory"])
        st.dataframe(df)

        st.markdown(create_download_link(df, "inventory.xlsx"), unsafe_allow_html=True)
    else:
        st.info("Inventaris kosong.")

def add_transaction():
    st.markdown("## Transaksi")
    data = st.session_state.data
    st.markdown(f"**Brand:** {st.session_state.current_brand.upper()}")

    trans_type = st.selectbox("Tipe Transaksi", ["IN", "OUT"])
    item_code = st.text_input("Kode Item")
    item_name = st.text_input("Nama Item")
    quantity = st.number_input("Jumlah", min_value=0, step=1)
    unit = st.selectbox("Unit", ["Kilo", "Gram", "Liter", "Meter", "Buah", "Pcs"])
    notes = st.text_area("Catatan")
    do_number = st.text_input("Nomor DO (Opsional)")
    event = st.text_input("Acara/Proyek (Opsional)")

    if st.button("Simpan Transaksi"):
        if not (item_code and item_name and quantity > 0):
            st.error("Kode item, nama item, dan jumlah tidak boleh kosong.")
        else:
            history_entry = {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "timestamp": datetime.now().isoformat(),
                "user": st.session_state.username,
                "code": item_code,
                "item": item_name,
                "trans_type": trans_type,
                "qty": quantity,
                "unit": unit,
                "notes": notes,
                "do_number": do_number,
                "event": event
            }
            data["history"].append(history_entry)
            save_data(data, st.session_state.current_brand) # Perubahan utama di sini
            st.success("Transaksi berhasil ditambahkan!")
            st.experimental_rerun()

def view_history():
    st.markdown("## Riwayat Transaksi")
    data = st.session_state.data
    st.markdown(f"**Brand:** {st.session_state.current_brand.upper()}")

    if data["history"]:
        df = pd.DataFrame(data["history"])
        df = df.sort_values(by="timestamp", ascending=False)
        st.dataframe(df)
        st.markdown(create_download_link(df, "history.xlsx"), unsafe_allow_html=True)
    else:
        st.info("Riwayat transaksi kosong.")

def add_pending_request():
    st.markdown("## Ajukan Permintaan")
    data = st.session_state.data
    st.markdown(f"**Brand:** {st.session_state.current_brand.upper()}")

    request_type = st.selectbox("Tipe Permintaan", ["Request IN", "Request OUT"])
    item_code = st.text_input("Kode Item")
    item_name = st.text_input("Nama Item")
    quantity = st.number_input("Jumlah", min_value=0, step=1)
    unit = st.selectbox("Unit", ["Kilo", "Gram", "Liter", "Meter", "Buah", "Pcs"])

    if st.button("Kirim Permintaan"):
        if not (item_code and item_name and quantity > 0):
            st.error("Kode item, nama item, dan jumlah tidak boleh kosong.")
        else:
            new_request = {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "timestamp": datetime.now().isoformat(),
                "user": st.session_state.username,
                "type": request_type,
                "code": item_code,
                "item": item_name,
                "qty": quantity,
                "unit": unit,
            }
            data["pending_requests"].append(new_request)
            save_data(data, st.session_state.current_brand) # Perubahan utama di sini
            st.success("Permintaan berhasil dikirim!")
            st.experimental_rerun()

def view_pending_requests():
    st.markdown("## Permintaan Tertunda")
    data = st.session_state.data
    st.markdown(f"**Brand:** {st.session_state.current_brand.upper()}")

    if data["pending_requests"]:
        df = pd.DataFrame(data["pending_requests"])
        st.dataframe(df)
    else:
        st.info("Tidak ada permintaan tertunda.")

def dashboard():
    st.markdown("## Dashboard")
    st.markdown(f"**Brand:** {st.session_state.current_brand.upper()}")

    data = st.session_state.data

    st.subheader("Ringkasan Data")

    col1, col2 = st.columns(2)
    with col1:
        st.metric(label="Total Item Inventaris", value=len(data["inventory"]))
    with col2:
        st.metric(label="Total Transaksi", value=len(data["history"]))

    # Grafik opsional
    if _ALT_OK and data["history"]:
        st.subheader("Grafik Transaksi Harian")
        df_history = pd.DataFrame(data["history"])
        df_history["date"] = pd.to_datetime(df_history["date"])
        df_history_agg = df_history.groupby("date").size().reset_index(name="Jumlah Transaksi")

        chart = alt.Chart(df_history_agg).mark_bar().encode(
            x=alt.X("date", axis=alt.Axis(title="Tanggal")),
            y=alt.Y("Jumlah Transaksi", axis=alt.Axis(title="Jumlah Transaksi"))
        ).properties(
            title="Riwayat Transaksi per Hari"
        )
        st.altair_chart(chart, use_container_width=True)


def admin_view_requests():
    st.markdown("## Admin: Kelola Permintaan")
    data = st.session_state.data
    st.markdown(f"**Brand:** {st.session_state.current_brand.upper()}")

    if data["pending_requests"]:
        st.subheader("Daftar Permintaan Masuk")
        for index, req in enumerate(data["pending_requests"]):
            st.markdown(f"**Permintaan dari:** {req.get('user')}")
            st.markdown(f"**Tipe:** {req.get('type')}")
            st.markdown(f"**Item:** {req.get('item')} ({req.get('code')})")
            st.markdown(f"**Jumlah:** {req.get('qty')} {req.get('unit')}")
            st.markdown("---")

            col1, col2 = st.columns(2)
            if col1.button("Setujui Permintaan", key=f"app_{index}"):
                # Tambahkan ke riwayat
                history_entry = {
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "timestamp": datetime.now().isoformat(),
                    "user": "admin",
                    "code": req.get("code"),
                    "item": req.get("item"),
                    "trans_type": req.get("type").replace("Request ", ""), # IN atau OUT
                    "qty": req.get("qty"),
                    "unit": req.get("unit"),
                    "notes": f"Permintaan disetujui dari {req.get('user')}",
                    "do_number": "-",
                    "event": "-"
                }
                data["history"].append(history_entry)
                # Hapus dari pending
                data["pending_requests"].pop(index)
                save_data(data, st.session_state.current_brand) # Tambahkan baris ini
                st.success("Permintaan berhasil disetujui dan dicatat!")
                st.experimental_rerun()

            if col2.button("Tolak Permintaan", key=f"rej_{index}"):
                data["pending_requests"].pop(index)
                save_data(data, st.session_state.current_brand) # Tambahkan baris ini
                st.info("Permintaan berhasil ditolak!")
                st.experimental_rerun()
    else:
        st.info("Tidak ada permintaan masuk.")

# Fungsi main app
def main_app():
    st.sidebar.title("Navigasi")
    menu = st.sidebar.selectbox("Pilih Halaman", ["Dashboard", "Tambah Inventaris", "Lihat Inventaris", "Transaksi", "Riwayat Transaksi", "Permintaan", "Admin (Kelola Permintaan)", "Logout"])
    st.sidebar.markdown(f"Pengguna: **{st.session_state.username}**")

    if menu == "Dashboard":
        dashboard()
    elif menu == "Tambah Inventaris":
        add_inventory()
    elif menu == "Lihat Inventaris":
        view_inventory()
    elif menu == "Transaksi":
        add_transaction()
    elif menu == "Riwayat Transaksi":
        view_history()
    elif menu == "Permintaan":
        add_pending_request()
        view_pending_requests()
    elif menu == "Admin (Kelola Permintaan)":
        if st.session_state.username == "admin":
            admin_view_requests()
        else:
            st.error("Anda tidak memiliki akses ke halaman ini.")
    elif menu == "Logout":
        st.session_state.logged_in = False
        st.session_state.username = None
        st.info("Anda telah logout.")
        st.experimental_rerun()

# Logic utama
st.set_page_config(
    page_title="Sistem Manajemen Inventaris",
    page_icon=ICON_URL,
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inisialisasi session state jika belum ada
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = None
if "current_brand" not in st.session_state:
    st.session_state.current_brand = "gulavit"

# Tampilan halaman login atau aplikasi utama
if st.session_state.logged_in:
    st.sidebar.title("Pilih Brand")
    brand = st.sidebar.selectbox("Pilih Brand", list(DATA_FILES.keys()))

    if brand != st.session_state.current_brand:
        st.session_state.current_brand = brand
        st.session_state.data = load_data(st.session_state.current_brand)
        st.experimental_rerun()

    # Load data
    if "data" not in st.session_state:
        st.session_state.data = load_data(st.session_state.current_brand)

    main_app()
else:
    login()
