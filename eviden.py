import streamlit as st
import pandas as pd
from fpdf import FPDF
import base64
import re
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from io import BytesIO
from docx import Document
from docx.shared import Pt, Inches, Cm
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

# --- KONEKSI GOOGLE DRIVE ---
def upload_to_drive(file_obj, filename):
    try:
        # Cek apakah secrets ada (untuk menghindari error di local tanpa setup)
        if "gcp_service_account" not in st.secrets:
            return "https://drive.google.com/file/d/dummy-link-karena-api-belum-set"
            
        gcp_info = st.secrets["gcp_service_account"]
        target_folder = st.secrets["target_folder_id"]
        creds = service_account.Credentials.from_service_account_info(
            gcp_info, scopes=['https://www.googleapis.com/auth/drive']
        )
        service = build('drive', 'v3', credentials=creds)
        file_metadata = {'name': filename, 'parents': [target_folder]}
        media = MediaIoBaseUpload(file_obj, mimetype=file_obj.type)
        file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
        return file.get('webViewLink')
    except Exception as e:
        st.error(f"Gagal Upload: {e}")
        return None

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

def parse_evidence(row):
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

# --- 1. GENERATOR PDF (Updated Layout) ---
class LCKB_PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 5, 'KEMENTERIAN AGAMA REPUBLIK INDONESIA', 0, 1, 'C')
        self.cell(0, 5, 'INSTITUT AGAMA ISLAM NEGERI (IAIN) TERNATE', 0, 1, 'C')
        self.ln(2)
        self.line(10, 22, 200, 22)
        self.ln(5)

def create_lckb_pdf_bytes(data_items, dosen_name, bulan, tahun, nama_dekan, nip_dekan):
    pdf = LCKB_PDF('P', 'mm', 'A4')
    pdf.add_page()
    
    pdf.set_font('Arial', 'B', 11)
    pdf.cell(0, 6, 'LAPORAN CAPAIAN KINERJA BULANAN (LCKB)', 0, 1, 'C')
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 5, f'BULAN: {str(bulan).upper()} {tahun}', 0, 1, 'C')
    pdf.ln(5)
    
    pdf.set_font('Arial', '', 10)
    pdf.cell(30, 5, 'Nama', 0, 0); pdf.cell(5, 5, ':', 0, 0); pdf.cell(0, 5, dosen_name, 0, 1)
    pdf.cell(30, 5, 'Fakultas', 0, 0); pdf.cell(5, 5, ':', 0, 0); pdf.cell(0, 5, 'Tarbiyah dan Ilmu Keguruan (FTIK)', 0, 1)
    pdf.ln(5)
    
    pdf.set_fill_color(230, 230, 230)
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(10, 8, 'NO', 1, 0, 'C', 1)
    pdf.cell(80, 8, 'URAIAN TUGAS/KEGIATAN', 1, 0, 'C', 1)
    pdf.cell(20, 8, 'VOL', 1, 0, 'C', 1)
    pdf.cell(20, 8, 'SATUAN', 1, 0, 'C', 1)
    pdf.cell(60, 8, 'BUKTI FISIK', 1, 1, 'C', 1)
    
    pdf.set_font('Arial', '', 8)
    
    no = 1
    for kat_code in ['A', 'B', 'C', 'D']:
        pdf.set_font('Arial', 'B', 9)
        pdf.cell(190, 7, f"{kat_code}. {KATEGORI_LABEL[kat_code]}", 1, 1, 'L', 1)
        
        items = [x for x in data_items if x['kategori'] == kat_code]
        pdf.set_font('Arial', '', 8)
        
        if not items:
            pdf.cell(190, 7, " (Tidak ada kegiatan)", 1, 1, 'C')
        else:
            for item in items:
                desc = item['uraian']
                bukti = item['bukti']
                if "http" in bukti and len(bukti) > 35: bukti_txt = "Link Google Drive (Terlampir)"
                else: bukti_txt = bukti

                push = max(pdf.get_string_width(desc)/80, 1) 
                h = 6 * (int(push) + 1)
                if pdf.get_y() + h > 260: pdf.add_page() # Cek batas bawah

                pdf.cell(10, h, str(no), 1, 0, 'C')
                x = pdf.get_x(); y = pdf.get_y()
                pdf.multi_cell(80, 6, desc, 1, 'L')
                pdf.set_xy(x + 80, y)
                pdf.cell(20, h, str(item['volume']), 1, 0, 'C')
                pdf.cell(20, h, item['satuan'], 1, 0, 'C')
                x = pdf.get_x(); y_curr = pdf.get_y()
                pdf.multi_cell(60, 6, bukti_txt, 1, 'L')
                pdf.set_xy(10, y + h)
                no += 1
                
    # --- FOOTER TANDA TANGAN (KIRI & KANAN) ---
    pdf.ln(10)
    # Cek space cukup
    if pdf.get_y() > 240: pdf.add_page()
    
    y_sig = pdf.get_y()
    
    # KIRI: DEKAN
    pdf.set_xy(20, y_sig)
    pdf.cell(60, 5, "Mengetahui,", 0, 1, 'C')
    pdf.set_xy(20, y_sig+5)
    pdf.cell(60, 5, "Dekan FTIK,", 0, 1, 'C')
    
    # KANAN: DOSEN
    pdf.set_xy(120, y_sig)
    pdf.cell(60, 5, f'Ternate, {datetime.now().strftime("%d-%m-%Y")}', 0, 1, 'C')
    pdf.set_xy(120, y_sig+5)
    pdf.cell(60, 5, 'Yang Melaporkan,', 0, 1, 'C')
    
    # SPACE TTD
    pdf.ln(25)
    y_name = pdf.get_y()
    
    # NAMA DEKAN
    pdf.set_xy(20, y_name)
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(60, 5, nama_dekan, 0, 1, 'C')
    pdf.set_xy(20, y_name+5)
    pdf.set_font('Arial', '', 9)
    pdf.cell(60, 5, f"NIP. {nip_dekan}", 0, 1, 'C')
    
    # NAMA DOSEN
    pdf.set_xy(120, y_name)
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(60, 5, dosen_name, 0, 1, 'C')
    # Bisa tambah NIP dosen di sini jika ada datanya

    return pdf.output(dest='S')

# --- 2. GENERATOR DOCX (NEW!) ---
def create_lckb_docx_bytes(data_items, dosen_name, bulan, tahun, nama_dekan, nip_dekan):
    doc = Document()
    
    # Set Margin
    sections = doc.sections
    for section in sections:
        section.top_margin = Cm(2)
        section.bottom_margin = Cm(2)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.5)

    # HEADER
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run('KEMENTERIAN AGAMA REPUBLIK INDONESIA\nINSTITUT AGAMA ISLAM NEGERI (IAIN) TERNATE')
    run.bold = True
    run.font.size = Pt(12)
    p.add_run('\n__________________________________________________________________________').bold = True

    # JUDUL
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(f'\nLAPORAN CAPAIAN KINERJA BULANAN (LCKB)\nBULAN {str(bulan).upper()} {tahun}')
    run.bold = True
    run.font.size = Pt(11)

    # BIODATA
    p = doc.add_paragraph(f'Nama\t: {dosen_name}\nFakultas\t: Tarbiyah dan Ilmu Keguruan (FTIK)')
    p.paragraph_format.tab_stops.add_tab_stop(Cm(3))

    # TABEL UTAMA
    table = doc.add_table(rows=1, cols=5)
    table.style = 'Table Grid'
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = 'NO'
    hdr_cells[1].text = 'URAIAN TUGAS/KEGIATAN'
    hdr_cells[2].text = 'VOL'
    hdr_cells[3].text = 'SATUAN'
    hdr_cells[4].text = 'BUKTI FISIK'
    
    # Set Widths (Approximation)
    for cell in hdr_cells:
        cell.paragraphs[0].runs[0].bold = True
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

    no = 1
    for kat_code in ['A', 'B', 'C', 'D']:
        # Row Kategori (Merged)
        row = table.add_row().cells
        row[0].merge(row[4])
        row[0].text = f"{kat_code}. {KATEGORI_LABEL[kat_code]}"
        row[0].paragraphs[0].runs[0].bold = True
        
        items = [x for x in data_items if x['kategori'] == kat_code]
        if not items:
            row = table.add_row().cells
            row[1].text = "(Tidak ada kegiatan)"
        else:
            for item in items:
                row_cells = table.add_row().cells
                row_cells[0].text = str(no)
                row_cells[1].text = item['uraian']
                row_cells[2].text = str(item['volume'])
                row_cells[3].text = item['satuan']
                row_cells[4].text = item['bukti']
                no += 1

    doc.add_paragraph('\n')

    # TANDA TANGAN (Table Borderless)
    sig_table = doc.add_table(rows=1, cols=2)
    sig_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    sig_table.autofit = True
    
    c1 = sig_table.rows[0].cells[0]
    c2 = sig_table.rows[0].cells[1]
    
    # KIRI (DEKAN)
    p = c1.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run(f'Mengetahui,\nDekan FTIK,\n\n\n\n\n{nama_dekan}\nNIP. {nip_dekan}')
    
    # KANAN (DOSEN)
    p = c2.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run(f'Ternate, {datetime.now().strftime("%d-%m-%Y")}\nYang Melaporkan,\n\n\n\n\n{dosen_name}')
    
    # Save to memory
    f = BytesIO()
    doc.save(f)
    f.seek(0)
    return f

# --- MAIN APP ---

url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQinSdwQBQZj649QKRimqqmTFQ0WaSlEHucehHOEg7jvTaioDXe0snCcpo3kTJJsnFrIcqEasjif9E8/pub?output=csv"
df, target_cols = load_data(url)

if 'manual_data' not in st.session_state: st.session_state['manual_data'] = []

st.sidebar.title("Navigasi")
menu = st.sidebar.radio("Pilih Menu:", ["1. Cek Bukti Mahasiswa", "2. Buat LCKB (Dosen)"])

# INPUT DATA PEJABAT (DEKAN) DI SIDEBAR
st.sidebar.divider()
st.sidebar.subheader("Pengaturan Tanda Tangan")
nama_dekan_input = st.sidebar.text_input("Nama Dekan FTIK", value="Dr. H. Sahjad M. Aksan, M.Phil")
nip_dekan_input = st.sidebar.text_input("NIP Dekan", value="19xxxxxxxx")

st.sidebar.divider()

if df is not None:
    if menu == "1. Cek Bukti Mahasiswa":
        st.header("📂 Data Evidence Mahasiswa")
        search = st.text_input("Cari Nama Dosen / Mahasiswa:")
        df_show = df[df.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)] if search else df
        st.dataframe(df_show)

    elif menu == "2. Buat LCKB (Dosen)":
        st.title("📝 Generator LCKB Otomatis")
        
        c1, c2, c3 = st.columns(3)
        selected_dosen = c1.selectbox("Nama Dosen:", DAFTAR_DOSEN_RESMI)
        selected_bulan = c2.selectbox("Bulan:", list(BULAN_INDO.values()), index=datetime.now().month-1)
        selected_tahun = c3.number_input("Tahun:", 2024, 2030, datetime.now().year)
        bulan_angka = list(BULAN_INDO.keys())[list(BULAN_INDO.values()).index(selected_bulan)]
        
        st.divider()

        # 1. OTOMATIS: UJIAN
        mask_dosen = pd.Series(False, index=df.index)
        for col in target_cols:
            mask_dosen |= df[col].apply(normalize_name).str.contains(normalize_name(selected_dosen), na=False)
        mask_waktu = (df['Bulan'] == bulan_angka) & (df['Tahun'] == selected_tahun)
        df_lckb = df[mask_dosen & mask_waktu].copy()
        
        kegiatan_otomatis = []
        if not df_lckb.empty:
            st.success(f"✅ Terdeteksi {len(df_lckb)} kegiatan ujian.")
            for _, row in df_lckb.iterrows():
                ev = parse_evidence(row)
                bukti = ev['ba'][0]['original'] if ev['ba'] else "-"
                kegiatan_otomatis.append({
                    'kategori': 'A',
                    'uraian': f"{row['Pilih Jenis Ujian']} - {row.get('Nama Lengkap Mahasiswa','-')}",
                    'volume': 1, 'satuan': 'Mhs', 'bukti': bukti
                })
        else:
            st.info("Belum ada data ujian mahasiswa bulan ini.")

        # 2. INPUT MANUAL (Gabungan A/B/C/D)
        with st.expander("➕ Tambah Kegiatan Manual (Mengajar/Penelitian/Dll)", expanded=True):
            with st.form("form_manual"):
                c_m1, c_m2 = st.columns([1, 2])
                kat = c_m1.selectbox("Kategori", list(KATEGORI_LABEL.keys()), format_func=lambda x: KATEGORI_LABEL[x])
                ur = c_m2.text_input("Uraian Kegiatan", placeholder="Contoh: Mengajar Mata Kuliah PAI (2 SKS)")
                
                c_m3, c_m4, c_m5 = st.columns(3)
                vol = c_m3.number_input("Volume", 1, 100, 1)
                sat = c_m4.text_input("Satuan", "Kegiatan/SKS")
                buk = c_m5.text_input("Link Bukti / Upload nanti")

                # Upload opsional
                uploaded_file = st.file_uploader("Upload Bukti (Opsional - Perlu API Key)")
                
                if st.form_submit_button("Simpan"):
                    final_link = buk
                    if uploaded_file:
                        link_drive = upload_to_drive(uploaded_file, f"{selected_dosen}_{ur[:5]}.pdf")
                        if link_drive: final_link = link_drive
                    
                    st.session_state['manual_data'].append({
                        'kategori': kat, 'uraian': ur, 'volume': vol, 'satuan': sat, 'bukti': final_link
                    })
                    st.rerun()

        # Preview
        if st.session_state['manual_data']:
            st.write("📋 **Draft Tambahan:**")
            st.table(pd.DataFrame(st.session_state['manual_data']))
            if st.button("Hapus Draft"):
                st.session_state['manual_data'] = []
                st.rerun()
        
        st.divider()
        
        # 3. AREA DOWNLOAD
        st.subheader("🖨️ Cetak Laporan")
        all_data = kegiatan_otomatis + st.session_state['manual_data']
        
        if all_data:
            col_pdf, col_docx = st.columns(2)
            
            # DOWNLOAD PDF
            with col_pdf:
                pdf_bytes = create_lckb_pdf_bytes(all_data, selected_dosen, selected_bulan, selected_tahun, nama_dekan_input, nip_dekan_input)
                b64_pdf = base64.b64encode(pdf_bytes).decode()
                fname_pdf = f"LCKB_{selected_dosen.split()[0]}_{selected_bulan}.pdf"
                href_pdf = f'<a href="data:application/pdf;base64,{b64_pdf}" download="{fname_pdf}" style="background-color: #dc3545; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display:block; text-align:center;">📄 Download PDF (Siap Cetak)</a>'
                st.markdown(href_pdf, unsafe_allow_html=True)
            
            # DOWNLOAD DOCX
            with col_docx:
                docx_file = create_lckb_docx_bytes(all_data, selected_dosen, selected_bulan, selected_tahun, nama_dekan_input, nip_dekan_input)
                st.download_button(
                    label="📝 Download Word (Bisa Edit)",
                    data=docx_file,
                    file_name=f"LCKB_{selected_dosen.split()[0]}_{selected_bulan}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True
                )
        else:
            st.warning("Data kosong, silakan input kegiatan dulu.")
else:
    st.warning("Sedang memuat data...")