import datetime
import io
import time
from fpdf import FPDF
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Monitoring Surat Kapal", page_icon="🚢", layout="wide"
)

st.title("🚢 Dashboard Monitoring Masa Berlaku Surat Kapal")
st.caption("Aplikasi pemantauan otomatis via Google Sheets (Real-time Live)")

# Spreadsheet ID
SPREADSHEET_ID = "1ovR8ZxhQmLYv73iSu1xWEXsG1ipL448fmIhs4zJ8P6o"


def load_data():
    timestamp = int(time.time())

    # 1. Baca Sheet Utama (Data Tanggal Surat)
    sheet_csv_url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&t={timestamp}"
    df_raw = pd.read_csv(sheet_csv_url, header=None, dtype=str)

    header_idx = 1
    raw_headers = df_raw.iloc[header_idx].tolist()
    df_data = df_raw.iloc[header_idx + 1 :].copy()

    clean_headers = []
    last_kapal = "Kapal Unknown"

    for i, h in enumerate(raw_headers):
        h_str = str(h).strip() if pd.notnull(h) else ""
        if "tanggal berakhir" in h_str.lower() or i == 0:
            if i == 0:
                clean_headers.append("Jenis Surat")
            else:
                clean_headers.append(f"{last_kapal} (Col {i})")
        elif h_str != "" and h_str.lower() != "nan":
            last_kapal = h_str
            clean_headers.append(h_str)
        else:
            clean_headers.append(f"{last_kapal} (Col {i})")

    df_data.columns = clean_headers

    df_data = df_data.dropna(subset=["Jenis Surat"])
    df_data["Jenis Surat"] = df_data["Jenis Surat"].astype(str).str.strip()
    df_data = df_data[
        ~df_data["Jenis Surat"].isin(["", "nan", "NaN", "JENIS SURAT", "None"])
    ]

    kolom_kapal = [c for c in clean_headers if c != "Jenis Surat"]

    # Unpivot / Transpose
    df_melted = pd.melt(
        df_data,
        id_vars=["Jenis Surat"],
        value_vars=kolom_kapal,
        var_name="Nama Kapal",
        value_name="Tgl_Raw",
    )

    df_melted["Nama Kapal"] = (
        df_melted["Nama Kapal"]
        .astype(str)
        .str.replace(r"\s\(Col\s\d+\)$", "", regex=True)
    )

    df_melted = df_melted[
        df_melted["Tgl_Raw"].notnull()
        & ~df_melted["Tgl_Raw"]
        .astype(str)
        .str.strip()
        .isin(["", "-", "None", "nan", "NaN", "0"])
    ].copy()

    # Parsing Tanggal (Day-First)
    def parse_flexible_date(val):
        val_str = str(val).strip()
        if not val_str or val_str in ["-", "nan", "NaN", "0"]:
            return None, None

        parsed = pd.to_datetime(val_str, errors="coerce", dayfirst=True)

        if pd.notnull(parsed) and parsed.year > 1980:
            dt = parsed.date()
            today = datetime.date.today()
            sisa = (dt - today).days
            return dt.strftime("%d-%b-%Y"), sisa

        return "FORMAT SALAH", 99999

    parsed_results = df_melted["Tgl_Raw"].apply(parse_flexible_date)

    df_melted["Tgl Expired"] = [r[0] for r in parsed_results]
    df_melted["Sisa Hari"] = [r[1] for r in parsed_results]

    df_melted = df_melted[df_melted["Tgl Expired"].notnull()].copy()

    def get_status(row):
        tgl_str = row["Tgl Expired"]
        sisa = row["Sisa Hari"]

        if tgl_str == "FORMAT SALAH":
            return "FORMAT TANGGAL SALAH"

        sisa = int(sisa)
        if sisa <= 0:
            return "EXPIRED"
        elif sisa <= 14:
            return "SANGAT DESAK (<=14 Hari)"
        elif sisa <= 30:
            return "PERINGATAN (<=30 Hari)"
        else:
            return "AMAN"

    df_melted["Status"] = df_melted.apply(get_status, axis=1)

    # 2. Baca Sheet2 (Link_Folder)
    dict_folder = {}
    try:
        folder_csv_url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq?tqx=out:csv&sheet=Link_Folder&t={timestamp}"
        df_folder = pd.read_csv(folder_csv_url, dtype=str)
        if (
            "Nama Kapal" in df_folder.columns
            and "Link Folder Google Drive" in df_folder.columns
        ):
            for _, r in df_folder.iterrows():
                k_nama = str(r["Nama Kapal"]).strip()
                k_link = str(r["Link Folder Google Drive"]).strip()
                if k_nama and k_link and k_link.lower() != "nan":
                    dict_folder[k_nama] = k_link
    except:
        pass

    df_melted["Link Folder"] = df_melted["Nama Kapal"].map(
        lambda x: dict_folder.get(str(x).strip(), "")
    )

    return df_melted[
        [
            "Nama Kapal",
            "Jenis Surat",
            "Tgl Expired",
            "Sisa Hari",
            "Status",
            "Link Folder",
        ]
    ]


# Class generator PDF
class PDFReport(FPDF):

    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(
            0, 8, "LAPORAN MONITORING MASA BERLAKU SURAT KAPAL", ln=True, align="C"
        )
        self.set_font("Helvetica", "", 10)
        self.cell(
            0,
            6,
            f"Tanggal Cetak: {datetime.date.today().strftime('%d-%b-%Y')}",
            ln=True,
            align="C",
        )
        self.ln(5)

        self.set_font("Helvetica", "B", 10)
        self.set_fill_color(220, 220, 220)
        self.cell(65, 8, " Nama Kapal", border=1, fill=True)
        self.cell(85, 8, " Jenis Surat", border=1, fill=True)
        self.cell(35, 8, " Tgl Expired", border=1, fill=True, align="C")
        self.cell(30, 8, " Sisa Hari", border=1, fill=True, align="C")
        self.cell(62, 8, " Status", border=1, fill=True, align="C")
        self.ln()

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Halaman {self.page_no()}/{{nb}}", align="C")


def convert_df_to_pdf(df_data):
    pdf = PDFReport(orientation="L", unit="mm", format="A4")
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_font("Helvetica", "", 9)

    for _, row in df_data.iterrows():
        status = str(row["Status"])

        if "EXPIRED" in status:
            pdf.set_fill_color(255, 204, 204)
        elif "DESAK" in status:
            pdf.set_fill_color(255, 230, 204)
        elif "PERINGATAN" in status:
            pdf.set_fill_color(255, 255, 204)
        else:
            pdf.set_fill_color(255, 255, 255)

        pdf.cell(
            65,
            7,
            f" {str(row['Nama Kapal'])[:35]}",
            border=1,
            fill=True,
        )
        pdf.cell(
            85,
            7,
            f" {str(row['Jenis Surat'])[:48]}",
            border=1,
            fill=True,
        )
        pdf.cell(
            35,
            7,
            str(row["Tgl Expired"]),
            border=1,
            align="C",
            fill=True,
        )
        pdf.cell(
            30,
            7,
            f"{row['Sisa Hari']} hari",
            border=1,
            align="C",
            fill=True,
        )
        pdf.cell(62, 7, f" {status}", border=1, fill=True)
        pdf.ln()

    return bytes(pdf.output())


try:
    df = load_data()

    total_expired = len(
        df[df["Status"].str.contains("EXPIRED", case=False, na=False)]
    )
    total_desak = len(
        df[df["Status"].str.contains("SANGAT DESAK", case=False, na=False)]
    )
    total_warning = len(
        df[df["Status"].str.contains("PERINGATAN", case=False, na=False)]
    )
    total_aman = len(
        df[df["Status"].str.contains("AMAN", case=False, na=False)]
    )
    total_error = len(
        df[
            df["Status"].str.contains(
                "FORMAT TANGGAL SALAH", case=False, na=False
            )
        ]
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🔴 Expired", f"{total_expired} Surat")
    col2.metric("🚨 Sangat Desak (H-14)", f"{total_desak} Surat")
    col3.metric("🟡 Peringatan (H-30)", f"{total_warning} Surat")
    col4.metric("🟢 Aman", f"{total_aman} Surat")

    if total_error > 0:
        st.warning(
            f"⚠️ Ada {total_error} surat yang format tanggalnya di Google Sheets tidak terbaca/salah ketik. Cek tabel di bawah!"
        )

    st.markdown("---")

    st.sidebar.header("🔍 Filter Data")
    status_options = list(df["Status"].unique())
    selected_status = st.sidebar.multiselect(
        "Pilih Status:", options=status_options, default=status_options
    )

    kapal_options = list(df["Nama Kapal"].unique())
    selected_kapal = st.sidebar.multiselect(
        "Filter Nama Kapal:", options=kapal_options, default=kapal_options
    )

    surat_options = list(df["Jenis Surat"].unique())
    selected_surat = st.sidebar.multiselect(
        "Filter Jenis Surat:", options=surat_options, default=surat_options
    )

    df_filtered = df[
        (df["Status"].isin(selected_status))
        & (df["Nama Kapal"].isin(selected_kapal))
        & (df["Jenis Surat"].isin(selected_surat))
    ]

    if "Sisa Hari" in df_filtered.columns:
        df_filtered = df_filtered.sort_values(
            by="Sisa Hari", ascending=True, na_position="last"
        )

    col_title, col_download = st.columns([3, 1])

    with col_title:
        st.subheader("📋 Daftar Detail Surat Kapal")

    with col_download:
        pdf_bytes = convert_df_to_pdf(df_filtered)
        st.download_button(
            label="📄 Download PDF Laporan",
            data=pdf_bytes,
            file_name=f"Laporan_Surat_Kapal_{datetime.date.today().strftime('%d_%b_%Y')}.pdf",
            mime="application/pdf",
        )

    # UI Display
    df_display = df_filtered.copy()
    status_emoji_map = {
        "EXPIRED": "🔴 EXPIRED",
        "SANGAT DESAK (<=14 Hari)": "🔴 SANGAT DESAK (<=14 Hari)",
        "PERINGATAN (<=30 Hari)": "🟡 PERINGATAN (<=30 Hari)",
        "AMAN": "🟢 AMAN",
        "FORMAT TANGGAL SALAH": "⚠️ FORMAT TANGGAL SALAH",
    }
    df_display["Status"] = df_display["Status"].map(
        lambda x: status_emoji_map.get(x, x)
    )

    # Tampilkan Tabel Utama (tanpa kolom link folder biar tetap bersih)
    st.dataframe(
        df_display[
            ["Nama Kapal", "Jenis Surat", "Tgl Expired", "Sisa Hari", "Status"]
        ],
        use_container_width=True,
        hide_index=True,
    )

    # FITUR DIRECT SOFTCOPY SERTIFIKAT VIA LINK FOLDER KAPAL
    st.markdown("---")
    st.subheader("📂 Direct Softcopy Sertifikat PDF")

    # Filter pilihan kapal khusus softcopy
    daftar_kapal_tersedia = list(df_display["Nama Kapal"].unique())
    pilihan_kapal = st.selectbox(
        "Pilih Nama Kapal untuk Membuka Folder Softcopy Sertifikat:",
        options=["-- Pilih Kapal --"] + daftar_kapal_tersedia,
    )

    if pilihan_kapal != "-- Pilih Kapal --":
        # Ambil link folder dari data
        row_kapal = df_display[df_display["Nama Kapal"] == pilihan_kapal].iloc[0]
        link_folder_kapal = row_kapal["Link Folder"]

        st.info(f"🚢 **Kapal Terpilih:** {pilihan_kapal}")

        if (
            pd.notnull(link_folder_kapal)
            and str(link_folder_kapal).strip().startswith("http")
        ):
            st.link_button(
                label=f"📂 Buka Folder Sertifikat PDF ({pilihan_kapal})",
                url=str(link_folder_kapal).strip(),
                use_container_width=True,
            )
        else:
            st.warning(
                f"⚠️ Link folder Google Drive untuk **{pilihan_kapal}** belum dimasukkan di tab sheet 'Link_Folder' pada Google Sheets."
            )

except Exception as e:
    st.error(f"Gagal membaca data dari Google Sheets.\n\nDetail Error: {e}")
