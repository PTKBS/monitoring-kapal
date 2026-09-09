import streamlit as st
import pandas as pd
import gspread
from datetime import datetime, timedelta
from fpdf import FPDF

# --- 1. KONFIGURASI HALAMAN ---
st.set_page_config(
    page_title="Monitoring Surat Kapal & Endorsement",
    page_icon="🚢",
    layout="wide"
)

st.title("🚢 Dashboard Monitoring Surat Kapal & Endorsement")

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

# --- 3. BACA DATA SPREADSHEET ---
def load_data():
    raw_data = worksheet.get_all_values()
    if not raw_data:
        return pd.DataFrame()
    
    # Ambil baris 2 jika mengandung data header, atau baris 1 sebagai fallback
    if len(raw_data) >= 2 and any(raw_data[1]):
        headers = [str(h).strip() for h in raw_data[1]]
        data_rows = raw_data[2:] if len(raw_data) > 2 else []
    else:
        headers = [str(h).strip() for h in raw_data[0]]
        data_rows = raw_data[1:] if len(raw_data) > 1 else []
    
    # Buat DataFrame
    df = pd.DataFrame(data_rows)
    
    # Jika kolom melebihi header, sesuaikan
    if not df.empty:
        df = df.iloc[:, :len(headers)]
        df.columns = [h if h != "" else f"Kolom_{i+1}" for i, h in enumerate(headers)]
    
    return df

raw_df = load_data()

# --- 4. PROSES & HITUNG KOLOM MONITORING ---
if not raw_df.empty:
    df = raw_df.copy()
    
    # Cari nama kolom secara fleksibel berdasarkan urutan atau kata kunci
    col_kapal = next((c for c in df.columns if "kapal" in c.lower()), df.columns[0])
    col_surat = next((c for c in df.columns if "surat" in c.lower()), df.columns[1] if len(df.columns) > 1 else df.columns[0])
    col_terbit = next((c for c in df.columns if "terbit" in c.lower()), df.columns[2] if len(df.columns) > 2 else None)
    col_exp = next((c for c in df.columns if any(k in c.lower() for k in ["exp", "kadaluarsa", "berlaku"])), df.columns[3] if len(df.columns) > 3 else None)
    col_ket = next((c for c in df.columns if "ket" in c.lower() or "catatan" in c.lower()), df.columns[4] if len(df.columns) > 4 else None)

    # Konversi Tanggal Expired
    today = datetime.now()
    if col_exp and col_exp in df.columns:
        df['Exp_Datetime'] = pd.to_datetime(df[col_exp], errors='coerce', dayfirst=True)
    else:
        df['Exp_Datetime'] = pd.NaT

    # 1. Perhitungan Sisa Hari
    df['Sisa_Hari_Num'] = (df['Exp_Datetime'] - today).dt.days

    # 2. Perhitungan Status Expired / Aman
    def get_status_surat(days):
        if pd.isna(days):
            return "⚪ Tanpa Tanggal Exp"
        elif days < 0:
            return "🔴 EXPIRED"
        elif days <= 15:
            return "🚨 Sangat Kritis (<= 15 Hari)"
        elif days <= 30:
            return "🟡 Kritis (<= 30 Hari)"
        elif days <= 60:
            return "🔵 Perhatian (<= 60 Hari)"
        else:
            return "🟢 AMAN"

    df['Status Surat'] = df['Sisa_Hari_Num'].apply(get_status_surat)
    df['Sisa Hari'] = df['Sisa_Hari_Num'].apply(lambda x: f"{int(x)} Hari" if pd.notna(x) else "-")

    # 3. Hitung Estimasi Tgl Endorse (-3 Bulan / 90 Hari Sebelum Expired)
    df['Tgl Endorse (-3 Bln)'] = df['Exp_Datetime'].apply(
        lambda d: (d - timedelta(days=90)).strftime("%Y-%m-%d") if pd.notna(d) else "-"
    )

    # 4. Status Jendela Endorsement (3 Bulan Sebelum & Sesudah)
    def get_status_endorse(days):
        if pd.isna(days):
            return "-"
        elif days < 0:
            return "❌ Lewat Masa Endorse (Expired)"
        elif days <= 90:
            return "⚠️ Waktunya Endorse (<= 3 Bulan Exp)"
        else:
            return "✅ Belum Masa Endorse (> 3 Bulan)"

    df['Status Endorse'] = df['Sisa_Hari_Num'].apply(get_status_endorse)

    # --- 5. SUSUN URUTAN KOLOM SUPAYA RAPI MENURUN ---
    output_cols = []
    output_cols.append(col_kapal)
    output_cols.append(col_surat)
    if col_terbit and col_terbit in df.columns: output_cols.append(col_terbit)
    if col_exp and col_exp in df.columns: output_cols.append(col_exp)
    
    # Masukkan kolom perhitungan tambahan di tengah/samping
    output_cols.extend(['Sisa Hari', 'Status Surat', 'Tgl Endorse (-3 Bln)', 'Status Endorse'])
    
    if col_ket and col_ket in df.columns: output_cols.append(col_ket)
    
    # Ambil kolom tersisa jika ada
    remaining = [c for c in df.columns if c not in output_cols and c not in ['Exp_Datetime', 'Sisa_Hari_Num']]
    final_cols = output_cols + remaining
    
    df_display = df[final_cols]

else:
    df = pd.DataFrame()
    df_display = pd.DataFrame()
    col_kapal, col_surat = "Nama Kapal", "Nama Surat"

# --- 6. FILTER SIDEBAR (NAMA KAPAL & NAMA SURAT) ---
st.sidebar.header("🔍 Filter Tampilan Data")

if not df.empty and col_kapal in df.columns:
    list_kapal = sorted([k for k in df[col_kapal].dropna().unique().tolist() if str(k).strip() != ""])
    selected_kapal = st.sidebar.multiselect("Pilih Nama Kapal", options=list_kapal, default=list_kapal)
else:
    list_kapal, selected_kapal = [], []

if not df.empty and col_surat in df.columns:
    list_surat = sorted([s for s in df[col_surat].dropna().unique().tolist() if str(s).strip() != ""])
    selected_surat = st.sidebar.multiselect("Pilih Nama Surat", options=list_surat, default=list_surat)
else:
    list_surat, selected_surat = [], []

# Terapkan Filter
if not df_display.empty:
    if selected_kapal:
        df_display = df_display[df_display[col_kapal].isin(selected_kapal)]
    if selected_surat:
        df_display = df_display[df_display[col_surat].isin(selected_surat)]

# --- 7. FORM INPUT DATA BARU ---
st.subheader("📝 Input / Update Surat Kapal")
with st.expander("➕ Tambah Data Surat Kapal Baru ke Google Sheets"):
    with st.form(key="form_input_kapal", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            in_kapal = st.selectbox("Nama Kapal", options=list_kapal if list_kapal else ["Tugboat A", "Barge B"])
            in_surat = st.selectbox("Nama Surat", options=list_surat if list_surat else ["PAS Besar", "Sertifikat Keselamatan"])
        with c2:
            tgl_terbit = st.date_input("Tanggal Terbit")
            tgl_kadaluarsa = st.date_input("Tanggal Kadaluarsa / Expired")
            keterangan = st.text_input("Keterangan Catatan")

        submit_btn = st.form_submit_button("💾 Simpan Data ke Google Sheets")

    if submit_btn:
        try:
            new_row = [
                in_kapal,
                in_surat,
                tgl_terbit.strftime("%Y-%m-%d"),
                tgl_kadaluarsa.strftime("%Y-%m-%d"),
                keterangan
            ]
            worksheet.append_row(new_row)
            st.success(f"✅ Data {in_kapal} - {in_surat} berhasil disimpan!")
            st.cache_resource.clear()
            st.rerun()
        except Exception as err:
            st.error(f"❌ Gagal menyimpan data: {err}")

# --- 8. DASHBOARD METRICS ---
st.divider()
st.subheader("📊 Summary Status Surat & Endorsement")

if not df.empty and 'Status Surat' in df.columns:
    m1, m2, m3, m4, m5 = st.columns(5)
    
    cnt_expired = len(df_display[df_display['Status Surat'] == "🔴 EXPIRED"])
    cnt_15 = len(df_display[df_display['Status Surat'] == "🚨 Sangat Kritis (<= 15 Hari)"])
    cnt_30 = len(df_display[df_display['Status Surat'] == "🟡 Kritis (<= 30 Hari)"])
    cnt_endorse = len(df_display[df_display['Status Endorse'] == "⚠️ Waktunya Endorse (<= 3 Bulan Exp)"])
    cnt_aman = len(df_display[df_display['Status Surat'] == "🟢 AMAN"])

    m1.metric("🔴 Expired", f"{cnt_expired} Surat")
    m2.metric("🚨 <= 15 Hari", f"{cnt_15} Surat")
    m3.metric("🟡 <= 30 Hari", f"{cnt_30} Surat")
    m4.metric("⚠️ Perlu Endorse", f"{cnt_endorse} Surat")
    m5.metric("🟢 Aman", f"{cnt_aman} Surat")

# --- 9. TAMPILAN TABEL MONITORING ---
st.write("")
if not df_display.empty:
    st.dataframe(df_display, use_container_width=True)

    # --- 10. EXPORT & SAVE TO PDF ---
    st.divider()
    st.subheader("📄 Export Laporan ke PDF")

    def generate_pdf(data_to_pdf):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", 'B', 12)
        pdf.cell(190, 8, text="Laporan Monitoring Surat & Endorsement Kapal", new_x="LMARGIN", new_y="NEXT", align='C')
        pdf.set_font("Helvetica", '', 8)
        pdf.cell(190, 5, text=f"Tanggal Cetak: {datetime.now().strftime('%d-%m-%Y %H:%M')}", new_x="LMARGIN", new_y="NEXT", align='C')
        pdf.ln(4)

        # Header PDF
        pdf.set_font("Helvetica", 'B', 7)
        w = [30, 45, 20, 20, 45, 30]
        pdf.cell(w[0], 6, text="Nama Kapal", border=1, align='C')
        pdf.cell(w[1], 6, text="Nama Surat", border=1, align='C')
        pdf.cell(w[2], 6, text="Sisa Hari", border=1, align='C')
        pdf.cell(w[3], 6, text="Est. Endorse", border=1, align='C')
        pdf.cell(w[4], 6, text="Status Surat", border=1, align='C')
        pdf.cell(w[5], 6, text="Status Endorse", border=1, align='C')
        pdf.ln()

        # Isi PDF
        pdf.set_font("Helvetica", '', 6)
        for _, row in data_to_pdf.iterrows():
            pdf.cell(w[0], 5, text=str(row.get(col_kapal, ''))[:18], border=1)
            pdf.cell(w[1], 5, text=str(row.get(col_surat, ''))[:28], border=1)
            pdf.cell(w[2], 5, text=str(row.get("Sisa Hari", '-')), border=1, align='C')
            pdf.cell(w[3], 5, text=str(row.get("Tgl Endorse (-3 Bln)", '-')), border=1, align='C')
            
            st_clean = str(row.get("Status Surat", '-')).encode('ascii', 'ignore').decode('ascii').strip()
            end_clean = str(row.get("Status Endorse", '-')).encode('ascii', 'ignore').decode('ascii').strip()
            
            pdf.cell(w[4], 5, text=st_clean[:28], border=1)
            pdf.cell(w[5], 5, text=end_clean[:20], border=1)
            pdf.ln()

        return bytes(pdf.output())

    pdf_bytes = generate_pdf(df_display)
    st.download_button(
        label="📥 Download Laporan (Save to PDF)",
        data=pdf_bytes,
        file_name=f"Laporan_Surat_Kapal_{datetime.now().strftime('%Y%m%d')}.pdf",
        mime="application/pdf"
    )
else:
    st.info("Belum ada data atau tidak ada data yang cocok dengan filter.")
