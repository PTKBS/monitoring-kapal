import datetime
import pandas as pd
import streamlit as st

# --- KONFIGURASI HALAMAN WEB ---
st.set_page_config(
    page_title="Monitoring Surat Kapal", page_icon="🚢", layout="wide"
)

st.title("🚢 Dashboard Monitoring Masa Berlaku Surat Kapal")
st.caption("Aplikasi pemantauan otomatis dari file Excel (`.xlsb`)")

nama_file = "DAFTAR EXP SURAT KAPAL - PYTHON.xlsb"


@st.cache_data
def load_data():
    # 1. Baca data mulai dari baris ke-2 (Baris nama kapal)
    df_raw = pd.read_excel(nama_file, engine="pyxlsb", header=1)

    # Kolom A adalah Nama Jenis Surat
    col_jenis_surat = df_raw.columns[0]
    df_raw = df_raw.rename(columns={col_jenis_surat: "Jenis Surat"})

    # 2. Ambil daftar kolom Nama Kapal (Abaikan kolom Unnamed)
    kolom_kapal = [
        c
        for c in df_raw.columns[1:]
        if "Unnamed" not in str(c) and str(c).strip() != ""
    ]

    # 3. TRANSPOSE / UNPIVOT TABEL MATRIKS JADI TABEL MEMANJANG
    df_melted = pd.melt(
        df_raw,
        id_vars=["Jenis Surat"],
        value_vars=kolom_kapal,
        var_name="Nama Kapal",
        value_name="Tgl_Raw",
    )

    # Hapus baris yang jenis suratnya kosong
    df_melted = df_melted.dropna(subset=["Jenis Surat"])
    df_melted["Jenis Surat"] = df_melted["Jenis Surat"].astype(str).str.strip()

    # 4. Konversi Tanggal Serial Excel / Teks Tanggal
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
        try:
            val_num = float(val)
            if val_num > 30000:  # Serial Date Excel
                return pd.to_datetime(
                    val_num, unit="D", origin="1899-12-30"
                ).date()
        except Exception:
            pass

        parsed = pd.to_datetime(val, errors="coerce")
        if pd.notnull(parsed) and parsed.year > 1980:
            return parsed.date()
        return None

    dt_series = df_melted["Tgl_Raw"].apply(convert_date)

    # Hanya ambil sel yang tanggalnya terisi (Tongkang tanpa sertifikat otomatis terabaikan)
    df_valid = df_melted[dt_series.notnull()].copy()
    dt_series_valid = dt_series[dt_series.notnull()]

    today = datetime.date.today()

    df_valid["Tgl Expired"] = dt_series_valid.apply(
        lambda x: x.strftime("%d-%b-%Y")
    )
    df_valid["Sisa Hari"] = dt_series_valid.apply(lambda x: (x - today).days)

    # 5. Hitung Status Expiry
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

    # Susun ulang urutan kolom yang tampil
    df_final = df_valid[
        ["Nama Kapal", "Jenis Surat", "Tgl Expired", "Sisa Hari", "Status"]
    ]

    return df_final


try:
    df = load_data()

    # --- METRICS RINGKASAN ---
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

    # --- SIDEBAR FILTER ---
    st.sidebar.header("🔍 Filter Data")

    # Filter Status
    status_options = list(df["Status"].unique())
    selected_status = st.sidebar.multiselect(
        "Pilih Status:", options=status_options, default=status_options
    )

    # Filter Nama Kapal
    kapal_options = list(df["Nama Kapal"].unique())
    selected_kapal = st.sidebar.multiselect(
        "Filter Nama Kapal:", options=kapal_options, default=kapal_options
    )

    # Filter Jenis Surat
    surat_options = list(df["Jenis Surat"].unique())
    selected_surat = st.sidebar.multiselect(
        "Filter Jenis Surat:", options=surat_options, default=surat_options
    )

    # Eksekusi Filter
    df_filtered = df[
        (df["Status"].isin(selected_status))
        & (df["Nama Kapal"].isin(selected_kapal))
        & (df["Jenis Surat"].isin(selected_surat))
    ]

    # Urutkan dari yang paling mendesak
    if "Sisa Hari" in df_filtered.columns:
        df_filtered = df_filtered.sort_values(
            by="Sisa Hari", ascending=True, na_position="last"
        )

    # Tampilkan Tabel
    st.subheader("📋 Daftar Detail Surat Kapal")
    st.dataframe(df_filtered, use_container_width=True, hide_index=True)

except Exception as e:
    st.error(f"Gagal membaca file data `{nama_file}`.\n\nDetail Error: {e}")