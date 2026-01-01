import streamlit as st
import pandas as pd
from fpdf import FPDF
import base64
import re
from datetime import datetime

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Sistem Pelaporan Ujian", layout="wide", page_icon="🎓")

# --- 0. KONSTANTA BULAN INDONESIA ---
BULAN_INDO = {
    1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April', 5: 'Mei', 6: 'Juni',
    7: 'Juli', 8: 'Agustus', 9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember'
}

# --- 1. LOGIKA PAWANG NAMA (SMART CLEANING) ---
def normalize_name(raw_name):
    if pd.isna(raw_name): return ""
    name = str(raw_name).upper()
    # Hapus gelar umum
    gelar_pattern = r'\b(DR|DRA|DRS|IR|S\.PD|M\.PD|S\.AG|M\.AG|S\.HUM|M\.HUM|S\.SI|M\.SI|S\.KOM|M\.KOM|PH\.D|M\.PI|S\.H|M\.H|I|II|S\.SOS|M\.SOS)\b'
    name = re.sub(gelar_pattern, '', name)
    name = re.sub(r'[.,]', ' ', name) # Hapus titik koma
    name = " ".join(name.split()) # Hapus spasi ganda
    return name

# --- 2. FUNGSI UTILITAS LINK ---
def extract_drive_id(url):
    if not isinstance(url, str): return None
    patterns = [r'/d/([a-zA-Z0-9_-]{25,})', r'id=([a-zA-Z0-9_-]{25,})', r'open\?id=([a-zA-Z0-9_-]{25,})']
    for p in patterns:
        m = re.search(p, url)
        if m: return m.group(1)
    return None

def process_links(raw_link_str):
    if pd.isna(raw_link_str) or not isinstance(raw_link_str, str): return []
    raw_links = re.split(r'[,\n\s]+', raw_link_str)
    processed = []
    for link in raw_links:
        link = link.strip().replace('"', '').replace("'", "")
        if len(link) < 10: continue
        fid = extract_drive_id(link)
        thumb = f"https://lh3.googleusercontent.com/d/{fid}=s400" if fid else None
        processed.append({'original': link, 'thumb': thumb})
    return processed

# --- 3. LOAD DATA & DETEKSI SEMUA PIHAK TERLIBAT ---
@st.cache_data
def load_data(url):
    try:
        df = pd.read_csv(url)
        df.columns = df.columns.str.strip() 
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], dayfirst=True, errors='coerce')
        
        # Buat Kolom Periode
        def get_periode_indo(dt):
            if pd.isna(dt): return "Tanggal Error"
            return f"{BULAN_INDO[dt.month]} {dt.year}"
        df['Periode_Str'] = df['Timestamp'].apply(get_periode_indo)
        
        # --- PERBAIKAN UTAMA DISINI ---
        # 1. Cari SEMUA kolom yang mengandung kata "Dosen", "Pembimbing", atau "Penguji"
        keywords = ['dosen', 'pembimbing', 'penguji']
        target_cols = [c for c in df.columns if 'nama' in c.lower() and any(k in c.lower() for k in keywords)]
        
        # 2. Normalisasi semua kolom tersebut agar bisa dicari
        # Kita simpan di dataframe baru khusus untuk pencarian
        search_df = df[target_cols].copy()
        for col in target_cols:
            search_df[col] = search_df[col].apply(normalize_name)
            
        # 3. Kumpulkan semua nama unik dari SELURUH kolom tersebut untuk Dropdown
        unique_names = set()
        for col in target_cols:
            unique_names.update(search_df[col].dropna().unique())
            
        # Bersihkan list nama
        clean_names_list = sorted([x for x in unique_names if isinstance(x, str) and x.strip() != ""])
        
        return df, target_cols, clean_names_list
        
    except Exception as e:
        st.error(f"Error membaca CSV: {e}")
        return None, None, None

def parse_evidence(row):
    jenis = str(row.get('Pilih Jenis Ujian', ''))
    label = "Ujian"
    if 'UAS' in jenis: label = "UAS"
    elif 'Proposal' in jenis: label = "Proposal"
    elif 'Kompre' in jenis: label = "Kompre"
    elif 'Skripsi' in jenis: label = "Skripsi"
    
    raw_ba = raw_foto = raw_naskah = None
    if 'UAS' in jenis:
        raw_ba = row.get('Upload Berita Acara UAS (dalam format PDF/JPG/PNG)')
        raw_foto = row.get('Foto/Dokumentasi Pelaksanaan UAS   (dalam format PDF/JPG/PNG)')
        raw_naskah = row.get('Naskah Soal UAS   (dalam format PDF/JPG/PNG)')
    elif 'Proposal' in jenis:
        raw_ba = row.get('Upload Berita Acara Ujian Proposal (dalam format PDF)')
        raw_foto = row.get('Foto/Dokumentasi Pelaksanaan Ujian Proposal')
    elif 'Kompre' in jenis:
        raw_ba = row.get('Upload Berita Acara Ujian Komprehensif (dalam format PDF)')
        raw_foto = row.get('Foto/Dokumentasi Pelaksanaan Ujian Komprehensif')
    elif 'Skripsi' in jenis:
        raw_ba = row.get('Upload Berita Acara Ujian Skripsi (dalam format PDF)')
        raw_foto = row.get('Foto/Dokumentasi Pelaksanaan Ujian Skripsi')

    return {'label': label, 'ba': process_links(raw_ba), 'foto': process_links(raw_foto), 'naskah': process_links(raw_naskah)}

# --- 4. PDF GENERATOR ---
def create_pdf(dataframe, dosen_name, periode_label):
    class PDF(FPDF):
        def header(self):
            self.set_font('Arial', 'B', 12)
            self.cell(0, 7, f'Laporan Bukti Ujian: {dosen_name}', 0, 1, 'C')
            self.set_font('Arial', 'I', 10)
            self.cell(0, 7, f'Periode: {periode_label}', 0, 1, 'C')
            self.ln(5)
            
    pdf = PDF('L'); pdf.add_page(); pdf.set_font("Arial", size=9)
    pdf.set_fill_color(230,230,230)
    pdf.cell(25, 10, "Tanggal", 1,0,'C',1)
    pdf.cell(40,10,"Jenis Ujian",1,0,'C',1)
    pdf.cell(60,10,"Mhs/Matkul",1,0,'C',1)
    pdf.cell(150,10,"Link Bukti",1,1,'C',1)
    
    pdf.set_font("Arial", size=8)
    for i, row in dataframe.iterrows():
        txt = ""
        for x in row['Links_BA']: txt += f"[BA] {x}\n"
        for x in row['Links_Naskah']: txt += f"[Soal] {x}\n"
        for x in row['Links_Foto']: txt += f"[Foto] {x}\n"
        
        h = max(10, (txt.count('\n')+1)*5)
        if pdf.get_y()+h > 185: pdf.add_page()
        
        x=pdf.get_x(); y=pdf.get_y()
        pdf.cell(25,h,str(row['Tanggal'])[:10],1)
        pdf.cell(40,h,str(row['Jenis Ujian'])[:25],1)
        pdf.cell(60,h,str(row['Keterangan'])[:35],1)
        pdf.multi_cell(150,5,txt,1)
        pdf.set_xy(x,y+h)
    
    # OUTPUT BYTES (FPDF2)
    return pdf.output(dest='S')

# --- MAIN APP ---
st.title("📂 Portal E-Eviden Ujian")

url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQinSdwQBQZj649QKRimqqmTFQ0WaSlEHucehHOEg7jvTaioDXe0snCcpo3kTJJsnFrIcqEasjif9E8/pub?output=csv"

# Load data dengan logika baru
df, target_cols, clean_names_list = load_data(url)

if df is not None and clean_names_list:
    st.sidebar.header("🔍 Filter Data")
    
    # 1. Dropdown Nama (Sekarang berisi SEMUA dosen yang pernah disebut di sheet)
    selected_clean_name = st.sidebar.selectbox("Pilih Nama Dosen/Penguji:", clean_names_list)
    
    # 2. Dropdown Periode
    df_sorted = df.sort_values('Timestamp', ascending=False)
    unique_periodes = df_sorted['Periode_Str'].unique().tolist()
    periode_options = ["Semua Waktu"] + unique_periodes
    selected_periode = st.sidebar.selectbox("Pilih Bulan/Tahun:", periode_options)
    
    # --- LOGIKA FILTERING MULTI-KOLOM ---
    # Cek apakah nama terpilih ada di SALAH SATU kolom (Dosen Utama / Pembimbing / Penguji)
    mask_name = pd.Series(False, index=df.index)
    
    for col in target_cols:
        # Kita normalisasi dulu kolom ini sebelum dicocokkan
        col_norm = df[col].apply(normalize_name)
        mask_name |= (col_norm == selected_clean_name)
        
    # Gabungkan dengan filter periode
    if selected_periode == "Semua Waktu":
        final_mask = mask_name
    else:
        mask_periode = df['Periode_Str'] == selected_periode
        final_mask = mask_name & mask_periode
        
    df_filtered = df[final_mask].copy()
    
    st.info(f"Menampilkan **{len(df_filtered)}** kegiatan di mana **{selected_clean_name}** terlibat (sebagai Penguji, Pembimbing, atau Dosen Utama).")
    
    # Sortir hasil berdasarkan tanggal terbaru
    df_filtered = df_filtered.sort_values('Timestamp', ascending=False)
    
    report_data = []
    
    for idx, row in df_filtered.iterrows():
        ev = parse_evidence(row)
        
        # Logika Keterangan (Matkul/Mhs)
        ket = "-"
        if pd.notna(row.get('Nama Matkul')):
            ket = row['Nama Matkul']
            if pd.notna(row.get('Nama Kelas')): ket += f" ({row['Nama Kelas']})"
        elif pd.notna(row.get('Nama Lengkap Mahasiswa')):
            ket = row['Nama Lengkap Mahasiswa']
        if ket == "-":
            mhs_cols = [c for c in df.columns if 'nama' in c.lower() and 'mahasiswa' in c.lower()]
            for c in mhs_cols: 
                if pd.notna(row.get(c)): ket = row[c]; break

        report_data.append({
            'Tanggal': row['Timestamp'], 'Jenis Ujian': row['Pilih Jenis Ujian'], 'Keterangan': ket,
            'Links_BA': [x['original'] for x in ev['ba']],
            'Links_Foto': [x['original'] for x in ev['foto']],
            'Links_Naskah': [x['original'] for x in ev['naskah']]
        })
        
        with st.expander(f"📅 {row['Timestamp'].strftime('%d %b %Y')} | {row['Pilih Jenis Ujian']} | {ket}"):
            c1, c2 = st.columns([1,2])
            with c1:
                 if ev['foto']: 
                     thumbs = [x['thumb'] for x in ev['foto'] if x['thumb']]
                     st.image(thumbs, width=150, caption=[f"Foto {i+1}" for i in range(len(thumbs))])
                 else: st.warning("Tidak ada foto")
            with c2:
                if ev['ba']:
                    st.markdown("**Berita Acara:**")
                    for x in ev['ba']: st.code(x['original'], language='text')
                if ev['naskah']:
                    st.markdown("**Naskah Soal:**")
                    for x in ev['naskah']: st.code(x['original'], language='text')
                if ev['foto']:
                    st.markdown("**Link Foto:**")
                    for x in ev['foto']: st.code(x['original'], language='text')

    if report_data:
        st.sidebar.divider()
        df_rep = pd.DataFrame(report_data)
        
        safe_periode = selected_periode.replace(" ", "_")
        filename_base = f"Laporan_{selected_clean_name}_{safe_periode}"
        
        st.sidebar.download_button("📥 Download Excel", df_rep.to_csv(index=False), f"{filename_base}.csv")
        
        if st.sidebar.button("📥 Generate PDF"):
            try:
                pdf_bytes = create_pdf(df_rep, selected_clean_name, selected_periode)
                b64 = base64.b64encode(pdf_bytes).decode()
                href = f'<a href="data:application/pdf;base64,{b64}" download="{filename_base}.pdf">Klik Disini Save PDF</a>'
                st.sidebar.markdown(href, unsafe_allow_html=True)
            except Exception as e: st.sidebar.error(f"Gagal buat PDF: {e}")

else:
    st.warning("Data belum bisa dibaca. Pastikan Link CSV benar.")
