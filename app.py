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

st.title("🚢 Dashboard & Laporan Monitoring Surat Kapal")

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

# --- 3. BACA & TRANSFORMASI DATA MATRIKS ---
def load_raw_matrix():
    return worksheet.get_all_values()

def load_and_transform_matrix_data(raw_data):
    if not raw_data or len(raw_data) < 3:
        return pd.DataFrame(), [], []
    
    header_row = raw_data[1] 
    kapal_list = [str(h).strip() for h in header_row[1:] if str(h).strip() != ""]
    
    rows_data = raw_data[2:]
    surat_list = []
    
    transformed_records = []
    today = datetime.now()

    for r in rows_data:
        if not r or len(r) == 0:
            continue
            
        jenis_surat = str(r[0]).strip()
        if not jenis_surat:
            continue
            
        surat_list.append(jenis_surat)
            
        for col_idx, kapal_name in enumerate(header_row[1:], start=1):
            kapal_name = str(kapal_name).strip()
            if not kapal_name:
                continue
                
            tgl_str = str(r[col_idx]).strip() if col_idx < len(r) else ""
            
            if tgl_str != "":
                exp_dt = pd.to_datetime(tgl_str, errors='coerce', dayfirst=True)
                
                if pd.notna(exp_dt):
                    sisa_hari_num = (exp_dt - today).days
                    tgl_exp_fmt = exp_dt.strftime("%d-%b-%Y")
                    sisa_hari_fmt = f"{sisa_hari_num} h"
                    
                    # Status
                    if sisa_hari_num < 0:
                        status_str = "EXPIRED"
                        cat_status = "EXPIRED"
                    elif sisa_hari_num <= 14:
                        status_str = f"SANGAT DESAK (<={sisa_hari_num} Hari)"
                        cat_status = "DESAK"
                    elif sisa_hari_num <= 30:
                        status_str = "KRITIS (<=30 Hari)"
                        cat_status = "KRITIS"
                    else:
                        status_str = "AMAN"
                        cat_status = "AMAN"
                        
                    # Window Endorse
                    jenis_upper = jenis_surat.upper()
                    if "SIUPAL" in jenis_upper and "ENDORSE" in jenis_upper:
                        # Khusus SIUPAL ENDORSE
                        window_endorse = exp_dt.strftime('%d %b %Y')
                    elif "ENDORSE" in jenis_upper:
                        # Endorse selain SIUPAL (±3 bulan / 90 hari)
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
                        "Cat_Status": cat_status,
                        "Sisa_Hari_Num": sisa_hari_num
                    })

    df_result = pd.DataFrame(transformed_records)
    
    if not df_result.empty:
        df_result = df_result.sort_values(by="Sisa_Hari_Num", ascending=True)
        
    return df_result, sorted(list(set(kapal_list))), sorted(list(set(surat_list)))

raw_data = load_raw_matrix()
df_table, list_kapal_all, list_surat_all = load_and_transform_matrix_data(raw_data)

# Inisialisasi filtered_df dari awal
filtered_df = df_table.copy() if not df_table.empty else pd.DataFrame()

# --- 4. RINGKASAN METRIK / BADGE SUMMARY ---
if not df_table.empty:
    cnt_expired = len(df_table[df_table['Cat_Status'] == "EXPIRED"])
    cnt_desak = len(df_table[df_table['Cat_Status'] == "DESAK"])
    cnt_kritis = len(df_table[df_table['Cat_Status'] == "KRITIS"])
    cnt_aman = len(df_table[df_table['Cat_Status'] == "AMAN"])

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(label="🔴 EXPIRED", value=f"{cnt_expired} Surat")
    with col2:
        st.metric(label="🟠 SANGAT DESAK (≤14 Hr)", value=f"{cnt_desak} Surat")
    with col3:
        st.metric(label="🟡 KRITIS (≤30 Hr)", value=f"{cnt_kritis} Surat")
    with col4:
        st.metric(label="🟢 AMAN (>30 Hr)", value=f"{cnt_aman} Surat")

    st.divider()

# --- 5. SIDEBAR: FILTER & FORM UPDATE ---
st.sidebar.header("🔍 Filter Data")

if not df_table.empty:
    selected_kapal = st.sidebar.multiselect("Filter Kapal", options=list_kapal_all, default=list_kapal_all)
    selected_surat = st.sidebar.multiselect("Filter Jenis Surat", options=list_surat_all, default=list_surat_all)
    
    if selected_kapal:
        filtered_df = filtered_df[filtered_df['Nama Kapal'].isin(selected_kapal)]
    if selected_surat:
        filtered_df = filtered_df[filtered_df['Jenis Surat'].isin(selected_surat)]

# FORM UPDATE TANGGAL DI SIDEBAR
st.sidebar.divider()
st.sidebar.header("📝 Update Tanggal Surat")
with st.sidebar.form("form_update_tanggal", clear_on_submit=True):
    input_kapal = st.selectbox("Pilih Kapal", options=["-- Pilih Kapal --"] + list_kapal_all)
    input_surat = st.selectbox("Pilih Jenis Surat", options=["-- Pilih Surat --"] + list_surat_all)
    
    # Format Tanggal Indonesia (DD/MM/YYYY)
    input_tgl = st.date_input(
        "Tanggal Expired Baru", 
        value=datetime.now(), 
        format="DD/MM/YYYY"
    )
    btn_submit = st.form_submit_button("💾 Simpan Tanggal Ke Google Sheets")

if btn_submit:
    if input_kapal == "-- Pilih Kapal --" or input_surat == "-- Pilih Surat --":
        st.sidebar.error("⚠️ Silakan pilih Kapal dan Jenis Surat yang valid!")
    else:
        try:
            header_row = raw_data[1]
            
            col_target = None
            for idx, k in enumerate(header_row):
                if str(k).strip() == input_kapal:
                    col_target = idx + 1
                    break
            
            row_target = None
            for idx, r in enumerate(raw_data):
                if len(r) > 0 and str(r[0]).strip() == input_surat:
                    row_target = idx + 1
                    break
            
            if row_target and col_target:
                tgl_formatted = input_tgl.strftime("%d-%m-%Y")
                worksheet.update_cell(row_target, col_target, tgl_formatted)
                st.sidebar.success(f"✅ Tanggal {input_surat} ({input_kapal}) berhasil diupdate ke {tgl_formatted}!")
                st.cache_resource.clear()
                st.rerun()
            else:
                st.sidebar.error("❌ Nama Kapal atau Surat tidak ditemukan pada tabel Google Sheets!")
        except Exception as e:
            st.sidebar.error(f"⚠️ Gagal memperbarui Google Sheets: {e}")

# --- 6. TAMPILAN TABEL + HIGHLIGHT WARNA ---
st.subheader("📋 Daftar Status Surat Kapal")

if not filtered_df.empty:
    show_df = filtered_df[["Nama Kapal", "Jenis Surat", "Tgl Expired", "Sisa Hari", "Status", "Window Endorse (±3 Bln)", "Cat_Status"]].copy()

    def highlight_rows(row):
        cat = row['Cat_Status']
        if cat == 'EXPIRED':
            return ['background-color: #ffcccc; color: #8b0000; font-weight: bold;'] * len(row)
        elif cat == 'DESAK':
            return ['background-color: #ffe6cc; color: #b35900; font-weight: bold;'] * len(row)
        elif cat == 'KRITIS':
            return ['background-color: #ffffcc; color: #808000;'] * len(row)
        else:
            return [''] * len(row)

    styled_df = show_df.style.apply(highlight_rows, axis=1)

    st.dataframe(
        styled_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Cat_Status": None
        }
    )
else:
    st.warning("⚠️ Tidak ada data ditemukan.")

# --- 7. EXPORT TO PDF ---
if not filtered_df.empty:
    st.divider()
    
    def generate_pdf(dataframe):
        # 💡 Urutkan per NAMA KAPAL (A-Z), lalu di dalam kapal tersebut diurutkan dari SISA HARI TERKECIL (Expired paling atas)
        pdf_df = dataframe.sort_values(by=["Nama Kapal", "Sisa_Hari_Num"], ascending=[True, True])

        pdf = FPDF(orientation='L', unit='mm', format='A4')
        pdf.add_page()
        
        # Judul Laporan
        pdf.set_font("Helvetica", 'B', 12)
        pdf.cell(277, 8, text="Laporan Monitoring Surat & Endorsement Kapal", new_x="LMARGIN", new_y="NEXT", align='C')
        pdf.set_font("Helvetica", '', 9)
        pdf.cell(277, 5, text=f"Tanggal Cetak: {datetime.now().strftime('%d-%b-%Y')}", new_x="LMARGIN", new_y="NEXT", align='C')
        pdf.ln(4)

        # Header Tabel
        pdf.set_font("Helvetica", 'B', 8)
        pdf.set_fill_color(230, 230, 230) # Warna latar header (abu-abu)
        w = [45, 65, 30, 25, 45, 67]
        headers = ["Nama Kapal", "Jenis Surat", "Tgl Expired", "Sisa Hari", "Status", "Window Endorse (±3 Bln)"]
        
        for i, h in enumerate(headers):
            pdf.cell(w[i], 7, text=h, border=1, align='C', fill=True)
        pdf.ln()

        # Isi Tabel Berwarna & Terurut
        pdf.set_font("Helvetica", '', 7)
        for _, row in pdf_df.iterrows():
            cat = row['Cat_Status']
            
            # Pewarnaan latar berdasarkan status (RGB)
            if cat == 'EXPIRED':
                pdf.set_fill_color(255, 204, 204) # Merah Muda
                fill = True
            elif cat == 'DESAK':
                pdf.set_fill_color(255, 230, 204) # Oranye Muda
                fill = True
            elif cat == 'KRITIS':
                pdf.set_fill_color(255, 255, 204) # Kuning Muda
                fill = True
            else:
                fill = False # Putih / Tanpa Latar

            pdf.cell(w[0], 6, text=str(row['Nama Kapal'])[:25], border=1, fill=fill)
            pdf.cell(w[1], 6, text=str(row['Jenis Surat'])[:40], border=1, fill=fill)
            pdf.cell(w[2], 6, text=str(row['Tgl Expired']), border=1, align='C', fill=fill)
            pdf.cell(w[3], 6, text=str(row['Sisa Hari']), border=1, align='C', fill=fill)
            pdf.cell(w[4], 6, text=str(row['Status'])[:28], border=1, fill=fill)
            pdf.cell(w[5], 6, text=str(row['Window Endorse (±3 Bln)']), border=1, align='C', fill=fill)
            pdf.ln()

        return bytes(pdf.output())

    pdf_bytes = generate_pdf(filtered_df)
    st.download_button(
        label="📥 Download PDF Laporan Berwarna",
        data=pdf_bytes,
        file_name=f"Laporan_Surat_Kapal_{datetime.now().strftime('%Y%m%d')}.pdf",
        mime="application/pdf"
    )
