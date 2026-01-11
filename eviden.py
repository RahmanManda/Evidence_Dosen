import streamlit as st
import pandas as pd
from fpdf import FPDF
import re
from datetime import datetime
from io import BytesIO
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Sistem LCKB & Evidence", layout="wide", page_icon="🎓")

# --- DATA MASTER ---
BULAN_INDO = {
    1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April', 5: 'Mei', 6: 'Juni',
    7: 'Juli', 8: 'Agustus', 9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember'
}

DAFTAR_DOSEN_RESMI = [
    "Amran Eku, M. Pd.", "Andi Nurmawaddah, M. Pd.", "Asmiraty. M.Pd.I",
    "Dr. Andy, S.Pd.I., M.Pd.", "Dr. Kartini Limatahu, MA", "Dr. Khalid Hasan Minabari, MA.",
    "Dr. M. Ridha Assagaf, S. Ag., M.Pd.", "Dr. Mubin Noho, S.Ag., M.Ag", "Dr. Usman Ilyas, M. Pd.",
    "Dra. Nursin Sapil, M.Pd.I", "Drs. Hi Ibrahim Muhammad, M.Pd.I", "Drs. Kamarun M. Sebe, M.Pd.",
    "Drs. Ramli Yusuf, M.Pd.", "Elfira Mahmud, M.Pd.", "Hamdy M. Zen, M. Pd.I",
    "Irno, S.Hum., M.Hum.", "M. Rizki Hi. Aman", "Mawardi Djamaludin",
    "Minggusta Juliadarma, M.Pd.I", "Mudayanah, M.Pd", "Puji Dwi Rahayu, M.Pd.",
    "Rinelsa R. Husaen, M.Pd", "Yani Djawa, S.Pd,M.Pd.Si", "Zainuddin Arifin"
]

KATEGORI_LABEL = {
    'A': 'BIDANG PENDIDIKAN DAN PENGAJARAN',
    'B': 'BIDANG PENELITIAN',
    'C': 'BIDANG PENGABDIAN MASYARAKAT',
    'D': 'BIDANG PENUNJANG AKADEMIK'
}

# --- FUNGSI HELPER EVIDENCE (VERSI 1) ---
def normalize_name(raw_name):
    if pd.isna(raw_name): return ""
    name = str(raw_name).upper()
    gelar_pattern = r'\b(DR|DRA|DRS|IR|S\.PD|M\.PD|S\.AG|M\.AG|S\.HUM|M\.HUM|S\.SI|M\.SI|S\.KOM|M\.KOM|PH\.D|M\.PI|S\.H|M\.H|I|II|S\.SOS|M\.SOS)\b'
    name = re.sub(gelar_pattern, '', name)
    name = re.sub(r'[.,]', ' ', name)
    name = " ".join(name.split())
    return name

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

def parse_evidence_full(row):
    jenis = str(row.get('Pilih Jenis Ujian', ''))
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
    return {'ba': process_links(raw_ba), 'foto': process_links(raw_foto), 'naskah': process_links(raw_naskah)}

@st.cache_data
def load_data(url):
    try:
        df = pd.read_csv(url)
        df.columns = df.columns.str.strip() 
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], dayfirst=True, errors='coerce')
        df['Bulan'] = df['Timestamp'].dt.month
        df['Tahun'] = df['Timestamp'].dt.year
        keywords = ['dosen', 'pembimbing', 'penguji']
        target_cols = [c for c in df.columns if 'nama' in c.lower() and any(k in c.lower() for k in keywords)]
        return df, target_cols
    except Exception as e:
        st.error(f"Error membaca CSV: {e}")
        return None, None

# --- GENERATOR PDF & DOCX (Sama seperti sebelumnya) ---
class LCKB_PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 5, 'KEMENTERIAN AGAMA REPUBLIK INDONESIA', 0, 1, 'C')
        self.cell(0, 5, 'INSTITUT AGAMA ISLAM NEGERI (IAIN) TERNATE', 0, 1, 'C')
        self.ln(2); self.line(10, 22, 200, 22); self.ln(5)

def create_lckb_pdf_bytes(data_items, dosen_name, bulan, tahun, nama_dekan, nip_dekan):
    pdf = LCKB_PDF('P', 'mm', 'A4')
    pdf.add_page()
    pdf.set_font('Arial', 'B', 11); pdf.cell(0, 6, 'LAPORAN CAPAIAN KINERJA BULANAN (LCKB)', 0, 1, 'C')
    pdf.set_font('Arial', '', 10); pdf.cell(0, 5, f'BULAN: {str(bulan).upper()} {tahun}', 0, 1, 'C'); pdf.ln(5)
    pdf.cell(30, 5, 'Nama', 0, 0); pdf.cell(5, 5, ':', 0, 0); pdf.cell(0, 5, dosen_name, 0, 1); pdf.ln(5)
    pdf.set_fill_color(230, 230, 230); pdf.set_font('Arial', 'B', 9)
    cols = [('NO', 10), ('URAIAN TUGAS/KEGIATAN', 80), ('VOL', 20), ('SATUAN', 20), ('BUKTI FISIK', 60)]
    for txt, w in cols: pdf.cell(w, 8, txt, 1, 0, 'C', 1)
    pdf.ln(8); pdf.set_font('Arial', '', 8)
    no = 1
    for kat in ['A', 'B', 'C', 'D']:
        pdf.set_font('Arial', 'B', 9); pdf.cell(190, 7, f"{kat}. {KATEGORI_LABEL[kat]}", 1, 1, 'L', 1)
        pdf.set_font('Arial', '', 8)
        items = [x for x in data_items if x['kategori'] == kat]
        if not items: pdf.cell(190, 6, " (Tidak ada kegiatan)", 1, 1, 'C')
        else:
            for it in items:
                pdf.cell(10, 6, str(no), 1, 0, 'C'); pdf.cell(80, 6, it['uraian'][:50], 1, 0, 'L')
                pdf.cell(20, 6, str(it['volume']), 1, 0, 'C'); pdf.cell(20, 6, it['satuan'], 1, 0, 'C')
                pdf.cell(60, 6, "Terlampir", 1, 1, 'L'); no += 1
    pdf.ln(10); y = pdf.get_y(); pdf.set_xy(20, y); pdf.cell(60, 5, "Mengetahui, Dekan FTIK,", 0, 0, 'C')
    pdf.set_xy(120, y); pdf.cell(60, 5, f'Ternate, {datetime.now().strftime("%d-%m-%Y")}', 0, 1, 'C')
    pdf.set_x(120); pdf.cell(60, 5, 'Yang Melaporkan,', 0, 1, 'C'); pdf.ln(15)
    pdf.set_font('Arial', 'B', 9); pdf.set_xy(20, pdf.get_y()); pdf.cell(60, 5, nama_dekan, 0, 0, 'C')
    pdf.set_xy(120, pdf.get_y()); pdf.cell(60, 5, dosen_name, 0, 1, 'C')
    return pdf.output(dest='S').encode('latin-1')

def create_lckb_docx_bytes(data_items, dosen_name, bulan, tahun, nama_dekan, nip_dekan):
    doc = Document(); doc.add_paragraph('LAPORAN LCKB').alignment = WD_ALIGN_PARAGRAPH.CENTER
    table = doc.add_table(rows=1, cols=5); table.style = 'Table Grid'
    for i, txt in enumerate(['NO', 'URAIAN', 'VOL', 'SAT', 'BUKTI']): table.rows[0].cells[i].text = txt
    no = 1
    for kat in ['A', 'B', 'C', 'D']:
        row = table.add_row().cells; row[0].merge(row[4]); row[0].text = f"{kat}. {KATEGORI_LABEL[kat]}"
        for it in [x for x in data_items if x['kategori'] == kat]:
            cells = table.add_row().cells; cells[0].text, cells[1].text, cells[2].text, cells[3].text, cells[4].text = str(no), it['uraian'], str(it['volume']), it['satuan'], it['bukti']; no += 1
    f = BytesIO(); doc.save(f); f.seek(0); return f

# --- MAIN APP ---
url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQinSdwQBQZj649QKRimqqmTFQ0WaSlEHucehHOEg7jvTaioDXe0snCcpo3kTJJsnFrIcqEasjif9E8/pub?output=csv"
df, target_cols = load_data(url)
if 'manual_data' not in st.session_state: st.session_state['manual_data'] = []

st.sidebar.title("Navigasi")
menu = st.sidebar.radio("Menu:", ["1. Cek Evidence Ujian", "2. Buat LCKB (Dosen)"])
nama_dekan = st.sidebar.text_input("Nama Dekan", "Dr. H. Sahjad M. Aksan, M.Phil")
nip_dekan = st.sidebar.text_input("NIP Dekan", "19xxxxxxx")

if df is not None:
    if menu == "1. Cek Evidence Ujian":
        st.title("📂 Evidence Ujian")
        search = st.text_input("🔍 Cari Nama Dosen atau Mahasiswa:")
        
        # Filter Logic
        if search:
            mask = df.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)
            df_filtered = df[mask]
        else:
            df_filtered = df

        st.info(f"Menampilkan {len(df_filtered)} data.")
        st.dataframe(df_filtered)

        st.divider()
        st.subheader("🖼️ Preview & Detail Bukti")
        
        # Tampilkan detail tiap baris (Ver 1 Style)
        for idx, row in df_filtered.head(10).iterrows():
            ev = parse_evidence_full(row)
            ket = row.get('Nama Matkul', row.get('Nama Lengkap Mahasiswa', '-'))
            
            with st.expander(f"📅 {row['Timestamp'].strftime('%d %b %Y') if not pd.isna(row['Timestamp']) else 'N/A'} | {row.get('Pilih Jenis Ujian','Ujian')} | {ket}"):
                c1, c2 = st.columns([1, 2])
                with c1:
                    if ev['foto']:
                        thumbs = [x['thumb'] for x in ev['foto'] if x['thumb']]
                        if thumbs: st.image(thumbs, width=150, caption=["Foto Bukti"]*len(thumbs))
                        else: st.warning("Thumbnail tidak tersedia")
                    else: st.info("Tidak ada foto")
                with c2:
                    if ev['ba']:
                        st.markdown("**📄 Berita Acara:**")
                        for l in ev['ba']: st.code(l['original'], language="text")
                    if ev['naskah']:
                        st.markdown("**📝 Naskah Soal:**")
                        for l in ev['naskah']: st.code(l['original'], language="text")
                    if ev['foto']:
                        st.markdown("**🔗 Link Foto:**")
                        for l in ev['foto']: st.code(l['original'], language="text")

    else:
        st.title("📝 Buat LCKB (Dosen)")
        # ... (Kode LCKB sama seperti sebelumnya) ...
        c1, c2, c3 = st.columns(3)
        dsn = c1.selectbox("Dosen:", DAFTAR_DOSEN_RESMI)
        bln = c2.selectbox("Bulan:", list(BULAN_INDO.values()))
        thn = c3.number_input("Tahun:", 2024, 2030, 2025)
        
        # Auto-pull dari data Mahasiswa untuk Dosen terpilih
        mask_dsn = pd.Series(False, index=df.index)
        for col in target_cols: mask_dsn |= df[col].apply(normalize_name).str.contains(normalize_name(dsn), na=False)
        mask_period = (df['Bulan'] == list(BULAN_INDO.keys())[list(BULAN_INDO.values()).index(bln)]) & (df['Tahun'] == thn)
        df_auto = df[mask_dsn & mask_period]

        st.write(f"Ditemukan {len(df_auto)} data ujian mahasiswa.")
        
        with st.form("manual"):
            kat = st.selectbox("Kategori", list(KATEGORI_LABEL.keys()), format_func=lambda x: KATEGORI_LABEL[x])
            uraian = st.text_input("Kegiatan")
            vol = st.number_input("Vol", 1)
            sat = st.text_input("Satuan", "Kegiatan")
            buk = st.text_input("Link Bukti")
            if st.form_submit_button("Tambah ke Draft"):
                st.session_state['manual_data'].append({'kategori':kat, 'uraian':uraian, 'volume':vol, 'satuan':sat, 'bukti':buk})
                st.rerun()

        # Combine Data
        final_list = []
        for _, r in df_auto.iterrows():
            final_list.append({'kategori':'A', 'uraian': f"Menguji {r.get('Pilih Jenis Ujian')} Mhs: {r.get('Nama Lengkap Mahasiswa','-')}", 'volume':1, 'satuan':'Mhs', 'bukti': 'Link Terlampir'})
        final_list += st.session_state['manual_data']

        if final_list:
            st.table(final_list)
            if st.button("Hapus Draft Manual"): st.session_state['manual_data'] = []; st.rerun()
            
            c_pdf, c_word = st.columns(2)
            pdf_b = create_lckb_pdf_bytes(final_list, dsn, bln, thn, nama_dekan, nip_dekan)
            c_pdf.download_button("📄 Download PDF", pdf_b, f"LCKB_{dsn}_{bln}.pdf", "application/pdf")
            
            word_b = create_lckb_docx_bytes(final_list, dsn, bln, thn, nama_dekan, nip_dekan)
            c_word.download_button("📝 Download Word", word_b, f"LCKB_{dsn}_{bln}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")