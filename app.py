import streamlit as st
import pandas as pd
import gspread
from datetime import datetime
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

# --- 3. BACA DATA (MENDUKUNG HEADER BARIS 2 / BARIS 1) ---
def load_data():
    raw_data = worksheet.get_all_values()
    if not raw_data:
        return pd.DataFrame()
    
    # Deteksi apakah baris 2 adalah header kapal
    if len(raw_data) >= 2 and any("kapal" in str(cell).lower() for cell in raw_data[1]):
        headers = [str(h).strip() for h in raw_data[1]]
        data_rows = raw_data[2:] if len(raw_data) > 2 else []
    else:
        headers = [str(h).strip() for h in raw_data[0]]
        data_rows = raw_data[1:] if len(raw_data) > 1 else []
    
    # Beri nama unik jika ada header kosong
    headers = [h if h != "" else f"Kolom_{i+1}" for i, h in enumerate(headers)]
    
    df = pd.DataFrame(data_rows, columns=headers)
    return df

df = load_data()

# --- 4. IDENTIFIKASI KOLOM KUNCI ---
col_kapal = next((c for c in df.columns if "kapal" in c.lower()), df.columns[0] if not df.empty else "Nama Kapal")
col_surat = next((c for c in df.columns if "surat" in c.lower()), df.columns[1] if len(df.columns) > 1 else "Nama Surat")
col_exp = next((c for c in df.columns if any(k in c.lower() for k in ["exp", "kadaluarsa", "berlaku", "tanggal", "tgl"])), None)

# --- 5. LOGIKA PERHITUNGAN EXPIRED, ENDORSEMENT, & SISA HARI ---
today = datetime.now()

if not df.empty and col_exp and col_exp in df.columns:
    df['Exp_Date'] = pd.to_datetime(df[col_exp], errors='coerce')
    df['Sisa_Hari_Num'] = (df['Exp_Date'] - today).dt.days
    
    def calculate_status(days):
        if pd.isna(days):
            return "⚪ Tanpa Tanggal"
        elif days < 0:
            return "🔴 EXPIRED"
        elif days <= 15:
            return "🚨 Sangat Kritis (<= 15 Hari)"
        elif days <= 30:
            return "🟡 Kritis (<= 30 Hari)"
        elif days <= 90:
            return "🔵 Perlu Endorse (Masa Endorse <= 3 Bulan)"
        else:
            return "🟢 Aman (> 3 Bulan / Sesudah Endorse)"

    df['Status Surat'] = df['Sisa_Hari_Num'].apply(calculate_status)
    df['Sisa Hari'] = df['Sisa_Hari_Num'].apply(lambda x: f"{int(x)} Hari" if pd.notna(x) else "-")
else:
    df['Status Surat'] = "⚪ Tanpa Tanggal"
    df['Sisa Hari'] = "-"
    df['Sisa_Hari_Num'] = None

# --- 6. DYNAMIC DROPDOWN FILTER (UNTUK FILTER TAMPILAN) ---
st.sidebar.header("🔍 Filter Tampilan Data")

if not df.empty and col_kapal in df.columns:
    unique_kapal = sorted([k for k in df[col_kapal].dropna().unique().tolist() if str(k).strip() != ""])
    filter_kapal = st.sidebar.multiselect("Pilih Nama Kapal", options=unique_kapal, default=unique_kapal)
else:
    filter_kapal = []

if not df.empty and col_surat in df.columns:
    unique_surat = sorted([s for s in df[col_surat].dropna().unique().tolist() if str(s).strip() != ""])
    filter_surat = st.sidebar.multiselect("Pilih Nama Surat", options=unique_surat, default=unique_surat)
else:
    filter_surat = []

# Tapis Data Berdasarkan Filter Sidebar
filtered_df = df.copy()
if filter_kapal:
    filtered_df = filtered_df[filtered_df[col_kapal].isin(filter_kapal)]
if filter_surat:
    filtered_df = filtered_df[filtered_df[col_surat].isin(filter_surat)]

# --- 7. FORM INPUT & UPDATE DATA ---
st.subheader("📝 Input / Update Data Surat Kapal")
with st.expander("Klik di sini untuk Tambah Data Baru ke Google Sheets"):
    with st.form(key="form_input_kapal", clear_on_submit=True):
        c_in1, c_in2 = st.columns(2)
        with c_in1:
            input_kapal = st.selectbox("Nama Kapal", options=unique_kapal if unique_kapal else ["Tugboat A", "Barge B"])
            input_surat = st.selectbox("Nama Surat", options=unique_surat if unique_surat else ["PAS Besar", "Sertifikat Keselamatan"])
        with c_in2:
            tgl_terbit = st.date_input("Tanggal Terbit")
            tgl_kadaluarsa = st.date_input("Tanggal Kadaluarsa / Expired")
            keterangan = st.text_input("Keterangan Catatan")

        submit_btn = st.form_submit_button("💾 Simpan Data ke Google Sheets")

    if submit_btn:
        try:
            new_row = [
                input_kapal,
                input_surat,
                tgl_terbit.strftime("%Y-%m-%d"),
                tgl_kadaluarsa.strftime("%Y-%m-%d"),
                keterangan
            ]
            worksheet.append_row(new_row)
            st.success(f"✅ Data {input_kapal} - {input_surat} berhasil disimpan!")
            st.cache_resource.clear()
            st.rerun()
        except Exception as err:
            st.error(f"❌ Gagal menyimpan data: {err}")

# --- 8. DASHBOARD METRICS & RINGKASAN ---
st.divider()
st.subheader("📊 Ringkasan Status Surat Kapal")

if not filtered_df.empty:
    m1, m2, m3, m4, m5 = st.columns(5)
    
    cnt_expired = len(filtered_df[filtered_df['Status Surat'] == "🔴 EXPIRED"])
    cnt_15 = len(filtered_df[filtered_df['Status Surat'] == "🚨 Sangat Kritis (<= 15 Hari)"])
    cnt_30 = len(filtered_df[filtered_df['Status Surat'] == "🟡 Kritis (<= 30 Hari)"])
    cnt_endorse = len(filtered_df[filtered_df['Status Surat'] == "🔵 Perlu Endorse (Masa Endorse <= 3 Bulan)"])
    cnt_safe = len(filtered_df[filtered_df['Status Surat'] == "🟢 Aman (> 3 Bulan / Sesudah Endorse)"])
    
    m1.metric("🔴 Expired", f"{cnt_expired}")
    m2.metric("🚨 <= 15 Hari", f"{cnt_15}")
    m3.metric("🟡 <= 30 Hari", f"{cnt_30}")
    m4.metric("🔵 Perlu Endorse", f"{cnt_endorse}")
    m5.metric("🟢 Aman", f"{cnt_safe}")

    st.write("")
    # Drop kolom bantu datetime sebelum ditampilkan di UI
    display_df = filtered_df.drop(columns=['Exp_Date', 'Sisa_Hari_Num'], errors='ignore')
    st.dataframe(display_df, use_container_width=True)

    # --- 9. EXPORT & SAVE TO PDF ---
    st.divider()
    st.subheader("📄 Export Laporan PDF (Sesuai Filter)")

    def generate_pdf(data_to_pdf):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", 'B', 14)
        pdf.cell(190, 10, text="Laporan Monitoring Surat & Endorsement Kapal", new_x="LMARGIN", new_y="NEXT", align='C')
        pdf.set_font("Helvetica", '', 9)
        pdf.cell(190, 6, text=f"Tanggal Dicetak: {datetime.now().strftime('%d-%m-%Y %H:%M')}", new_x="LMARGIN", new_y="NEXT", align='C')
        pdf.ln(4)

        # Header Tabel PDF
        pdf.set_font("Helvetica", 'B', 8)
        w = [40, 55, 25, 70]
        headers_pdf = [col_kapal, col_surat, "Sisa Hari", "Status Surat"]
        for i, h in enumerate(headers_pdf):
            pdf.cell(w[i], 7, text=str(h), border=1, align='C')
        pdf.ln()

        # Isi Tabel PDF
        pdf.set_font("Helvetica", '', 7)
        for _, row in data_to_pdf.iterrows():
            pdf.cell(w[0], 6, text=str(row.get(col_kapal, ''))[:20], border=1)
            pdf.cell(w[1], 6, text=str(row.get(col_surat, ''))[:30], border=1)
            pdf.cell(w[2], 6, text=str(row.get("Sisa Hari", '-')), border=1, align='C')
            
            # Bersihkan emoji dari status agar PDF tidak corrupt/error
            status_clean = str(row.get("Status Surat", '-')).encode('ascii', 'ignore').decode('ascii').strip()
            pdf.cell(w[3], 6, text=status_clean, border=1)
            pdf.ln()

        return bytes(pdf.output())

    pdf_bytes = generate_pdf(filtered_df)
    st.download_button(
        label="📥 Download Laporan (Save to PDF)",
        data=pdf_bytes,
        file_name=f"Laporan_Surat_Kapal_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
        mime="application/pdf"
    )
else:
    st.info("Tidak ada data yang sesuai dengan filter yang dipilih.")
