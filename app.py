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

# --- 3. PEMBACAAN DAN TRANSFORMASI DATA MATRIKS ---
def load_and_transform_matrix_data():
    raw_data = worksheet.get_all_values()
    if not raw_data or len(raw_data) < 3:
        return pd.DataFrame()
    
    # Baris 2 (indeks 1) berisi Nama-nama Kapal (Kolom B, C, D, dst.)
    header_row = raw_data[1] 
    
    # Ambil daftar kapal mulai dari Kolom B (indeks 1 ke atas)
    kapal_list = [str(h).strip() for h in header_row[1:]]
    
    # Data surat dimulai dari Baris 3 (indeks 2 ke bawah)
    rows_data = raw_data[2:]
    
    transformed_records = []
    today = datetime.now()

    for r in rows_data:
        if not r or len(r) == 0:
            continue
            
        jenis_surat = str(r[0]).strip()
        if not jenis_surat: # Abaikan baris kosong
            continue
            
        # Periksa tiap kolom kapal untuk jenis surat ini
        for col_idx, kapal_name in enumerate(kapal_list, start=1):
            if not kapal_name: # Jika nama kapal di header kosong, lewati
                continue
                
            tgl_str = str(r[col_idx]).strip() if col_idx < len(r) else ""
            
            # Jika ada tanggal expired di sel tersebut
            if tgl_str != "":
                # Coba parse berbagai format tanggal (e.g. 4-3-2027, 04/03/2027, 2027-03-04)
                exp_dt = pd.to_datetime(tgl_str, errors='coerce', dayfirst=True)
                
                if pd.notna(exp_dt):
                    sisa_hari_num = (exp_dt - today).days
                    
                    # Format Tanggal Expired
                    tgl_exp_fmt = exp_dt.strftime("%d-%b-%Y")
                    
                    # Format Sisa Hari
                    sisa_hari_fmt = f"{sisa_hari_num} h"
                    
                    # Format Status
                    if sisa_hari_num < 0:
                        status_str = "EXPIRED"
                    elif sisa_hari_num <= 14:
                        status_str = f"SANGAT DESAK (<={sisa_hari_num} Hari)"
                    elif sisa_hari_num <= 30:
                        status_str = "KRITIS (<=30 Hari)"
                    else:
                        status_str = "AMAN"
                        
                    # Format Window Endorse (±3 Bln) khusus surat dengan kata ENDORSE
                    if "ENDORSE" in jenis_surat.upper():
                        start_w = exp_dt - timedelta(days=90)
                        end_w = exp_dt + timedelta(days=90)
                        window_endorse = f"{start_w.strftime('%d %b %Y')} s/d {end_w.strftime('%d %b %Y')}"
                    else:
                        window_endorse = "-"
                        
                    transformed_records.append({
                        "Nama Kapal": kapal_name,
                        "Jenis Surat": jenis_surat,
                        "Tgl Expired": tgl_exp_fmt,
                        "Sisa Hari": sisa_hari_fmt,
                        "Status": status_str,
                        "Window Endorse (±3 Bln)": window_endorse,
                        "Sisa_Hari_Num": sisa_hari_num # Untuk sorting
                    })

    df_result = pd.DataFrame(transformed_records)
    
    # Sort berdasarkan sisa hari (yang paling mendesak/expired paling atas)
    if not df_result.empty:
        df_result = df_result.sort_values(by="Sisa_Hari_Num", ascending=True)
        df_result = df_result.drop(columns=["Sisa_Hari_Num"])
        
    return df_result

df_table = load_and_transform_matrix_data()

# --- 4. TAMPILAN KEPALA LAPORAN ---
st.caption(f"Tanggal Cetak: {datetime.now().strftime('%d-%b-%Y')}")

# --- 5. SIDEBAR FILTER ---
st.sidebar.header("🔍 Filter Data")
if not df_table.empty:
    list_kapal = sorted([k for k in df_table['Nama Kapal'].unique().tolist() if k])
    list_surat = sorted([s for s in df_table['Jenis Surat'].unique().tolist() if s])
    
    selected_kapal = st.sidebar.multiselect("Nama Kapal", options=list_kapal, default=list_kapal)
    selected_surat = st.sidebar.multiselect("Jenis Surat", options=list_surat, default=list_surat)
    
    if selected_kapal:
        df_table = df_table[df_table['Nama Kapal'].isin(selected_kapal)]
    if selected_surat:
        df_table = df_table[df_table['Jenis Surat'].isin(selected_surat)]

# --- 6. TABEL UTAMA ---
if not df_table.empty:
    st.dataframe(
        df_table,
        use_container_width=True,
        hide_index=True
    )
else:
    st.warning("⚠️ Tidak ada data ditemukan. Pastikan Google Sheets terisi dengan format tanggal yang benar.")

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

        # Header Tabel PDF
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
