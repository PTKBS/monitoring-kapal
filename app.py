import streamlit as st
import pandas as pd
import gspread
from datetime import datetime
from fpdf import FPDF

# --- 1. KONFIGURASI HALAMAN ---
st.set_page_config(
    page_title="Monitoring Kapal & Surat",
    page_icon="🚢",
    layout="wide"
)

st.title("🚢 Aplikasi Monitoring Surat Kapal")

# --- 2. KONEKSI GOOGLE SHEETS ---
@st.cache_resource
def get_worksheet():
    credentials = dict(st.secrets["gcp_service_account"])
    if "private_key" in credentials:
        credentials["private_key"] = credentials["private_key"].replace("\\n", "\n")
        
    gc = gspread.service_account_from_dict(credentials)
    
    # 💡 PASTE SPREADSHEET ID KAMU DI SINI (dari URL browser)
    SPREADSHEET_ID = "PASTE_ID_SPREADSHEET_KAMU_DI_SINI"
    
    sh = gc.open_by_key(SPREADSHEET_ID)
    return sh.sheet1

try:
    worksheet = get_worksheet()
except Exception as e:
    st.error(f"⚠️ Gagal terhubung ke Google Sheets: {e}")
    st.stop()

# --- 3. FUNGSI BACA DATA (HEADER DI BARIS 2, DATA BARIS 3+) ---
def load_data():
    raw_data = worksheet.get_all_values()
    if len(raw_data) < 2:
        return pd.DataFrame()
    
    headers = [h.strip() for h in raw_data[1]]
    data_rows = raw_data[2:] if len(raw_data) > 2 else []
    
    df = pd.DataFrame(data_rows, columns=headers)
    return df

df = load_data()

# --- 4. PERHITUNGAN STATUS EXPIRED & SISA HARI ---
if not df.empty:
    col_kapal = next((c for c in df.columns if "kapal" in c.lower()), df.columns[0])
    col_surat = next((c for c in df.columns if "surat" in c.lower()), df.columns[1])
    col_exp = next((c for c in df.columns if "exp" in c.lower() or "kadaluarsa" in c.lower() or "berlaku" in c.lower()), None)
    
    if col_exp:
        df['Exp_Date'] = pd.to_datetime(df[col_exp], errors='coerce')
        today = datetime.now()
        
        df['Sisa Hari'] = (df['Exp_Date'] - today).dt.days
        
        def check_status(days):
            if pd.isna(days):
                return "⚪ Tanpa Tanggal"
            elif days < 0:
                return "🔴 EXPIRED"
            elif days <= 30:
                return "🟡 Kritis (<= 30 Hari)"
            elif days <= 60:
                return "🔵 Perhatian (<= 60 Hari)"
            else:
                return "🟢 Aman"
                
        df['Status Surat'] = df['Sisa Hari'].apply(check_status)

# --- 5. EKSTRAKSI DROPDOWN ---
if not df.empty:
    list_kapal = [k for k in df[col_kapal].dropna().unique().tolist() if str(k).strip() != ""]
    list_surat = [s for s in df[col_surat].dropna().unique().tolist() if str(s).strip() != ""]
else:
    list_kapal, list_surat = [], []

if not list_kapal: list_kapal = ["Tugboat A", "Tugboat B", "Barge C"]
if not list_surat: list_surat = ["Sertifikat Keselamatan", "PAS Besar", "Izin Layak Laut"]

# --- 6. FORM INPUT DATA BARU ---
st.subheader("📝 Input / Update Surat Kapal")
with st.form(key="form_input_kapal", clear_on_submit=True):
    col1, col2 = st.columns(2)
    with col1:
        selected_kapal = st.selectbox("Pilih Nama Kapal", options=list_kapal)
        selected_surat = st.selectbox("Pilih Nama Surat", options=list_surat)
    with col2:
        tgl_terbit = st.date_input("Tanggal Terbit")
        tgl_kadaluarsa = st.date_input("Tanggal Kadaluarsa / Expired")
        keterangan = st.text_input("Keterangan Catatan")

    submit_button = st.form_submit_button(label="💾 Simpan Data ke Google Sheets")

if submit_button:
    try:
        new_row = [
            selected_kapal,
            selected_surat,
            tgl_terbit.strftime("%Y-%m-%d"),
            tgl_kadaluarsa.strftime("%Y-%m-%d"),
            keterangan
        ]
        worksheet.append_row(new_row)
        st.success(f"✅ Data **{selected_kapal}** - **{selected_surat}** berhasil disimpan!")
        st.cache_resource.clear()
        st.rerun()
    except Exception as err:
        st.error(f"❌ Gagal menyimpan data: {err}")

# --- 7. TAMPILAN MONITORING & FILTER ---
st.divider()
st.subheader("📊 Data Monitoring Surat Kapal")

if not df.empty:
    c1, c2, c3 = st.columns(3)
    exp_count = len(df[df['Status Surat'] == "🔴 EXPIRED"])
    warn_count = len(df[df['Status Surat'].str.contains("Kritis|Perhatian", na=False)])
    safe_count = len(df[df['Status Surat'] == "🟢 Aman"])
    
    c1.metric("🔴 Expired", f"{exp_count} Surat")
    c2.metric("🟡 Mendekati Expired", f"{warn_count} Surat")
    c3.metric("🟢 Aman", f"{safe_count} Surat")

    display_df = df.drop(columns=['Exp_Date'], errors='ignore')
    st.dataframe(display_df, use_container_width=True)

    # --- 8. FITUR SAVE TO PDF (KOMPATIBEL FPDF2) ---
    st.divider()
    st.subheader("📄 Export Laporan ke PDF")

    def generate_pdf(dataframe):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", 'B', 14)
        pdf.cell(190, 10, text="Laporan Monitoring Surat Kapal", new_x="LMARGIN", new_y="NEXT", align='C')
        pdf.set_font("Helvetica", '', 10)
        pdf.cell(190, 8, text=f"Tanggal Cetak: {datetime.now().strftime('%Y-%m-%d %H:%M')}", new_x="LMARGIN", new_y="NEXT", align='C')
        pdf.ln(5)

        # Header Tabel
        pdf.set_font("Helvetica", 'B', 9)
        cols = [col_kapal, col_surat, "Sisa Hari", "Status Surat"]
        w = [45, 65, 30, 50]
        for i, col in enumerate(cols):
            pdf.cell(w[i], 8, text=str(col), border=1, align='C')
        pdf.ln()

        # Isi Tabel
        pdf.set_font("Helvetica", '', 8)
        for _, row in dataframe.iterrows():
            pdf.cell(w[0], 7, text=str(row.get(col_kapal, ''))[:22], border=1)
            pdf.cell(w[1], 7, text=str(row.get(col_surat, ''))[:35], border=1)
            pdf.cell(w[2], 7, text=str(row.get("Sisa Hari", '-')), border=1, align='C')
            
            # Bersihkan emoji agar fpdf2 standar font tidak error
            status_clean = str(row.get("Status Surat", '-')).encode('ascii', 'ignore').decode('ascii').strip()
            pdf.cell(w[3], 7, text=status_clean, border=1, align='C')
            pdf.ln()

        # Output sebagai bytes menggunakan output() standar fpdf2
        return bytes(pdf.output())

    pdf_data = generate_pdf(df)
    st.download_button(
        label="📥 Download Laporan (Save to PDF)",
        data=pdf_data,
        file_name=f"Laporan_Monitoring_Kapal_{datetime.now().strftime('%Y%m%d')}.pdf",
        mime="application/pdf"
    )
else:
    st.info("Belum ada data yang tersimpan di spreadsheet.")
