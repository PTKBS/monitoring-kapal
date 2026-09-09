import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# --- 1. KONFIGURASI HALAMAN STREAMLIT ---
st.set_page_config(
    page_title="Monitoring Kapal & Surat",
    page_icon="🚢",
    layout="wide"
)

st.title("🚢 Aplikasi Monitoring Kapal & Surat")

# --- 2. KONEKSI KE GOOGLE SHEETS VIA STREAMLIT SECRETS ---
@st.cache_resource
def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    # Mengambil kredensial dari Streamlit Secrets [gcp_service_account]
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scopes
    )
    return gspread.authorize(credentials)

try:
    gc = get_gspread_client()
    
    # OPSIONAL: Ganti nama spreadsheet di bawah ini jika nama filenya berbeda, 
    # atau gunakan: sh = gc.open_by_key("ID_SPREADSHEET_KAMU")
    sh = gc.open("Monitoring Kapal") 
    worksheet = sh.sheet1
except Exception as e:
    st.error(f"⚠️ Gagal terhubung ke Google Sheets: {e}")
    st.stop()

# --- 3. FUNGSI LOAD DATA (HEADER DARI BARIS 2, DATA DARI BARIS 3) ---
def load_data():
    raw_data = worksheet.get_all_values()
    
    if len(raw_data) < 2:
        st.warning("Data di Google Sheets belum memiliki header di Baris 2.")
        return pd.DataFrame()
    
    # Baris 2 (index 1) sebagai Header / Nama Kolom
    headers = raw_data[1]
    
    # Baris 3 ke bawah (index 2:) sebagai Isi Data
    data_rows = raw_data[2:] if len(raw_data) > 2 else []
    
    df = pd.DataFrame(data_rows, columns=headers)
    return df

df = load_data()

# --- 4. EKSTRAKSI LIST KAPAL & SURAT UNTUK DROPDOWN ---
# Silakan sesuaikan string 'Nama Kapal' & 'Nama Surat' jika di Sheet tulisan kapitalnya berbeda
kolom_kapal = "Nama Kapal" if "Nama Kapal" in df.columns else (df.columns[0] if len(df.columns) > 0 else "")
kolom_surat = "Nama Surat" if "Nama Surat" in df.columns else (df.columns[1] if len(df.columns) > 1 else "")

if not df.empty and kolom_kapal in df.columns and kolom_surat in df.columns:
    # Ambil nilai unik dan buang string kosong/NaN
    list_kapal = [k for k in df[kolom_kapal].dropna().unique().tolist() if str(k).strip() != ""]
    list_surat = [s for s in df[kolom_surat].dropna().unique().tolist() if str(s).strip() != ""]
else:
    list_kapal = []
    list_surat = []

# Fallback jika data di sheet masih kosong / belum ada opsi
if not list_kapal:
    list_kapal = ["Tugboat A", "Tugboat B", "Barge C"]
if not list_surat:
    list_surat = ["Sertifikat Keselamatan", "PAS Besar", "Izin Layak Laut", "Surat Ukur"]

# --- 5. FORM INPUT DATA BARU ---
st.subheader("📝 Input Data / Update Surat Kapal")

with st.form(key="form_input_kapal", clear_on_submit=True):
    col1, col2 = st.columns(2)
    
    with col1:
        selected_kapal = st.selectbox("Pilih Nama Kapal", options=list_kapal)
        selected_surat = st.selectbox("Pilih Nama Surat", options=list_surat)
    
    with col2:
        tgl_terbit = st.date_input("Tanggal Terbit Surat")
        tgl_kadaluarsa = st.date_input("Tanggal Kadaluarsa / Expired")
        keterangan = st.text_input("Keterangan Catatan (Opsional)")

    submit_button = st.form_submit_button(label="💾 Simpan Data ke Google Sheets")

if submit_button:
    try:
        # Menyiapkan baris data baru sesuai urutan kolom di sheet
        new_row = [
            selected_kapal,
            selected_surat,
            tgl_terbit.strftime("%Y-%m-%d"),
            tgl_kadaluarsa.strftime("%Y-%m-%d"),
            keterangan
        ]
        
        # Simpan ke baris paling bawah di Google Sheets
        worksheet.append_row(new_row)
        
        st.success(f"✅ Data untuk **{selected_kapal}** - **{selected_surat}** berhasil disimpan!")
        st.cache_resource.clear()
        st.rerun()
    except Exception as err:
        st.error(f"❌ Gagal menyimpan data: {err}")

# --- 6. TAMPILKAN TABEL MONITORING DATA ---
st.divider()
st.subheader("📊 Data Monitoring Kapal Saat Ini")

if not df.empty:
    st.dataframe(df, use_container_width=True)
else:
    st.info("Belum ada data yang tersimpan di spreadsheet.")
