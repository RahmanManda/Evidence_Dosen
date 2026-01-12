import streamlit as st
import pandas as pd
from fpdf import FPDF
import re
from datetime import datetime
from io import BytesIO
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement 
from docx.opc.constants import RELATIONSHIP_TYPE as RT

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

# --- FUNGSI HELPER ---
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

# --- GENERATOR PDF EVIDENCE ---
class EvidencePDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 5, 'KEMENTERIAN AGAMA REPUBLIK INDONESIA', 0, 1, 'C')
        self.cell(0, 5, 'INSTITUT AGAMA ISLAM NEGERI (IAIN) TERNATE', 0, 1, 'C')
        self.ln(2); self.line(10, 22, 200, 22); self.ln(5)

def create_evidence_pdf_bytes(df_filtered, dosen_name, periode_label):
    try:
        pdf = EvidencePDF('P', 'mm', 'A4')
        pdf.add_page()
        pdf.set_font('Arial', 'B', 11)
        pdf.cell(0, 6, 'LAPORAN BUKTI FISIK PELAKSANAAN UJIAN', 0, 1, 'C')
        pdf.set_font('Arial', '', 10)
        pdf.cell(0, 5, f'PERIODE: {periode_label.upper()}', 0, 1, 'C'); pdf.ln(8)
        pdf.set_font('Arial', '', 10)
        pdf.cell(30, 5, 'Nama Dosen', 0, 0); pdf.cell(5, 5, ':', 0, 0); pdf.cell(0, 5, dosen_name, 0, 1)
        pdf.ln(5)

        # BAGIAN 1: UAS
        df_uas = df_filtered[df_filtered['Pilih Jenis Ujian'].str.contains('UAS', case=False, na=False)]
        if not df_uas.empty:
            pdf.set_font('Arial', 'B', 10); pdf.cell(0, 8, 'A. UJIAN AKHIR SEMESTER (UAS)', 0, 1, 'L')
            pdf.set_fill_color(230, 230, 230); pdf.set_font('Arial', 'B', 8)
            cols = [('NO', 10), ('MATA KULIAH / KELAS', 70), ('BERITA ACARA', 35), ('DOKUMENTASI', 35), ('NASKAH SOAL', 35)]
            for txt, w in cols: pdf.cell(w, 8, txt, 1, 0, 'C', 1)
            pdf.ln(); pdf.set_font('Arial', '', 8)
            no = 1
            for _, row in df_uas.iterrows():
                ev = parse_evidence_full(row)
                matkul = f"{row.get('Nama Matkul','-')} ({row.get('Nama Kelas','-')})"
                link_ba = ev['ba'][0]['original'] if ev['ba'] else ""
                link_dok = ev['foto'][0]['original'] if ev['foto'] else ""
                link_soal = ev['naskah'][0]['original'] if ev['naskah'] else ""
                
                # Encode text
                matkul = matkul.encode('latin-1', 'ignore').decode('latin-1')

                h = 8
                if pdf.get_y() + h > 260: pdf.add_page()
                pdf.cell(10, h, str(no), 1, 0, 'C')
                pdf.cell(70, h, matkul[:40], 1, 0, 'L')
                x=pdf.get_x(); y=pdf.get_y()
                pdf.cell(35, h, "Buka File" if link_ba else "-", 1, 0, 'C', link=link_ba)
                pdf.cell(35, h, "Buka File" if link_dok else "-", 1, 0, 'C', link=link_dok)
                pdf.cell(35, h, "Buka File" if link_soal else "-", 1, 1, 'C', link=link_soal)
                no += 1
            pdf.ln(5)

        # BAGIAN 2: NON-UAS
        df_non_uas = df_filtered[~df_filtered['Pilih Jenis Ujian'].str.contains('UAS', case=False, na=False)]
        if not df_non_uas.empty:
            pdf.set_font('Arial', 'B', 10); pdf.cell(0, 8, 'B. UJIAN SKRIPSI / PROPOSAL / KOMPREHENSIF', 0, 1, 'L')
            pdf.set_fill_color(230, 230, 230); pdf.set_font('Arial', 'B', 8)
            cols = [('NO', 10), ('URAIAN KEGIATAN', 90), ('BERITA ACARA', 40), ('DOKUMENTASI', 40)]
            for txt, w in cols: pdf.cell(w, 8, txt, 1, 0, 'C', 1)
            pdf.ln(); pdf.set_font('Arial', '', 8)
            no = 1
            for _, row in df_non_uas.iterrows():
                ev = parse_evidence_full(row)
                uraian = f"{row.get('Pilih Jenis Ujian')} - {row.get('Nama Lengkap Mahasiswa','-')}"
                uraian = uraian.encode('latin-1', 'ignore').decode('latin-1')

                link_ba = ev['ba'][0]['original'] if ev['ba'] else ""
                link_dok = ev['foto'][0]['original'] if ev['foto'] else ""
                h = 8
                if pdf.get_y() + h > 260: pdf.add_page()
                pdf.cell(10, h, str(no), 1, 0, 'C')
                pdf.cell(90, h, uraian[:55], 1, 0, 'L')
                pdf.cell(40, h, "Buka File" if link_ba else "-", 1, 0, 'C', link=link_ba)
                pdf.cell(40, h, "Buka File" if link_dok else "-", 1, 1, 'C', link=link_dok)
                no += 1

        pdf.ln(10)
        if pdf.get_y() > 240: pdf.add_page()
        pdf.set_x(120); pdf.cell(60, 5, f'Ternate, {datetime.now().strftime("%d-%m-%Y")}', 0, 1, 'C')
        pdf.set_x(120); pdf.cell(60, 5, 'Dosen Yang Melaporkan,', 0, 1, 'C'); pdf.ln(20)
        pdf.set_x(120); pdf.set_font('Arial', 'B', 9); pdf.cell(60, 5, dosen_name, 0, 1, 'C')
        return pdf.output(dest='S').encode('latin-1', 'ignore')
    except Exception as e:
        return None

# --- GENERATOR WORD EVIDENCE (FIXED HYPERLINK) ---
def add_hyperlink(paragraph, url, text, color="0000FF", underline=True):
    part = paragraph.part
    r_id = part.relate_to(url, RT.HYPERLINK, is_external=True)
    hyperlink = OxmlElement('w:hyperlink')
    hyperlink.set(qn('r:id'), r_id)
    new_run = OxmlElement('w:r')
    rPr = OxmlElement('w:rPr')
    if color:
        c = OxmlElement('w:color')
        c.set(qn('w:val'), color)
        rPr.append(c)
    if underline:
        u = OxmlElement('w:u')
        u.set(qn('w:val'), 'single')
        rPr.append(u)
    new_run.append(rPr)
    new_text = OxmlElement('w:t')
    new_text.text = text
    new_run.append(new_text)
    hyperlink.append(new_run)
    paragraph._element.append(hyperlink)
    return hyperlink

def create_evidence_docx_bytes(df_filtered, dosen_name, periode_label):
    try:
        doc = Document()
        doc.add_paragraph('LAPORAN BUKTI FISIK PELAKSANAAN UJIAN').alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph(f'PERIODE: {periode_label}').alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph(f'Nama Dosen: {dosen_name}')
        doc.add_paragraph('\n')

        # TABEL UAS
        df_uas = df_filtered[df_filtered['Pilih Jenis Ujian'].str.contains('UAS', case=False, na=False)]
        if not df_uas.empty:
            doc.add_paragraph('A. UJIAN AKHIR SEMESTER (UAS)').runs[0].bold = True
            table = doc.add_table(rows=1, cols=5); table.style = 'Table Grid'
            hdr = table.rows[0].cells
            hdr[0].text='NO'; hdr[1].text='MATA KULIAH'; hdr[2].text='BERITA ACARA'; hdr[3].text='DOKUMENTASI'; hdr[4].text='NASKAH SOAL'
            no = 1
            for _, row in df_uas.iterrows():
                ev = parse_evidence_full(row)
                row_cells = table.add_row().cells
                row_cells[0].text = str(no)
                row_cells[1].text = f"{row.get('Nama Matkul','-')} ({row.get('Nama Kelas','-')})"
                
                ba = ev['ba'][0]['original'] if ev['ba'] else None
                dok = ev['foto'][0]['original'] if ev['foto'] else None
                soal = ev['naskah'][0]['original'] if ev['naskah'] else None
                
                if ba: add_hyperlink(row_cells[2].add_paragraph(), ba, "Buka File")
                else: row_cells[2].text = "-"
                if dok: add_hyperlink(row_cells[3].add_paragraph(), dok, "Buka File")
                else: row_cells[3].text = "-"
                if soal: add_hyperlink(row_cells[4].add_paragraph(), soal, "Buka File")
                else: row_cells[4].text = "-"
                no += 1
            doc.add_paragraph('\n')

        # TABEL NON-UAS
        df_non = df_filtered[~df_filtered['Pilih Jenis Ujian'].str.contains('UAS', case=False, na=False)]
        if not df_non.empty:
            doc.add_paragraph('B. UJIAN PROPOSAL / SKRIPSI / KOMPREHENSIF').runs[0].bold = True
            table = doc.add_table(rows=1, cols=4); table.style = 'Table Grid'
            hdr = table.rows[0].cells
            hdr[0].text='NO'; hdr[1].text='URAIAN KEGIATAN'; hdr[2].text='BERITA ACARA'; hdr[3].text='DOKUMENTASI'
            no = 1
            for _, row in df_non.iterrows():
                ev = parse_evidence_full(row)
                row_cells = table.add_row().cells
                row_cells[0].text = str(no)
                row_cells[1].text = f"{row.get('Pilih Jenis Ujian')} - {row.get('Nama Lengkap Mahasiswa')}"
                
                ba = ev['ba'][0]['original'] if ev['ba'] else None
                dok = ev['foto'][0]['original'] if ev['foto'] else None
                
                if ba: add_hyperlink(row_cells[2].add_paragraph(), ba, "Buka File")
                else: row_cells[2].text = "-"
                if dok: add_hyperlink(row_cells[3].add_paragraph(), dok, "Buka File")
                else: row_cells[3].text = "-"
                no += 1
                
        doc.add_paragraph('\n')
        sig = doc.add_paragraph(f'Ternate, {datetime.now().strftime("%d-%m-%Y")}\nDosen Yang Melaporkan,\n\n\n\n\n{dosen_name}')
        sig.alignment = WD_ALIGN_PARAGRAPH.RIGHT

        f = BytesIO(); doc.save(f); return f.getvalue()
    except Exception as e:
        return None

# --- GENERATOR LCKB (Menu 2) ---
class LCKB_PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 5, 'KEMENTERIAN AGAMA REPUBLIK INDONESIA', 0, 1, 'C')
        self.cell(0, 5, 'INSTITUT AGAMA ISLAM NEGERI (IAIN) TERNATE', 0, 1, 'C')
        self.ln(2); self.line(10, 22, 200, 22); self.ln(5)

def create_lckb_pdf_bytes(data_items, dosen_name, bulan, tahun, nama_dekan, nip_dekan):
    try:
        pdf = LCKB_PDF('P', 'mm', 'A4'); pdf.add_page()
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
                for item in items:
                    desc = item['uraian'].encode('latin-1', 'ignore').decode('latin-1')
                    pdf.cell(10, 6, str(no), 1, 0, 'C'); pdf.cell(80, 6, desc[:50], 1, 0, 'L')
                    pdf.cell(20, 6, str(item['volume']), 1, 0, 'C'); pdf.cell(20, 6, item['satuan'], 1, 0, 'C')
                    pdf.cell(60, 6, "Terlampir", 1, 1, 'L'); no += 1
        pdf.ln(10); y = pdf.get_y(); pdf.set_xy(20, y); pdf.cell(60, 5, "Mengetahui, Dekan FTIK,", 0, 0, 'C')
        pdf.set_xy(120, y); pdf.cell(60, 5, f'Ternate, {datetime.now().strftime("%d-%m-%Y")}', 0, 1, 'C')
        pdf.set_x(120); pdf.cell(60, 5, 'Yang Melaporkan,', 0, 1, 'C'); pdf.ln(15)
        pdf.set_font('Arial', 'B', 9); pdf.set_xy(20, pdf.get_y()); pdf.cell(60, 5, nama_dekan, 0, 0, 'C')
        pdf.set_xy(120, pdf.get_y()); pdf.cell(60, 5, dosen_name, 0, 1, 'C')
        return pdf.output(dest='S').encode('latin-1', 'ignore')
    except: return None

def create_lckb_docx_bytes(data_items, dosen_name, bulan, tahun, nama_dekan, nip_dekan):
    try:
        doc = Document(); doc.add_paragraph('LAPORAN LCKB').alignment = WD_ALIGN_PARAGRAPH.CENTER
        table = doc.add_table(rows=1, cols=5); table.style = 'Table Grid'
        for i, txt in enumerate(['NO', 'URAIAN', 'VOL', 'SAT', 'BUKTI']): table.rows[0].cells[i].text = txt
        no = 1
        for kat in ['A', 'B', 'C', 'D']:
            row = table.add_row().cells; row[0].merge(row[4]); row[0].text = f"{kat}. {KATEGORI_LABEL[kat]}"
            for it in [x for x in data_items if x['kategori'] == kat]:
                cells = table.add_row().cells; cells[0].text, cells[1].text, cells[2].text, cells[3].text, cells[4].text = str(no), it['uraian'], str(it['volume']), it['satuan'], it['bukti']; no += 1
        f = BytesIO(); doc.save(f); return f.getvalue()
    except: return None

# --- MAIN APP ---
url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQinSdwQBQZj649QKRimqqmTFQ0WaSlEHucehHOEg7jvTaioDXe0snCcpo3kTJJsnFrIcqEasjif9E8/pub?output=csv"
df, target_cols = load_data(url)
if 'manual_data' not in st.session_state: st.session_state['manual_data'] = []

st.sidebar.title("Navigasi")
menu = st.sidebar.radio("Menu:", ["1. Cek Evidence & Cetak", "2. Buat LCKB (Dosen)"])
nama_dekan = st.sidebar.text_input("Nama Dekan", "Dr. H. Sahjad M. Aksan, M.Phil")
nip_dekan = st.sidebar.text_input("NIP Dekan", "19xxxxxxx")

if df is not None:
    if menu == "1. Cek Evidence & Cetak":
        st.title("📂 Data Evidence")
        c1, c2, c3 = st.columns(3)
        dsn = c1.selectbox("Dosen:", DAFTAR_DOSEN_RESMI)
        # UPDATE: Ditambahkan 'Semua Data'
        mode = c2.selectbox("Filter Waktu:", ["Bulanan", "Semester Ganjil", "Semester Genap", "Tahunan", "Semua Data"])
        thn = c3.number_input("Tahun", 2024, 2030, datetime.now().year)
        
        # Filter Logic
        df_d = df[df.astype(str).apply(lambda x: x.str.contains(normalize_name(dsn), case=False)).any(axis=1)].copy()
        label = f"TAHUN {thn}"
        
        if mode == "Bulanan":
            bln = st.selectbox("Bulan:", list(BULAN_INDO.values()))
            b_int = list(BULAN_INDO.keys())[list(BULAN_INDO.values()).index(bln)]
            df_f = df_d[(df_d['Bulan']==b_int)&(df_d['Tahun']==thn)]
            label = f"{bln.upper()} {thn}"
        elif mode == "Semester Ganjil":
            df_f = df_d[(df_d['Bulan'].isin([7,8,9,10,11,12]))&(df_d['Tahun']==thn)]
            label = f"SEMESTER GANJIL {thn}"
        elif mode == "Semester Genap":
            df_f = df_d[(df_d['Bulan'].isin([1,2,3,4,5,6]))&(df_d['Tahun']==thn)]
            label = f"SEMESTER GENAP {thn}"
        elif mode == "Tahunan":
            df_f = df_d[df_d['Tahun']==thn]
        else: # SEMUA DATA
            df_f = df_d
            label = "SEMUA RIWAYAT DATA"

        st.divider(); st.write(f"Menampilkan **{len(df_f)}** data ({label})")
        
        tab1, tab2 = st.tabs(["Preview", "Download"])
        with tab1:
            if df_f.empty: st.warning("Data Kosong")
            for _, r in df_f.iterrows():
                ev = parse_evidence_full(r)
                with st.expander(f"{r['Timestamp'].strftime('%d %b')} | {r.get('Pilih Jenis Ujian')} | {r.get('Nama Lengkap Mahasiswa','-')}"):
                    ca, cb = st.columns([1,2])
                    with ca: 
                        if ev['foto']: st.image([x['thumb'] for x in ev['foto'] if x['thumb']], width=100)
                    with cb:
                        for k in ['ba','naskah','foto']:
                            if ev[k]: st.write(f"**{k.upper()}:** " + ", ".join([f"[{x['original']}]({x['original']})" for x in ev[k]]))
        with tab2:
            if not df_f.empty:
                c_p, c_w = st.columns(2)
                pdf_v = create_evidence_pdf_bytes(df_f, dsn, label)
                c_p.download_button("📄 PDF Laporan", pdf_v, f"Lap_{dsn}.pdf", "application/pdf")
                docx_v = create_evidence_docx_bytes(df_f, dsn, label)
                c_w.download_button("📝 Word Laporan", docx_v, f"Lap_{dsn}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    elif menu == "2. Buat LCKB (Dosen)":
        st.title("📝 Buat LCKB")
        c1, c2, c3 = st.columns(3)
        dsn = c1.selectbox("Dosen:", DAFTAR_DOSEN_RESMI)
        bln = c2.selectbox("Bulan:", list(BULAN_INDO.values()))
        thn = c3.number_input("Tahun", 2024, 2030, 2025)
        
        b_int = list(BULAN_INDO.keys())[list(BULAN_INDO.values()).index(bln)]
        mask_d = pd.Series(False, index=df.index)
        for c in target_cols: mask_d |= df[c].apply(normalize_name).str.contains(normalize_name(dsn), na=False)
        df_auto = df[mask_d & (df['Bulan']==b_int) & (df['Tahun']==thn)]
        
        st.info(f"Auto-detect: {len(df_auto)} ujian.")
        with st.form("add"):
            kat = st.selectbox("Kategori", list(KATEGORI_LABEL.keys()), format_func=lambda x:KATEGORI_LABEL[x])
            ur = st.text_input("Kegiatan"); vol = st.number_input("Vol",1); sat = st.text_input("Satuan","Keg"); buk = st.text_input("Bukti")
            if st.form_submit_button("Tambah"): st.session_state['manual_data'].append({'kategori':kat,'uraian':ur,'volume':vol,'satuan':sat,'bukti':buk}); st.rerun()
            
        final = [{'kategori':'A', 'uraian':f"Menguji {r.get('Pilih Jenis Ujian')} - {r.get('Nama Lengkap Mahasiswa')}", 'volume':1, 'satuan':'Mhs', 'bukti':'Link'} for _, r in df_auto.iterrows()] + st.session_state['manual_data']
        
        if final:
            st.table(final)
            if st.button("Clear Manual"): st.session_state['manual_data']=[]; st.rerun()
            ca, cb = st.columns(2)
            pdf_l = create_lckb_pdf_bytes(final, dsn, bln, thn, nama_dekan, nip_dekan)
            if pdf_l: ca.download_button("📄 PDF LCKB", pdf_l, "LCKB.pdf", "application/pdf")
            docx_l = create_lckb_docx_bytes(final, dsn, bln, thn, nama_dekan, nip_dekan)
            if docx_l: cb.download_button("📝 Word LCKB", docx_l, "LCKB.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")