import streamlit as st
import pandas as pd
import gspread
from datetime import datetime, timedelta
from fpdf import FPDF

# --- 1. KONFIGURASI HALAMAN ---
st.set_page_config(
    page_title="Monitoring Surat Kapal",
    page_icon="🚢",
    layout="wide"
)

st.title("🚢 Laporan Monitoring Surat & Endorsement Kapal")

# --- 2. KONEKSI GOOGLE SHEETS ---
@st.cache_resource
def get_worksheet():
    credentials = dict(st.secrets["gcp_service_account"])
    if "private_key" in credentials:
        credentials["private_key"] = credentials["private_key"].replace("\\n", "\n")
        
    gc = gspread.service_account_from_dict(credentials)
    
    # 💡 PASTE SPREADSHEET ID KAMU DI SINI
    SPREADSHEET_ID = "1ovR8ZxhQmLYv73iSu1xWEXsG1ipL448fmIhs4zJ8P6o"
    
    sh = gc.open_by_key(SPREADSHEET_ID)
    return sh.sheet1

try:
    worksheet = get_worksheet()
except Exception as e:
    st.error(f"⚠️ Gagal terhubung ke Google Sheets: {e}")
    st.stop()

# --- 3. PEMBACAAN DAN OLAH DATA ---
def load_and_process_data():
    raw_data = worksheet.get_all_values()
    if not raw_data:
        return pd.DataFrame()
    
    # Ambil baris header & data
    if len(raw_data) >= 2 and any(raw_data[1]):
        headers = [str(h).strip() for h in raw_data[1]]
        data_rows = raw_data[2:] if len(raw_data) > 2 else []
    else:
        headers = [str(h).strip() for h in raw_data[0]]
        data_rows = raw_data[1:] if len(raw_data) > 1 else []
        
    df = pd.DataFrame(data_rows)
    if df.empty:
        return pd.DataFrame()
        
    df = df.iloc[:, :len(headers)]
    df.columns = [h if h != "" else f"Kolom_{i+1}" for i, h in enumerate(headers)]

    # Otomatisasi Pencarian Kolom
    col_kapal = next((c for c in df.columns if "kapal" in c.lower()), df.columns[0])
    col_surat = next((c for c in df.columns if "surat" in c.lower()), df.columns[1] if len(df.columns) > 1 else df.columns[0])
    col_exp = next((c for c in df.columns if any(k in c.lower() for k in ["exp", "kadaluarsa", "berlaku"])), None)

    today = datetime.now()
    
    # Parse Tanggal Expired
    if col_exp and col_exp in df.columns:
        df['Exp_Dt'] = pd.to_datetime(df[col_exp], errors='coerce', dayfirst=True)
    else:
        df['Exp_Dt'] = pd.NaT

    # Perhitungan Sisa Hari
    df['Sisa_Hari_Num'] = (df['Exp_Dt'] - today).dt.days

    # 1. Format Tgl Expired (DD-Mon-YYYY)
    df['Tgl Expired'] = df['Exp_Dt'].apply(lambda d: d.strftime("%d-%b-%Y") if pd.notna(d) else "-")

    # 2. Format Sisa Hari ("14 h")
    df['Sisa Hari'] = df['Sisa_Hari_Num'].apply(lambda x: f"{int(x)} h" if pd.notna(x) else "-")

    # 3. Format Status Exact
    def get_status_text(days):
        if pd.isna(days):
            return "TANPA TANGGAL"
        elif days < 0:
            return "EXPIRED"
        elif days <= 14:
            return f"SANGAT DESAK (<={int(days)} Hari)"
        elif days <= 30:
            return "KRITIS (<=30 Hari)"
        else:
            return "AMAN"

    df['Status'] = df['Sisa_Hari_Num'].apply(get_status_text)

    # 4. Format Window Endorse (±3 Bln) -> Rentang 3 Bulan Sebelum s/d 3 Bulan Sesudah
    def get_window_endorse(row):
        surat_name = str(row.get(col_surat, "")).upper()
        exp_dt = row.get('Exp_Dt')
        
        # Hanya dihitung jika ada kata ENDORSE pada jenis surat / tanggal valid
        if "ENDORSE" in surat_name and pd.notna(exp_dt):
            start_window = exp_dt - timedelta(days=90)
            end_window = exp_dt + timedelta(days=90)
            return f"{start_window.strftime('%d %b %Y')} s/d {end_window.strftime('%d %b %Y')}"
        return "-"

    df['Window Endorse (±3 Bln)'] = df.apply(get_window_endorse, axis=1)

    # Susun DataFrame Persis Sesuai Kolom Gambar
    final_df = pd.DataFrame()
    final_df['Nama Kapal'] = df[col_kapal]
    final_df['Jenis Surat'] = df[col_surat]
    final_df['Tgl Expired'] = df['Tgl Expired']
    final_df['Sisa Hari'] = df['Sisa Hari']
    final_df['Status'] = df['Status']
    final_df['Window Endorse (±3 Bln)'] = df['Window Endorse (±3 Bln)']
    
    return final_df

df_table = load_and_process_data()

# --- 4. TAMPILAN TANGGAL CETAK ---
st.caption(f"Tanggal Cetak: {datetime.now().strftime('%d-%b-%Y')}")

# --- 5. SIDEBAR FILTER ---
st.sidebar.header("🔍 Filter Data")
if not df_table.empty:
    list_kapal = sorted([k for k in df_table['Nama Kapal'].dropna().unique().tolist() if str(k).strip() != ""])
    list_surat = sorted([s for s in df_table['Jenis Surat'].dropna().unique().tolist() if str(s).strip() != ""])
    
    selected_kapal = st.sidebar.multiselect("Nama Kapal", options=list_kapal, default=list_kapal)
    selected_surat = st.sidebar.multiselect("Jenis Surat", options=list_surat, default=list_surat)
    
    if selected_kapal:
        df_table = df_table[df_table['Nama Kapal'].isin(selected_kapal)]
    if selected_surat:
        df_table = df_table[df_table['Jenis Surat'].isin(selected_surat)]

# --- 6. TABEL MONITORING UTAMA ---
if not df_table.empty:
    st.dataframe(
        df_table,
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("Data tidak ditemukan atau belum ada isi.")

# --- 7. EXPORT TO PDF ---
if not df_table.empty:
    st.divider()
    
    def generate_pdf(dataframe):
        pdf = FPDF(orientation='L', unit='mm', format='A4') # Landscape A4
        pdf.add_page()
        pdf.set_font("Helvetica", 'B', 12)
        pdf.cell(277, 8, text="Laporan Monitoring Surat & Endorsement Kapal", new_x="LMARGIN", new_y="NEXT", align='C')
        pdf.set_font("Helvetica", '', 9)
        pdf.cell(277, 5, text=f"Tanggal Cetak: {datetime.now().strftime('%d-%b-%Y')}", new_x="LMARGIN", new_y="NEXT", align='C')
        pdf.ln(4)

        # Header PDF
        pdf.set_font("Helvetica", 'B', 8)
        w = [45, 65, 30, 25, 45, 67]
        headers = ["Nama Kapal", "Jenis Surat", "Tgl Expired", "Sisa Hari", "Status", "Window Endorse (±3 Bln)"]
        for i, h in enumerate(headers):
            pdf.cell(w[i], 7, text=h, border=1, align='C')
        pdf.ln()

        # Isi PDF
        pdf.set_font("Helvetica", '', 7)
        for _, row in dataframe.iterrows():
            pdf.cell(w[0], 6, text=str(row['Nama Kapal'])[:25], border=1)
            pdf.cell(w[1], 6, text=str(row['Jenis Surat'])[:40], border=1)
            pdf.cell(w[2], 6, text=str(row['Tgl Expired']), border=1, align='C')
            pdf.cell(w[3], 6, text=str(row['Sisa Hari']), border=1, align='C')
            pdf.cell(w[4], 6, text=str(row['Status'])[:28], border=1)
            pdf.cell(w[5], 6, text=str(row['Window Endorse (±3 Bln)']), border=1, align='C')
            pdf.ln()

        return bytes(pdf.output())

    pdf_bytes = generate_pdf(df_table)
    st.download_button(
        label="📥 Download PDF Laporan",
        data=pdf_bytes,
        file_name=f"Laporan_Surat_Kapal_{datetime.now().strftime('%Y%m%d')}.pdf",
        mime="application/pdf"
    )
