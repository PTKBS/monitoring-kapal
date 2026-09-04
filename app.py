import datetime
import time
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Monitoring Surat Kapal", page_icon="🚢", layout="wide"
)

st.title("🚢 Dashboard Monitoring Masa Berlaku Surat Kapal")
st.caption("Aplikasi pemantauan otomatis via Google Sheets (Real-time Live)")


# TANPA @st.cache_data agar data ditarik langsung dari Google Sheets
def load_data():
    # Menambahkan timestamp unik agar URL selalu dianggap baru oleh server (bypass cache)
    timestamp = int(time.time())
    sheet_csv_url = f"https://docs.google.com/spreadsheets/d/1ovR8ZxhQmLYv73iSu1xWEXsG1ipL448fmIhs4zJ8P6o/export?format=csv&t={timestamp}"

    # 1. Baca data dari Google Sheets CSV
    df_raw = pd.read_csv(sheet_csv_url, header=1)

    col_jenis_surat = df_raw.columns[0]
    df_raw = df_raw.rename(columns={col_jenis_surat: "Jenis Surat"})

    kolom_kapal = [
        c
        for c in df_raw.columns[1:]
        if "Unnamed" not in str(c) and str(c).strip() != ""
    ]

    # 2. Transpose / Unpivot
    df_melted = pd.melt(
        df_raw,
        id_vars=["Jenis Surat"],
        value_vars=kolom_kapal,
        var_name="Nama Kapal",
        value_name="Tgl_Raw",
    )

    df_melted = df_melted.dropna(subset=["Jenis Surat"])
    df_melted["Jenis Surat"] = df_melted["Jenis Surat"].astype(str).str.strip()

    # 3. Konversi Tanggal (Format DD/MM/YYYY)
    def convert_date(val):
        if pd.isnull(val) or str(val).strip() in [
            "",
            "-",
            "NaN",
            "nan",
            "0",
            "None",
        ]:
            return None

        val_str = str(val).strip()
        parsed = pd.to_datetime(val_str, errors="coerce", dayfirst=True)

        if pd.notnull(parsed) and parsed.year > 1980:
            return parsed.date()
        return None

    dt_series = df_melted["Tgl_Raw"].apply(convert_date)

    df_valid = df_melted[dt_series.notnull()].copy()
    dt_series_valid = dt_series[dt_series.notnull()]

    today = datetime.date.today()

    df_valid["Tgl Expired"] = dt_series_valid.apply(
        lambda x: x.strftime("%d-%b-%Y")
    )
    df_valid["Sisa Hari"] = dt_series_valid.apply(lambda x: (x - today).days)

    def get_status(sisa):
        sisa = int(sisa)
        if sisa <= 0:
            return "🔴 EXPIRED"
        elif sisa <= 14:
            return "🔴 SANGAT DESAK (<=14 Hari)"
        elif sisa <= 30:
            return "🟡 PERINGATAN (<=30 Hari)"
        else:
            return "🟢 AMAN"

    df_valid["Status"] = df_valid["Sisa Hari"].apply(get_status)

    return df_valid[
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

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🔴 Expired", f"{total_expired} Surat")
    col2.metric("🚨 Sangat Desak (H-14)", f"{total_desak} Surat")
    col3.metric("🟡 Peringatan (H-30)", f"{total_warning} Surat")
    col4.metric("🟢 Aman", f"{total_aman} Surat")

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
