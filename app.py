import streamlit as st
import pandas as pd
import datetime
import gspread
from google.oauth2.service_account import Credentials
from fpdf import FPDF
from fpdf.enums import XPos, YPos

# ---------------------------------------------------------
# SETUP HALAMAN STREAMLIT
# ---------------------------------------------------------
st.set_page_config(
    page_title="Monitoring Surat Kapal",
    page_icon="🚢",
    layout="wide"
)

# Ganti dengan SPREADSHEET_ID milikmu
SPREADSHEET_ID = "1..."  # Masukkan Spreadsheet ID kamu di sini jika belum

# ---------------------------------------------------------
# KONEKSI GOOGLE SHEETS VIA STREAMLIT SECRETS
# ---------------------------------------------------------
def get_gspread_client():
    credentials_dict = dict(st.secrets["gcp_service_account"])
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
    return gspread.authorize(creds)

@st.cache_data(ttl=60)
def load_data():
    try:
        gc = get_gspread_client()
        sh = gc.open_by_key(SPREADSHEET_ID)
        worksheet = sh.sheet1
        data = worksheet.get_all_values()
        
        # Asumsi header kapal ada di baris ke-2
        headers = data[1]
        df_raw = pd.DataFrame(data[2:], columns=headers)
        return df_raw
    except Exception as e:
        st.error(f"Gagal mengambil data dari Google Sheets: {e}")
        return pd.DataFrame()

# Class untuk PDF Report
class PDFReport(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 10, "LAPORAN MONITORING SURAT KAPAL", border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Halaman {self.page_no()}", border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")

# Load Data
df = load_data()

st.title("🚢 Monitoring Masa Berlaku Surat Kapal")

if not df.empty:
    # ---------------------------------------------------------
    # SIDEBAR: FITUR UPDATE TANGGAL SURAT (DROPDOWN TGL, BULAN, TAHUN)
    # ---------------------------------------------------------
    st.sidebar.header("✏️ Update Tanggal Surat")
    with st.sidebar.form("form_update_tgl"):
        list_kapal = sorted(list(df["Nama Kapal"].dropna().unique())) if "Nama Kapal" in df.columns else []
        selected_kapal_input = st.selectbox("Pilih Kapal:", list_kapal)

        # Filter Jenis Surat sesuai Kapal
        if "Jenis Surat" in df.columns:
            list_surat_by_kapal = sorted(
                list(df[df["Nama Kapal"] == selected_kapal_input]["Jenis Surat"].dropna().unique())
            )
        else:
            list_surat_by_kapal = []

        selected_surat_input = st.selectbox("Pilih Jenis Surat:", list_surat_by_kapal)

        st.markdown("**Tanggal Expired Baru:**")
        col_d, col_m, col_y = st.columns([1, 1, 1])
        
        today = datetime.date.today()
        
        with col_d:
            day_val = st.selectbox("Tgl", list(range(1, 32)), index=today.day - 1)
        with col_m:
            months = [
                "Januari", "Februari", "Maret", "April", "Mei", "Juni",
                "Juli", "Agustus", "September", "Oktober", "November", "Desember"
            ]
            month_val = st.selectbox("Bulan", range(1, 13), format_func=lambda x: months[x-1], index=today.month - 1)
        with col_y:
            current_year = today.year
            year_val = st.selectbox("Tahun", list(range(current_year - 2, current_year + 15)), index=2)

        btn_update = st.form_submit_button("💾 Update ke Google Sheets")

    if btn_update:
        try:
            tgl_baru = datetime.date(year_val, month_val, day_val)
            
            with st.spinner("Memperbarui data di Google Sheets..."):
                gc = get_gspread_client()
                sh = gc.open_by_key(SPREADSHEET_ID)
                worksheet = sh.sheet1

                cell_surat = worksheet.find(selected_surat_input)
                row_header = worksheet.row_values(2)
                col_idx = None
                for idx, val in enumerate(row_header, start=1):
                    if selected_kapal_input.lower() in val.lower():
                        col_idx = idx
                        break

                if cell_surat and col_idx:
                    formatted_date = tgl_baru.strftime("%d/%m/%Y")
                    worksheet.update_cell(cell_surat.row, col_idx, formatted_date)

                    st.sidebar.success(f"✅ Berhasil update {selected_surat_input} ({selected_kapal_input}) -> {formatted_date}")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.sidebar.error("❌ Nama Kapal atau Jenis Surat tidak ditemukan di posisi layout Google Sheets.")
        except ValueError:
            st.sidebar.error("⚠️ Kombinasi tanggal tidak valid (misal: 31 Februari). Silakan cek kembali!")
        except Exception as e_update:
            st.sidebar.error(f"Gagal Update Data: {e_update}")

    # Display Data Tabular
    st.subheader("📋 Data Sertifikat & Surat Kapal")
    st.dataframe(df, width="stretch")
else:
    st.info("Data belum tersedia atau gagal dimuat dari Google Sheets.")
