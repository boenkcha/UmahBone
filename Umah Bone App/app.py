from models import RestoDB
from flask import Flask, request, render_template, flash, redirect, url_for, jsonify, send_file
from datetime import datetime
import sqlite3
import math
from io import TextIOWrapper
import csv
import json
import pandas as pd
import io
import difflib
import re
from collections import defaultdict

app = Flask(__name__)
app.secret_key = 'secret'
db = RestoDB()

@app.route('/')
def index():
    daftar_menu = db.ambil_menu()
    daftar_bahan = db.ambil_bahan()
    return render_template('index.html', daftar_menu=daftar_menu, daftar_bahan=daftar_bahan)

@app.route('/tambah_bahan', methods=['POST'])
def tambah_bahan():
    nama = request.form['nama'].strip()
    satuan = request.form['satuan'].strip()
    if not nama or not satuan:
        flash("Semua kolom bahan harus diisi", "danger")
        return redirect(url_for('index'))

    try:
        db.tambah_bahan(nama, satuan)
        flash("Bahan berhasil ditambahkan", "success")
    except Exception as e:
        flash(f"Gagal menambah bahan: {e}", "danger")
    return redirect(url_for('index'))

@app.route('/tambah_menu', methods=['POST'])
def tambah_menu():
    nama = request.form['nama'].strip()
    harga = request.form['harga'].strip()
    if not nama or not harga.isdigit():
        flash("Nama dan harga harus diisi dengan benar", "danger")
        return redirect(url_for('index'))

    try:
        db.tambah_menu(nama, int(harga))
        flash("Menu berhasil ditambahkan", "success")
    except Exception as e:
        flash(f"Error saat menambah menu: {e}", "danger")
    return redirect(url_for('index'))

@app.route('/resep/<nama_menu>', methods=['GET', 'POST'])
def kelola_resep(nama_menu):
    if request.method == 'POST':
        nm_menu = request.form['nm_menu']
        nm_bahan = request.form['nm_bahan']
        qty = float(request.form['qty'])
        satuan_pakai = request.form['satuan_pakai']
        konversi = float(request.form['konversi'])
        porsi = int(request.form['porsi'])

        semua_bahan = db.ambil_semua_bahan()
        satuan_stok = next((b[1] for b in semua_bahan if b[0] == nm_bahan), None)

        try:
            db.tambah_resep(nm_menu, nm_bahan, qty, satuan_pakai, konversi, satuan_stok)
            db.set_porsi(nm_menu, porsi)
            flash("Berhasil menambah resep dan memperbarui porsi", "success")
        except Exception as e:
            print("Error:", e)
            flash(f"Gagal menambahkan resep: {str(e)}", "danger")
        
        return redirect(url_for('kelola_resep', nama_menu=nm_menu))

    semua_menu = db.ambil_semua_menu_dari_resep()
    semua_bahan = db.ambil_semua_bahan()
    resep = db.ambil_resep_per_menu(nama_menu)
    porsi = db.get_porsi(nama_menu)
    return render_template(
        'resep.html',
        nama_menu=nama_menu,
        semua_bahan=semua_bahan,
        semua_menu=semua_menu,
        resep=resep,
        selected_menu=nama_menu,
        porsi=porsi
    )

@app.route('/jual_menu', methods=['POST'])
def jual_menu():
    nama = request.form['menu'].strip()
    jumlah = request.form['jumlah'].strip()
    if not nama or not jumlah.isdigit() or int(jumlah) <= 0:
        flash("Jumlah harus angka positif", "danger")
        return redirect(url_for('index'))

    jumlah = int(jumlah)
    if db.jual_menu(nama, jumlah):
        flash(f"Berhasil menjual {jumlah} porsi {nama}", "success")
    else:
        flash(f"Stok tidak cukup untuk {nama}", "danger")
    return redirect(url_for('index'))

@app.route("/stok")
def stok():
    page = int(request.args.get('page', 1))
    per_page = 10
    offset = (page - 1) * per_page
    q = request.args.get('q', '').strip()

    # Ambil data stok berdasarkan alias
    stok_list = db.get_stok_list_with_alias(limit=per_page, offset=offset, search_query=q)
    total_data = db.count_stok_with_alias(search_query=q)
    total_pages = math.ceil(total_data / per_page)

    # Cek kemiripan nama (berbasis nama yang sudah distandarkan)
    import difflib
    def normalisasi_nama(nama):
        nama = nama.lower()
        nama = nama.replace(",", ".")
        nama = re.sub(r"\(.*?\)", "", nama)
        nama = re.sub(r"[\d]+(?:\.\d+)?", "", nama)
        nama = re.sub(r"[^a-z\s]", "", nama)
        return re.sub(r"\s+", " ", nama).strip()

    nama_list = [normalisasi_nama(row['nama']) for row in stok_list]
    mirip_index = set()

    for i in range(len(nama_list)):
        for j in range(i + 1, len(nama_list)):
            ratio = difflib.SequenceMatcher(None, nama_list[i], nama_list[j]).ratio()
            if ratio >= 0.95:
                mirip_index.add(i)
                mirip_index.add(j)

    # Tambahkan flag is_mirip ke stok_list
    stok_list_mirip = []
    for idx, row in enumerate(stok_list):
        is_mirip = idx in mirip_index
        stok_list_mirip.append((
            row['nama'],
            row['jumlah'],
            row['satuan'],
            row['harga'],
            is_mirip
        ))

    return render_template(
        "stok.html",
        stok_list=stok_list_mirip,
        page=page,
        total_pages=total_pages,
        q=q
    )


@app.route('/resep', methods=['GET', 'POST'])
def resep():
    semua_menu = db.get_menu()
    semua_bahan = db.get_bahan()

    if request.method == 'POST':
        nm_menu = request.form['nm_menu']
        nm_bahan = request.form['nm_bahan']
        qty = float(request.form['qty'])
        satuan_pakai = request.form['satuan_pakai']
        konversi = float(request.form['konversi'])

        # Ambil satuan stok dari database, bukan dari form
        satuan_stok = next((b[1] for b in semua_bahan if b[0] == nm_bahan), None)

        if satuan_stok is None:
            flash('Satuan stok tidak ditemukan untuk bahan ini.', 'danger')
        else:
            try:
                db.tambah_resep(nm_menu, nm_bahan, qty, satuan_pakai, konversi, satuan_stok)
                flash('Resep berhasil ditambahkan.', 'success')
                return redirect(url_for('resep', menu=nm_menu))
            except Exception as e:
                flash(f'Gagal menambahkan resep: {e}', 'danger')

    # ✅ Ambil menu yang sedang dipilih (GET atau dari POST fallback)
    selected_menu = request.args.get('menu') or request.form.get('nm_menu')
    daftar_resep = db.ambil_resep_per_menu(selected_menu) if selected_menu else []
    konversi_list = db.get_konversi_data()
    porsi = db.get_porsi(selected_menu) if selected_menu else ''

    return render_template('resep.html',
        semua_menu=semua_menu,
        semua_bahan=semua_bahan,
        selected_menu=selected_menu,
        daftar_resep=daftar_resep,
        nama_menu=selected_menu,
        konversi_list=konversi_list,
        porsi=porsi  # ✅ penting: jangan lupa koma di sini
    )

@app.route('/hapus_bahan_resep', methods=['POST'])
def hapus_bahan_resep():
    nm_menu = request.form['nm_menu']
    nm_bahan = request.form['nm_bahan']
    try:
        db.hapus_bahan_dari_resep(nm_menu, nm_bahan)
        flash(f"Bahan '{nm_bahan}' berhasil dihapus dari resep '{nm_menu}'", "success")
    except Exception as e:
        flash(f"Gagal menghapus bahan: {str(e)}", "danger")
    return redirect(url_for('kelola_resep', nama_menu=nm_menu))

@app.route('/buat_paket', methods=['POST'])
def buat_paket():
    nm_paket = request.form['nm_paket']
    deskripsi = request.form.get('deskripsi', '')  # optional
    harga = float(request.form['harga'])
    jumlah_porsi = int(request.form['jumlah_porsi'])
    try:
        db.cursor.execute(
            "INSERT INTO Paket (nm_paket, deskripsi, harga, jumlah_porsi) VALUES (?, ?, ?, ?)",
            (nm_paket, deskripsi, harga, jumlah_porsi)
        )
        db.conn.commit()
        flash("Paket berhasil dibuat", "success")
    except Exception as e:
        flash(f"Gagal membuat paket: {e}", "danger")

    return redirect(url_for('kelola_paket'))

@app.route('/tambah_menu_ke_paket', methods=['POST'])
def tambah_menu_ke_paket():
    nm_paket = request.form['nm_paket']
    nm_menu = request.form['nm_menu']
    jumlah = int(request.form['jumlah'])  # Jumlah dimasukkan manual

    conn = db.conn
    cur = conn.cursor()

    # Validasi keberadaan paket dan menu
    cur.execute("SELECT 1 FROM Paket WHERE nm_paket = ?", (nm_paket,))
    if not cur.fetchone():
        flash("Paket tidak ditemukan", "danger")
        return redirect(url_for('kelola_paket'))

    cur.execute("SELECT 1 FROM Menu WHERE nm_menu = ?", (nm_menu,))
    if not cur.fetchone():
        flash("Menu tidak ditemukan", "danger")
        return redirect(url_for('kelola_paket'))

    # Tambahkan ke PaketDetail
    cur.execute('''
        INSERT INTO PaketDetail (nm_paket, nm_menu, jumlah)
        VALUES (?, ?, ?)
    ''', (nm_paket, nm_menu, jumlah))

    # Ambil resep bahan dari menu
    cur.execute('''
        SELECT Nm_bahan, Qty, Satuan_pakai, Konversi, Satuan_stok
        FROM Resep
        WHERE Nm_menu = ?
    ''', (nm_menu,))
    bahan_resep = cur.fetchall()

    kebutuhan_bahan = []
    for bahan in bahan_resep:
        nm_bahan, qty, satuan_pakai, konversi, satuan_stok = bahan
        total_qty = qty * jumlah
        total_stok = total_qty * konversi
        kebutuhan_bahan.append((nm_bahan, total_qty, satuan_pakai, total_stok, satuan_stok))

    # (Opsional) Tampilkan kebutuhan bahan
    for b in kebutuhan_bahan:
        print(f"Bahan: {b[0]}, Qty: {b[1]} {b[2]} → {b[3]} {b[4]}")

    conn.commit()
    flash(f"Menu '{nm_menu}' ditambahkan ke paket '{nm_paket}' sebanyak {jumlah}x. Bahan dihitung otomatis.", "success")
    return redirect(url_for('kelola_paket'))


@app.route('/kelola_paket')
def kelola_paket():
    # Ambil data paket dan detail paket
    db.cursor.execute("SELECT nm_paket, deskripsi, harga, jumlah_porsi FROM Paket")
    daftar_paket = db.cursor.fetchall()

    db.cursor.execute("SELECT nm_paket, nm_menu, jumlah FROM PaketDetail")
    detail_paket = db.cursor.fetchall()

    # Ambil semua menu untuk dropdown
    db.cursor.execute("SELECT nm_menu FROM Menu")
    semua_menu = db.cursor.fetchall()

    return render_template(
        'paket.html',
        daftar_paket=daftar_paket,
        detail_paket=detail_paket,
        semua_menu=semua_menu
    )

@app.route('/hapus_menu_dari_paket', methods=['POST'])
def hapus_menu_dari_paket():
    nm_paket = request.form['nm_paket']
    nm_menu = request.form['nm_menu']

    try:
        db.cursor.execute(
            "DELETE FROM PaketDetail WHERE nm_paket = ? AND nama_menu = ?",
            (nm_paket, nm_menu)
        )
        db.conn.commit()
        flash("Menu berhasil dihapus dari paket.", "success")
    except Exception as e:
        flash(f"Gagal menghapus menu dari paket: {str(e)}", "danger")

    return redirect(url_for('kelola_paket'))


@app.route('/proses_penjualan', methods=['POST'])
def proses_penjualan():
    nm_paket = request.form['nm_paket']
    jumlah = int(request.form['jumlah'])

    # Ambil harga dari database
    db.cursor.execute("SELECT harga FROM Paket WHERE nm_paket = ?", (nm_paket,))
    result = db.cursor.fetchone()
    if not result:
        flash("Paket tidak ditemukan", "danger")
        return redirect(url_for('form_penjualan'))

    harga = result[0]
    total = harga * jumlah
    tanggal = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Simpan ke tabel transaksi
    db.cursor.execute("""
        INSERT INTO Transaksi (tanggal, nm_paket, jumlah, harga_satuan, total)
        VALUES (?, ?, ?, ?, ?)
    """, (tanggal, nm_paket, jumlah, harga, total))
    db.conn.commit()

    flash("Penjualan berhasil dicatat", "success")
    return redirect(url_for('form_penjualan'))

@app.route('/hapus_menu/<nama_menu>')
def hapus_menu(nama_menu):
    db.hapus_menu(nama_menu)
    flash(f'Menu {nama_menu} berhasil dihapus.', 'success')
    return redirect(url_for('index'))

@app.route('/simpan_porsi', methods=['POST'])
def simpan_porsi():
    nm_menu = request.form['nm_menu']
    porsi = request.form.get('porsi')

    try:
        porsi_int = int(porsi)
        db.cursor.execute("UPDATE Menu SET porsi = ? WHERE nama_menu = ?", (porsi_int, nm_menu))
        db.conn.commit()
        flash('Jumlah porsi berhasil disimpan.', 'success')
    except Exception as e:
        flash(f'Gagal menyimpan porsi: {e}', 'danger')

    return redirect(url_for('resep', menu=nm_menu))

@app.route('/transaksi', methods=['GET', 'POST'])
def transaksi():
    if request.method == 'POST':
        no_nota = request.form['no_nota']
        konsumen = request.form.get('konsumen', '')
        tanggal = request.form['tanggal']
        jenis_pembayaran = request.form['jenis_pembayaran']
        items = request.form.getlist('item[]')  # format: nama|jenis
        jumlahs = request.form.getlist('jumlah[]')
        hargas = request.form.getlist('harga[]')  # harga total per item

        try:
            # MULAI transaksi database manual
            db.cursor.execute("BEGIN")

            # Simpan header transaksi
            db.insert_transaksi(no_nota, konsumen, tanggal, jenis_pembayaran)

            # Simpan detail transaksi
            for i, item_str in enumerate(items):
                nama, jenis = item_str.split('|')
                jumlah = int(jumlahs[i])
                harga_satuan = float(hargas[i]) / jumlah
                db.insert_transaksi_detail(no_nota, jenis, nama, jumlah, harga_satuan)

            # Hitung kebutuhan dan update stok (bisa raise exception jika stok tidak cukup)
            db.hitung_simpan_kebutuhan_bahan(no_nota)

            # Kalau semua berhasil → COMMIT
            db.conn.commit()
            flash('Transaksi berhasil disimpan!', 'success')
            return redirect(url_for('transaksi'))

        except Exception as e:
            # Kalau gagal → ROLLBACK semua
            db.conn.rollback()
            flash(f'Transaksi gagal: {e}', 'danger')
            return redirect(url_for('transaksi'))

    daftar_menu = db.get_daftar_menu()
    daftar_paket = db.get_daftar_paket()
    return render_template('transaksi.html', daftar_menu=daftar_menu, daftar_paket=daftar_paket)

@app.route('/preview_kebutuhan', methods=['POST'])
def preview_kebutuhan():
    data = request.get_json()
    items = data.get('items', [])  # [{'nama': 'Nasi Goreng', 'jenis': 'menu', 'jumlah': 2}, ...]

    kebutuhan = {}
    for item in items:
        nama = item['nama']
        jenis = item['jenis']
        jumlah = int(item['jumlah'])

        if jenis == 'menu':
            resep = db.get_resep_menu(nama)  # (Nm_bahan, Qty, Konversi, Satuan_pakai)
            for bahan, qty, konversi, satuan in resep:
                total = qty * jumlah #* konversi
                if bahan in kebutuhan:
                    kebutuhan[bahan]['jumlah'] += total
                else:
                    kebutuhan[bahan] = {'jumlah': total, 'satuan': satuan}

        elif jenis == 'paket':
            daftar_menu = db.get_menu_dalam_paket(nama)  # (nm_menu, jumlah)
            for nm_menu, jml_menu in daftar_menu:
                resep = db.get_resep_menu(nm_menu)
                for bahan, qty, konversi, satuan in resep:
                    total = qty * jumlah * jml_menu #* konversi
                    if bahan in kebutuhan:
                        kebutuhan[bahan]['jumlah'] += total
                    else:
                        kebutuhan[bahan] = {'jumlah': total, 'satuan': satuan}

    # Format hasil untuk dikirim ke frontend
    result = [
        {'bahan': b, 'jumlah': round(v['jumlah'], 2), 'satuan': v['satuan']}
        for b, v in kebutuhan.items()
    ]
    return jsonify(result)

@app.route('/import_lengkap', methods=['POST'])
def import_menu_resep_lengkap():
    file = request.files.get('file')
    if not file:
        flash('File tidak ditemukan.', 'danger')
        return redirect(url_for('index'))

    csv_file = TextIOWrapper(file, encoding='utf-8-sig')
    reader = list(csv.DictReader(csv_file))

    if not reader:
        flash('File CSV kosong.', 'danger')
        return redirect(url_for('index'))

    # Pastikan header strip semua nama kolom
    reader_fieldnames = [f.strip() for f in reader[0].keys()]
    required_fields = {'nm_menu', 'harga', 'porsi', 'nm_bahan', 'qty', 'satuan_pakai', 'konversi'}
    if not required_fields.issubset(set(reader_fieldnames)):
        missing = required_fields - set(reader_fieldnames)
        flash(f"Header CSV tidak lengkap. Kolom berikut hilang: {', '.join(missing)}", 'danger')
        return redirect(url_for('index'))

    # Ambil bahan dari CSV (strip dan lowercase)
    bahan_csv = {row['nm_bahan'].strip().lower() for row in reader}

    # Ambil bahan dari database
    bahan_db = {row[0].strip().lower() for row in db.cursor.execute("SELECT Nm_bahan FROM Bahan").fetchall()}
    bahan_tidak_ditemukan = bahan_csv - bahan_db
    if bahan_tidak_ditemukan:
        flash(f"Import dibatalkan. Bahan tidak ditemukan: {', '.join(bahan_tidak_ditemukan)}", 'danger')
        return redirect(url_for('index'))

    menu_sudah_ditambah = set()

    try:
        db.conn.execute('BEGIN')

        for row in reader:
            nm_menu = row['nm_menu'].strip()
            harga = float(row['harga'])
            porsi = int(row['porsi'])
            nm_bahan = row['nm_bahan'].strip()
            qty = float(row['qty'])
            satuan_pakai = row['satuan_pakai'].strip()
            konversi = float(row.get('konversi', '1.0') or 1.0)

            db.cursor.execute("SELECT Satuan FROM Bahan WHERE LOWER(TRIM(Nm_bahan)) = ?", (nm_bahan.lower(),))
            satuan_stok_result = db.cursor.fetchone()
            if not satuan_stok_result:
                raise Exception(f"Bahan '{nm_bahan}' tidak ditemukan di database.")
            satuan_stok = satuan_stok_result[0]

            if nm_menu not in menu_sudah_ditambah:
                db.cursor.execute(
                    "INSERT OR IGNORE INTO Menu (nm_menu, harga, porsi) VALUES (?, ?, ?)",
                    (nm_menu, harga, porsi)
                )
                menu_sudah_ditambah.add(nm_menu)

            db.cursor.execute(
                "INSERT INTO Resep (Nm_menu, Nm_bahan, Qty, Satuan_pakai, Konversi, Satuan_stok) VALUES (?, ?, ?, ?, ?, ?)",
                (nm_menu, nm_bahan, qty, satuan_pakai, konversi, satuan_stok)
            )

        db.conn.commit()
        flash('Import menu dan resep lengkap berhasil.', 'success')

    except Exception as e:
        db.conn.rollback()
        flash(f"Gagal mengimpor data. Error: {e}", 'danger')

    return redirect(url_for('index'))

@app.route('/preview_import', methods=['POST'])
def preview_import():
    print("=== ROUTE preview_import DIJALANKAN ===")  # <-- debug
    file = request.files.get('file')
    if not file:
        flash("File tidak ditemukan.", "danger")
        return redirect(url_for('index'))

    csv_file = TextIOWrapper(file, encoding='utf-8-sig')  # penting: utf-8-sig untuk file dari Excel/Windows
    reader = csv.DictReader(csv_file)
    print("Header CSV yang terbaca:", reader.fieldnames)

    # Pastikan header strip semua nama kolom
    reader.fieldnames = [f.strip() for f in reader.fieldnames]

    required_fields = {'nm_menu', 'harga', 'porsi', 'nm_bahan', 'qty', 'satuan_pakai'}
    if not required_fields.issubset(reader.fieldnames):
        missing = required_fields - set(reader.fieldnames)
   #     flash(f"Header CSV tidak lengkap. Kolom berikut hilang: {', '.join(missing)}", "danger")
        return redirect(url_for('index'))

    preview_data = []
    bahan_tidak_ditemukan = set()
    daftar_bahan = {row[0] for row in db.cursor.execute("SELECT Nm_bahan FROM Bahan").fetchall()}

    for row in reader:
        nm_bahan = row['nm_bahan'].strip()
        row['bahan_tersedia'] = nm_bahan in daftar_bahan
        if not row['bahan_tersedia']:
            bahan_tidak_ditemukan.add(nm_bahan)
        preview_data.append(row)

    try:
        return render_template('preview_import.html',
                            data=preview_data,
                            bahan_tidak_ditemukan=bahan_tidak_ditemukan)
    except Exception as e:
        return f"Gagal render preview: {e}"

@app.route('/cari_transaksi', methods=['GET', 'POST'])
def cari_transaksi():
    transaksi = None
    hasil = []
    kebutuhan = []
    transaksi_list = []
    no_nota = ''
    tanggal_awal = ''
    tanggal_akhir = ''
    total_detail = 0
    total_kebutuhan = 0
    isi_paket = {}

    if request.method == 'POST':
        no_nota = request.form.get('no_nota', '').strip()
        tanggal_awal = request.form.get('tanggal_awal', '')
        tanggal_akhir = request.form.get('tanggal_akhir', '')

        if no_nota:
            transaksi = db.get_transaksi_by_nota(no_nota)
            hasil = db.get_transaksi_detail(no_nota)
            kebutuhan = db.get_kebutuhan_bahan(no_nota)
        elif tanggal_awal and tanggal_akhir:
            transaksi_list = db.get_transaksi_by_tanggal(tanggal_awal, tanggal_akhir)

        total_detail = 0
        if hasil:
            for item in hasil:
                if len(item) >= 4:
                    total_detail += item[3] * item[2]  # harga * jumlah

        total_kebutuhan = 0
        if kebutuhan:
            total_kebutuhan = sum(item[4] for item in kebutuhan if len(item) >= 5)




        isi_paket = {}
        for jenis, nama, jumlah, harga in hasil:
            if jenis == 'paket':
                isi_paket[nama] = db.get_menu_dalam_paket(nama)

    return render_template('cari_transaksi.html',
                           transaksi=transaksi,
                           hasil=hasil,
                           kebutuhan=kebutuhan,
                           transaksi_list=transaksi_list,
                           no_nota=no_nota,
                           tanggal_awal=tanggal_awal,
                           tanggal_akhir=tanggal_akhir,
                           total_detail=total_detail,
                           total_kebutuhan=total_kebutuhan,
                           isi_paket=isi_paket)
#oba
@app.route('/pembelian', methods=['GET', 'POST'])
def pembelian():
    daftar_bahan = db.get_daftar_bahan()
    data_pembelian = []
    mode = 'form'  # default tampilan

    if request.method == 'POST':
        no_nota = request.form['no_nota']
        tanggal = request.form['tanggal']
        supplier = request.form['nama_supplier']
        status = request.form['status_pembayaran']
        nm_bahan = request.form.getlist('nm_bahan[]')
        jumlah = request.form.getlist('jumlah[]')
        satuan = request.form.getlist('satuan[]')
        harga = request.form.getlist('harga[]')

        try:
            db.insert_pembelian(no_nota, tanggal, supplier, status)
            for i in range(len(nm_bahan)):
                jml = float(jumlah[i])
                hrg = float(harga[i])
                db.insert_pembelian_detail(no_nota, nm_bahan[i], jumlah[i], satuan[i], harga[i])
                db.update_stok_setelah_pembelian(nm_bahan[i], jml, satuan[i], hrg)

            data_pembelian = db.get_pembelian_by_nota(no_nota)
            flash('Data pembelian berhasil disimpan', 'success')
            mode = 'result'

        except ValueError as ve:
            flash(str(ve), 'danger')
        except Exception as e:
            flash('Terjadi kesalahan saat menyimpan data pembelian.', 'danger')

    elif request.method == 'GET' and 'no_nota' in request.args:
        no_nota = request.args.get('no_nota')
        data_pembelian = db.get_pembelian_by_nota(no_nota)
        if data_pembelian:
            flash(f'Data pembelian untuk No Nota: {no_nota}', 'info')
            mode = 'result'
        else:
            flash(f'Tidak ditemukan data pembelian untuk No Nota: {no_nota}', 'warning')

    return render_template('pembelian.html',
                           daftar_bahan=daftar_bahan,
                           daftar_pembelian=data_pembelian,
                           mode=mode)

@app.route('/pembelian/edit', methods=['GET', 'POST'])
def edit_pembelian():
    no_nota = request.args.get('no_nota') or request.form.get('no_nota')
    if not no_nota:
        flash('No Nota tidak ditemukan', 'danger')
        return redirect(url_for('pembelian'))

    daftar_bahan = db.get_daftar_bahan()

    if request.method == 'POST':
        tanggal = request.form['tanggal']
        supplier = request.form['nama_supplier']
        status = request.form['status_pembayaran']
        nm_bahan = request.form.getlist('nm_bahan[]')
        jumlah = request.form.getlist('jumlah[]')
        satuan = request.form.getlist('satuan[]')
        harga = request.form.getlist('harga[]')

        # Update header pembelian
        db.update_pembelian(no_nota, tanggal, supplier, status)

        # Ambil data pembelian lama untuk rollback stok
        pembelian_lama = db.get_pembelian_by_nota(no_nota)

        # Kembalikan stok bahan dari pembelian lama (kurangi stok pembelian lama)
        for row in pembelian_lama:
            nm_bhn_lama = row[4]
            jml_lama = float(row[5])
            satuan_lama = row[6]
            hrg_lama = float(row[7])
            db.update_stok_setelah_pembelian(nm_bhn_lama, -jml_lama, satuan_lama, -hrg_lama)

        # Hapus detail pembelian lama
        db.delete_pembelian_detail(no_nota)

        # Masukkan detail pembelian baru dan update stok
        for i in range(len(nm_bahan)):
            jml = float(jumlah[i])
            hrg = float(harga[i])
            db.insert_pembelian_detail(no_nota, nm_bahan[i], jumlah[i], satuan[i], harga[i])
            db.update_stok_setelah_pembelian(nm_bahan[i], jml, satuan[i], hrg)

        flash('Data pembelian berhasil diperbarui', 'success')
        return redirect(url_for('pembelian', no_nota=no_nota))

    else:
        # GET: tampilkan form edit dengan data lama
        data_pembelian = db.get_pembelian_by_nota(no_nota)
        if not data_pembelian:
            flash(f'Tidak ditemukan data pembelian untuk No Nota: {no_nota}', 'warning')
            return redirect(url_for('pembelian'))

        # Data header pembelian untuk isi form
        header = {
            'no_nota': data_pembelian[0][0],
            'tanggal': data_pembelian[0][1],
            'nama_supplier': data_pembelian[0][2],
            'status_pembayaran': data_pembelian[0][3],
        }

        return render_template('edit_pembelian.html',
                               header=header,
                               detail=data_pembelian,
                               daftar_bahan=daftar_bahan)


@app.route('/pembelian/import', methods=['GET', 'POST'])
def import_pembelian():
    if request.method == 'POST':
        file = request.files.get('file_csv')  # disesuaikan dengan input HTML kamu
        if not file:
            flash('File CSV tidak ditemukan', 'danger')
            return redirect(request.url)
        try:
            db.import_pembelian_csv(file)
            flash('Data pembelian berhasil diimpor', 'success')
        except Exception as e:
            flash(f'Gagal import CSV: {str(e)}', 'danger')
        return redirect(url_for('pembelian'))

    # HANYA untuk GET
    return render_template("import_pembelian.html")

@app.route('/cari_pembelian', methods=['GET', 'POST'])
def cari_pembelian():
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')

    if start_date and end_date:
        pembelian = db.eksekusi_select("""
            SELECT * FROM Pembelian WHERE DATE(tanggal) BETWEEN DATE(?) AND DATE(?) ORDER BY tanggal DESC
        """, (start_date, end_date))
    else:
        pembelian = db.eksekusi_select("SELECT * FROM Pembelian ORDER BY tanggal DESC")

    return render_template("cari_pembelian.html", data=pembelian, start_date=start_date, end_date=end_date)

@app.route('/rincian_pembelian/<no_nota>')
def rincian_pembelian(no_nota):
    hasil = db.eksekusi_select("""
        SELECT nm_bahan, jumlah, satuan, harga FROM PembelianDetail WHERE no_nota = ?
    """, (no_nota,))
    return jsonify(hasil)



@app.route('/get_satuan', methods=['GET'])
def get_satuan():
    nama_bahan = request.args.get('nama_bahan')
    satuan = db.get_satuan_bahan(nama_bahan)
    return jsonify({'satuan': satuan})

@app.route('/laporan/kartu-stok')
def laporan_kartu_stok():
    start = request.args.get('start')
    end = request.args.get('end')
    html_table = db.render_html_kartu_stok(start, end)
    return render_template('kartu_stok.html', table=html_table, start=start, end=end)


@app.route('/laporan/kartu-stok/export')
def export_kartu_stok_excel():
    output = db.export_kartu_stok_excel_buffer()
    if output is None:
        return "Tidak ada data untuk diekspor.", 404

    return send_file(
        output,
        as_attachment=True,
        download_name="kartu_stok.xlsx",
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@app.route("/infostok/<nm_bahan>")
def infostok(nm_bahan):
    info_data = db.get_info_stok(nm_bahan)
    return render_template("info_stok.html",
        nm_bahan=nm_bahan,
        info_by_satuan=info_data["records_by_satuan"],
        alias_list=info_data["alias_list"],
        satuan_stok=info_data["satuan_stok"]
    )



@app.route('/import_menu', methods=['POST'])
def import_menu():
    print("📥 Route import_menu dijalankan")

    file = request.files.get('file')
    if not file:
        flash('File tidak ditemukan', 'danger')
        return redirect(url_for('home'))

    stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
    reader = csv.reader(stream)
    next(reader, None)
    for row in reader:
        if len(row) < 8:
            continue
        nm_menu = row[0]
        harga = int(row[6])
        porsi = int(row[7])

        try:
            db.cursor.execute("INSERT INTO Menu (Nm_menu, Harga, porsi) VALUES (?, ?, ?)", (nm_menu, harga, porsi))
            db.conn.commit()
        except:
            pass  # Menu sudah ada

    flash('Import menu berhasil!', 'success')
    return redirect(url_for('index'))


@app.route('/import_menu_resep_lengkap2', methods=['POST'])
def import_menu_resep_lengkap2():
    print("📥 Route import_menu_resep_lengkap2 dijalankan")
    file = request.files.get('file')
    if not file:
        flash('Tidak ada file yang dipilih.', 'danger')
        return redirect(url_for('index'))

    import csv, io
    stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
    reader = csv.reader(stream)

    next(reader, None)  # Lewati header

    total_menu_baru = 0
    total_menu_duplikat = 0
    total_resep_baru = 0
    total_resep_duplikat = 0

    for row in reader:
        if len(row) < 8:
            print(f"[SKIP] Baris tidak lengkap: {row}")
            continue

        try:
            nm_menu = row[0].strip()
            nm_bahan = row[1].strip()
            qty = float(row[2])
            satuan_pakai = row[3].strip()
            konversi = float(row[4])
            satuan_stok = row[5].strip()
            harga = int(row[6])
            porsi = int(row[7])
        except Exception as e:
            print(f"[ERROR] Gagal parsing baris: {row} => {e}")
            continue

        # Validasi Menu
        db.cursor.execute("SELECT 1 FROM Menu WHERE Nm_menu = ?", (nm_menu,))
        if not db.cursor.fetchone():
            try:
                db.cursor.execute("INSERT INTO Menu (Nm_menu, Harga, porsi) VALUES (?, ?, ?)", (nm_menu, harga, porsi))
                total_menu_baru += 1
                print(f"✅ INSERT Menu: {nm_menu}")
            except Exception as e:
                print(f"❌ Gagal insert menu: {e}")
        else:
            total_menu_duplikat += 1
            print(f"⏩ Skip Menu (duplikat): {nm_menu}")

        # Validasi Resep (menu + bahan tidak boleh duplikat)
        db.cursor.execute("SELECT 1 FROM Resep WHERE nm_menu = ? AND nm_bahan = ?", (nm_menu, nm_bahan))
        if not db.cursor.fetchone():
            try:
                db.cursor.execute("""
                    INSERT INTO Resep (nm_menu, nm_bahan, qty, satuan_pakai, konversi, satuan_stok)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (nm_menu, nm_bahan, qty, satuan_pakai, konversi, satuan_stok))
                total_resep_baru += 1
                print(f"✅ INSERT Resep: {nm_menu} - {nm_bahan}")
            except Exception as e:
                print(f"❌ Gagal insert resep: {e} | Baris: {row}")
        else:
            total_resep_duplikat += 1
            print(f"⏩ Skip Resep (duplikat): {nm_menu} - {nm_bahan}")

    db.conn.commit()

    flash(f"""
        ✅ Import selesai:
        - Menu baru: {total_menu_baru}, duplikat: {total_menu_duplikat}
        - Resep baru: {total_resep_baru}, duplikat: {total_resep_duplikat}
    """, 'success')
    return redirect(url_for('index'))

@app.route('/laporan_kebutuhan', methods=['GET', 'POST'])
def laporan_kebutuhan():
    from collections import defaultdict
    data_grouped = []
    if request.method == 'POST':
        tgl_awal = request.form.get('tgl_awal')
        tgl_akhir = request.form.get('tgl_akhir')
        query = """
            SELECT T.no_nota, T.tanggal, K.nm_paket, K.nm_menu, K.nm_bahan, K.jumlah, K.satuan_pakai, K.harga
            FROM Transaksi T
            JOIN KebutuhanPaket K ON T.no_nota = K.no_nota
            WHERE T.tanggal BETWEEN ? AND ?
            ORDER BY T.tanggal, T.no_nota, K.nm_paket, K.nm_menu, K.nm_bahan
        """
        db.cursor.execute(query, (tgl_awal, tgl_akhir))
        rows = db.cursor.fetchall()

        grouped = defaultdict(list)
        for row in rows:
            key = (row[1], row[0])  # (tanggal, no_nota)
            grouped[key].append(row)

        # Tambahkan grouping internal untuk paket + menu
        for (tanggal, no_nota), items in grouped.items():
            paket_menu_group = defaultdict(list)
            for row in items:
                key = (row[2], row[3])  # (nm_paket, nm_menu)
                paket_menu_group[key].append(row)

            rows_with_span = []
            for (nm_paket, nm_menu), lines in paket_menu_group.items():
                for i, line in enumerate(lines):
                    rows_with_span.append({
                        'row': line,
                        'show_paket_menu': i == 0,
                        'paket_menu_rowspan': len(lines)
                    })

            data_grouped.append({
                'tanggal': tanggal,
                'no_nota': no_nota,
                'rows': rows_with_span
            })

    return render_template('laporan_kebutuhan.html', data_grouped=data_grouped)

@app.route('/cek_list_bahan')
def cek_list_bahan():
    keyword = request.args.get('keyword', '').strip()
    conn = db.conn
    cur = conn.cursor()

    if keyword:
        query = "SELECT * FROM Bahan WHERE Nm_bahan LIKE ? COLLATE NOCASE ORDER BY Nm_bahan COLLATE NOCASE ASC"
        cur.execute(query, (f"%{keyword}%",))
    else:
        query = "SELECT * FROM Bahan ORDER BY Nm_bahan COLLATE NOCASE ASC"
        cur.execute(query)

    daftar_bahan = cur.fetchall()

    # Deteksi kemiripan nama bahan (case-insensitive)
    nama_list = [row[0].strip().lower() for row in daftar_bahan]
    mirip_index = set()

    for i in range(len(nama_list)):
        for j in range(i + 1, len(nama_list)):
            ratio = difflib.SequenceMatcher(None, nama_list[i], nama_list[j]).ratio()
            if ratio >= 0.95:
                mirip_index.add(i)
                mirip_index.add(j)

    # Tandai baris yang mirip
    hasil_bahan = []
    for idx, row in enumerate(daftar_bahan):
        is_mirip = idx in mirip_index
        hasil_bahan.append((row[0], row[1], row[2], is_mirip))

    return render_template('cek_list_bahan.html', daftar_bahan=hasil_bahan)

@app.route('/alias_bahan', methods=['GET', 'POST'])
def alias_bahan():
    if request.method == 'POST':
        nama_lama = request.form['nama_lama'].strip()
        nama_standar = request.form['nama_standar'].strip()

        try:
            conn = db.conn
            cur = conn.cursor()
            cur.execute("REPLACE INTO BahanAlias (nama_lama, nama_standar) VALUES (?, ?)", 
                        (nama_lama, nama_standar))
            conn.commit()
            flash('Alias berhasil disimpan.', 'success')
        except Exception as e:
            flash(f'Gagal menyimpan alias: {e}', 'danger')

        return redirect(url_for('alias_bahan'))

    # Tampilkan daftar alias yang sudah ada
    conn = db.conn
    cur = conn.cursor()
    cur.execute("SELECT * FROM BahanAlias ORDER BY nama_standar ASC")
    data_alias = cur.fetchall()

    return render_template('alias_bahan.html', data_alias=data_alias)

@app.route("/generate_alias_otomatis")
def generate_alias_otomatis():
    db.buat_alias_otomatis()
    flash("Alias otomatis berhasil dibuat dari data pembelian.", "success")
    return redirect(url_for("alias_bahan"))


@app.route('/normalisasi_stok/<nm_bahan>/<satuan>')
def normalisasi_stok(nm_bahan, satuan):
    cursor = db.conn.cursor()

    # Ambil semua data stok matching nama & satuan (case-insensitive)
    rows = cursor.execute("""
        SELECT jumlah, harga_modal FROM Stok
        WHERE LOWER(nm_bahan) = LOWER(?) AND LOWER(satuan) = LOWER(?)
    """, (nm_bahan, satuan)).fetchall()

    if not rows:
        flash("Data tidak ditemukan untuk dinormalisasi.")
        return redirect(url_for('stok'))

    total_jumlah = sum([r[0] for r in rows])
    total_nilai = sum([r[0] * r[1] for r in rows])
    rata_harga = total_nilai / total_jumlah if total_jumlah else 0

    # Hapus stok lama
    cursor.execute("""
        DELETE FROM Stok
        WHERE LOWER(nm_bahan) = LOWER(?) AND LOWER(satuan) = LOWER(?)
    """, (nm_bahan, satuan))

    # Insert 1 baris hasil normalisasi
    cursor.execute("""
        INSERT INTO Stok (nm_bahan, jumlah, satuan, harga_modal)
        VALUES (?, ?, ?, ?)
    """, (nm_bahan.upper(), total_jumlah, satuan.upper(), rata_harga))

    db.conn.commit()
    flash(f"Stok '{nm_bahan}' ({satuan}) berhasil dinormalisasi.")
    return redirect(url_for('stok'))

if __name__ == '__main__':
    app.run(debug=True)
