import datetime
import time
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Monitoring Surat Kapal", page_icon="🚢", layout="wide"
)

st.title("🚢 Dashboard Monitoring Masa Berlaku Surat Kapal")
st.caption("Aplikasi pemantauan otomatis via Google Sheets (Real-time Live)")


def load_data():
    timestamp = int(time.time())
    sheet_csv_url = f"https://docs.google.com/spreadsheets/d/1ovR8ZxhQmLYv73iSu1xWEXsG1ipL448fmIhs4zJ8P6o/export?format=csv&t={timestamp}"

    # 1. Baca data mentah dari Google Sheets
    df_raw = pd.read_csv(sheet_csv_url, header=None, dtype=str)

    # Kunci indeks header ke baris ke-2 (index 1) di mana nama kapal sebenarnya berada
    header_idx = 1

    # Ambil baris header kapal
    raw_headers = df_raw.iloc[header_idx].tolist()

    # Tentukan baris data mulai setelah header
    df_data = df_raw.iloc[header_idx + 1 :].copy()

    # Tentukan nama kapal dengan mengisi merged cells (ffill)
    clean_headers = []
    last_kapal = "Kapal Unknown"

    for i, h in enumerate(raw_headers):
        h_str = str(h).strip() if pd.notnull(h) else ""

        # Abaikan jika ini teks label 'Tanggal Berakhir Surat'
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

    # Filter baris yang Jenis Surat-nya kosong atau cuma header terikut
    df_data = df_data.dropna(subset=["Jenis Surat"])
    df_data["Jenis Surat"] = df_data["Jenis Surat"].astype(str).str.strip()

    df_data = df_data[
        ~df_data["Jenis Surat"].isin(["", "nan", "NaN", "JENIS SURAT", "None"])
    ]

    kolom_kapal = [c for c in clean_headers if c != "Jenis Surat"]

    # 2. Unpivot / Transpose
    df_melted = pd.melt(
        df_data,
        id_vars=["Jenis Surat"],
        value_vars=kolom_kapal,
        var_name="Nama Kapal",
        value_name="Tgl_Raw",
    )

    # Bersihkan nama kapal dari sufiks unik kolom
    df_melted["Nama Kapal"] = (
        df_melted["Nama Kapal"]
        .astype(str)
        .str.replace(r"\s\(Col\s\d+\)$", "", regex=True)
    )

    # Filter sel tanggal kosong / strip
    df_melted = df_melted[
        df_melted["Tgl_Raw"].notnull()
        & ~df_melted["Tgl_Raw"]
        .astype(str)
        .str.strip()
        .isin(["", "-", "None", "nan", "NaN", "0"])
    ].copy()

    # 3. Parsing Tanggal
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

    # Filter data yang tidak valid
    df_melted = df_melted[df_melted["Tgl Expired"].notnull()].copy()

    def get_status(row):
        tgl_str = row["Tgl Expired"]
        sisa = row["Sisa Hari"]

        if tgl_str == "FORMAT SALAH":
            return "⚠️ FORMAT TANGGAL SALAH"

        sisa = int(sisa)
        if sisa <= 0:
            return "🔴 EXPIRED"
        elif sisa <= 14:
            return "🔴 SANGAT DESAK (<=14 Hari)"
        elif sisa <= 30:
            return "🟡 PERINGATAN (<=30 Hari)"
        else:
            return "🟢 AMAN"

    df_melted["Status"] = df_melted.apply(get_status, axis=1)

    return df_melted[
        ["Nama Kapal", "Jenis Surat", "Tgl Expired", "Sisa Hari", "Status"]
    ]


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

    st.subheader("📋 Daftar Detail Surat Kapal")
    st.dataframe(df_filtered, use_container_width=True, hide_index=True)

except Exception as e:
    st.error(f"Gagal membaca data dari Google Sheets.\n\nDetail Error: {e}")
