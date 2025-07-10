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
    daftar_menu = db.ambil_menu()  # [(nm_menu, harga)]
    daftar_bahan = db.ambil_bahan()  # [(nm_bahan, satuan)]

    # Ambil semua pasangan bahan dan satuan dari stok (dalam huruf kecil)
    stok_data = db.ambil_stok_bahan_dan_satuan()  # kamu buat def-nya di bawah
    stok_set = {(bahan.strip().lower(), satuan.strip().lower()) for bahan, satuan in stok_data}

    daftar_menu_dengan_status = []
    for menu in daftar_menu:
        nama_menu = menu[0]
        harga_menu = menu[1]

        resep = db.ambil_resep_per_menu(nama_menu)  # [(nm_bahan, qty, satuan_pakai, konversi, satuan_stok)]

        bahan_hilang = any(
            (r[0].strip().lower(), r[4].strip().lower()) not in stok_set
            for r in resep
        )

        # Simpan tuple dengan status bahan hilang
        daftar_menu_dengan_status.append((nama_menu, harga_menu, bahan_hilang))

    return render_template('index.html', daftar_menu=daftar_menu_dengan_status, daftar_bahan=daftar_bahan)



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
        satuan_stok = request.form['satuan_stok']  # Ambil dari input hidden

        try:
            # 1. Tambah resep
            db.tambah_resep(nm_menu, nm_bahan, qty, satuan_pakai, konversi, satuan_stok)

            # 2. Insert or update konversi_satuan
            db.cursor.execute("""
                SELECT COUNT(*) FROM konversi_satuan
                WHERE nm_bahan = ? AND dari_satuan = ? AND ke_satuan = ?
            """, (nm_bahan, satuan_stok, satuan_pakai))
            exists = db.cursor.fetchone()[0]

            if exists:
                # Update faktor konversi jika data sudah ada
                db.cursor.execute("""
                    UPDATE konversi_satuan
                    SET faktor_konversi = ?
                    WHERE nm_bahan = ? AND dari_satuan = ? AND ke_satuan = ?
                """, (konversi, nm_bahan, satuan_stok, satuan_pakai))
                print(f"🔄 Updated konversi_satuan: {nm_bahan} {satuan_stok}->{satuan_pakai} = {konversi}")
            else:
                # Insert data baru jika belum ada
                db.cursor.execute("""
                    INSERT INTO konversi_satuan (nm_bahan, dari_satuan, ke_satuan, faktor_konversi)
                    VALUES (?, ?, ?, ?)
                """, (nm_bahan, satuan_stok, satuan_pakai, konversi))
                print(f"✅ Inserted konversi_satuan: {nm_bahan} {satuan_stok}->{satuan_pakai} = {konversi}")

            # 3. Set porsi menu
            db.set_porsi(nm_menu, porsi)

            db.conn.commit()
            flash("Berhasil menambah resep, update konversi_satuan, dan memperbarui porsi", "success")
        except Exception as e:
            db.conn.rollback()
            print("Error:", e)
            flash(f"Gagal menambahkan resep: {str(e)}", "danger")
        
        return redirect(url_for('kelola_resep', nama_menu=nm_menu))

    semua_menu = db.ambil_semua_menu_dari_resep()
    semua_bahan = db.ambil_semua_stok()
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
        q=q,
        max=max,  # ← ini penting
        min=min
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
            "DELETE FROM PaketDetail WHERE nm_paket = ? AND nm_menu = ?",
            (nm_paket, nm_menu)
        )
        db.conn.commit()
        flash("Menu berhasil dihapus dari paket.", "success")
    except Exception as e:
        db.conn.rollback()
        flash(f"Gagal menghapus menu dari paket: {str(e)}", "danger")

    return redirect(url_for('kelola_paket'))

@app.route('/hapus_paket/<path:nm_paket>', methods=['GET'])
def hapus_paket(nm_paket):
    try:
        db.cursor.execute("DELETE FROM PaketDetail WHERE nm_paket = ?", (nm_paket,))
        db.cursor.execute("DELETE FROM Paket WHERE nm_paket = ?", (nm_paket,))
        db.conn.commit()
        flash(f"Paket '{nm_paket}' dan semua menu di dalamnya berhasil dihapus.", "success")
    except Exception as e:
        db.conn.rollback()
        flash(f"Gagal menghapus paket '{nm_paket}': {str(e)}", "danger")

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

#GANTI ROOLBACK
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

@app.route('/transaksi/batal/<no_nota>', methods=['GET'])
def batal_transaksi(no_nota):
    try:
        db.cursor.execute("BEGIN")

        # Ambil semua kebutuhan bahan
        db.cursor.execute("""
            SELECT nm_bahan, jumlah, satuan_pakai
            FROM KebutuhanPaket
            WHERE no_nota = ?
        """, (no_nota,))
        kebutuhan_bahan = db.cursor.fetchall()

        for nm_bahan, jumlah_pakai, satuan_pakai in kebutuhan_bahan:
            # Cek jumlah satuan berbeda di stok
            db.cursor.execute("""
                SELECT COUNT(DISTINCT satuan)
                FROM Stok
                WHERE nm_bahan = ?
            """, (nm_bahan,))
            jumlah_satuan = db.cursor.fetchone()[0]

            if jumlah_satuan == 1:
                # Ambil satuan stok yang ada
                db.cursor.execute("""
                    SELECT jumlah, satuan
                    FROM Stok
                    WHERE nm_bahan = ?
                """, (nm_bahan,))
                stok_row = db.cursor.fetchone()
                jumlah_stok, satuan_stok = stok_row

                if satuan_pakai == satuan_stok:
                    # Satuan sama → langsung tambahkan
                    db.cursor.execute("""
                        UPDATE Stok SET jumlah = jumlah + ?
                        WHERE nm_bahan = ? AND satuan = ?
                    """, (jumlah_pakai, nm_bahan, satuan_stok))
                    print(f"✅ Restock {nm_bahan}: +{jumlah_pakai} {satuan_stok}")
                else:
                    # Satuan berbeda → ambil faktor konversi dari Resep
                    db.cursor.execute("""
                        SELECT Konversi
                        FROM Resep
                        WHERE nm_bahan = ? AND Satuan_pakai = ?
                    """, (nm_bahan, satuan_pakai))
                    konversi_row = db.cursor.fetchone()

                    if konversi_row and konversi_row[0]:
                        faktor_konversi = konversi_row[0]
                        jumlah_konversi = jumlah_pakai / faktor_konversi
                        db.cursor.execute("""
                            UPDATE Stok SET jumlah = jumlah + ?
                            WHERE nm_bahan = ? AND satuan = ?
                        """, (jumlah_konversi, nm_bahan, satuan_stok))
                        print(f"✅ Restock {nm_bahan}: +{jumlah_konversi} {satuan_stok} (dikonversi dari {jumlah_pakai} {satuan_pakai})")
                    else:
                        raise Exception(f"Tidak ada konversi di Resep untuk {nm_bahan} dari {satuan_pakai} ke {satuan_stok}")

            else:
                # Jika stok memiliki lebih dari 1 satuan, gunakan konversi_satuan seperti script sebelumnya
                db.cursor.execute("""
                    SELECT s.jumlah, s.satuan, k.faktor_konversi
                    FROM Stok s
                    JOIN konversi_satuan k
                      ON s.nm_bahan = k.nm_bahan AND s.satuan = k.ke_satuan
                    WHERE k.dari_satuan = ? AND s.nm_bahan = ?
                    ORDER BY s.jumlah DESC
                """, (satuan_pakai, nm_bahan))
                rows = db.cursor.fetchall()

                updated = False
                for jumlah_stok, satuan_stok, faktor in rows:
                    jumlah_konversi = jumlah_pakai * faktor
                    db.cursor.execute("""
                        UPDATE Stok SET jumlah = jumlah + ?
                        WHERE nm_bahan = ? AND satuan = ?
                    """, (jumlah_konversi, nm_bahan, satuan_stok))
                    print(f"✅ Restock {nm_bahan}: +{jumlah_konversi} {satuan_stok} (dikonversi dari {jumlah_pakai} {satuan_pakai})")
                    updated = True
                    break

                if not updated:
                    raise Exception(f"Tidak ditemukan stok dengan satuan sama atau konversi untuk {nm_bahan} saat cancel transaksi.")

        # Hapus transaksi, detail, dan kebutuhan bahan
        db.cursor.execute("DELETE FROM TransaksiDetail WHERE no_nota = ?", (no_nota,))
        db.cursor.execute("DELETE FROM KebutuhanPaket WHERE no_nota = ?", (no_nota,))
        db.cursor.execute("DELETE FROM Transaksi WHERE no_nota = ?", (no_nota,))

        db.conn.commit()
        flash(f'Transaksi {no_nota} berhasil dibatalkan dan stok dikembalikan dengan konversi otomatis.', 'success')

    except Exception as e:
        db.conn.rollback()
        flash(f'Gagal membatalkan transaksi: {e}', 'danger')

    return redirect(url_for('transaksi'))

@app.route('/preview_kebutuhan', methods=['POST'])
def preview_kebutuhan():
    data = request.get_json()
    items = data.get('items', [])

    kebutuhan = {}
    for item in items:
        nama = item['nama']
        jenis = item['jenis']
        jumlah = int(item['jumlah'])

        if jenis == 'menu':
            resep = db.get_resep_menu(nama)  # (Nm_bahan, Qty, Konversi, Satuan_pakai)
            for bahan, qty, konversi, satuan in resep:
                total = qty * jumlah
                if bahan in kebutuhan:
                    kebutuhan[bahan]['jumlah'] += total
                else:
                    kebutuhan[bahan] = {'jumlah': total, 'satuan': satuan}

        elif jenis == 'paket':
            daftar_menu = db.get_menu_dalam_paket(nama)
            for nm_menu, jml_menu in daftar_menu:
                resep = db.get_resep_menu(nm_menu)
                for bahan, qty, konversi, satuan in resep:
                    total = qty * jumlah * jml_menu
                    if bahan in kebutuhan:
                        kebutuhan[bahan]['jumlah'] += total
                    else:
                        kebutuhan[bahan] = {'jumlah': total, 'satuan': satuan}

    # Format hasil + cek stok
    result = []
    for b, v in kebutuhan.items():
        jumlah_dibutuhkan = round(v['jumlah'], 2)
        stok = db.cek_stok(b)  # harus kamu buat di class database

        if stok is None:
            status = "tidak_ada"
        elif stok < jumlah_dibutuhkan:
            status = "tidak_cukup"
        else:
            status = "cukup"

        result.append({
            'bahan': b,
            'jumlah': jumlah_dibutuhkan,
            'satuan': v['satuan'],
            'status': status
        })

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
    elif request.method == 'GET' and request.args.get('no_nota'):
        no_nota = request.args.get('no_nota').strip()

    # Cek jika ada no_nota, ambil detail transaksi
    if no_nota:
        transaksi = db.get_transaksi_by_nota(no_nota)
        hasil = db.get_transaksi_detail(no_nota)
        kebutuhan = db.get_kebutuhan_bahan(no_nota)

        if hasil:
            total_detail = sum(item[3] * item[2] for item in hasil if len(item) >= 4)

        if kebutuhan:
            total_kebutuhan = sum(item[4] for item in kebutuhan if len(item) >= 5)

        isi_paket = {}
        for jenis, nama, jumlah, harga in hasil:
            if jenis == 'paket':
                isi_paket[nama] = db.get_menu_dalam_paket(nama)

    elif tanggal_awal and tanggal_akhir:
        transaksi_list = db.get_transaksi_by_tanggal(tanggal_awal, tanggal_akhir)

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
    mode = 'form'

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
                nama = nm_bahan[i]
                sat = satuan[i]
                jml = float(jumlah[i])
                hrg = float(harga[i])

                # Tambahkan ke tabel Bahan jika belum ada kombinasi nama + satuan
                if not db.cek_bahan_ada(nama, sat):
                    db.tambah_bahan(nama, sat, hrg)

                db.insert_pembelian_detail(no_nota, nama, jml, sat, hrg)
                db.update_stok_setelah_pembelian(nama, jml, sat, hrg)

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

        # Ambil data pembelian lama
        pembelian_lama = db.get_pembelian_by_nota(no_nota)

        # Buat dict untuk cek perbedaan
        data_lama = [
            {
                'nm_bahan': row[4],
                'jumlah': float(row[5]),
                'satuan': row[6],
                'harga': float(row[7])
            }
            for row in pembelian_lama
        ]

        data_baru = [
            {
                'nm_bahan': nm_bahan[i],
                'jumlah': float(jumlah[i]),
                'satuan': satuan[i],
                'harga': float(harga[i])
            }
            for i in range(len(nm_bahan))
        ]

        # Jika data lama != data baru → rollback dan update
            # Hapus & rollback hanya baris yang berubah
        for row_lama in data_lama:
            found_match = False
            for row_baru in data_baru:
                if (
                    row_lama['nm_bahan'] == row_baru['nm_bahan'] and
                    row_lama['satuan'] == row_baru['satuan']
                ):
                    # Jika nama dan satuan sama, cek jumlah/harga
                    if (
                        row_lama['jumlah'] != row_baru['jumlah'] or
                        row_lama['harga'] != row_baru['harga']
                    ):
                        # rollback dulu yang lama
                        db.update_stok_setelah_pembelian(
                            row_lama['nm_bahan'],
                            -row_lama['jumlah'],
                            row_lama['satuan'],
                            -row_lama['harga']
                        )
                        # lalu hapus yang lama
                        db.delete_pembelian_detail_bahan(no_nota, row_lama['nm_bahan'], row_lama['satuan'])

                        # dan insert baru
                        db.insert_pembelian_detail(
                            no_nota,
                            row_baru['nm_bahan'],
                            row_baru['jumlah'],
                            row_baru['satuan'],
                            row_baru['harga']
                        )
                        db.update_stok_setelah_pembelian(
                            row_baru['nm_bahan'],
                            row_baru['jumlah'],
                            row_baru['satuan'],
                            row_baru['harga']
                        )
                    found_match = True
                    break

            if not found_match:
                # Data lama dihapus karena tidak ada di data baru
                db.update_stok_setelah_pembelian(
                    row_lama['nm_bahan'],
                    -row_lama['jumlah'],
                    row_lama['satuan'],
                    -row_lama['harga']
                )
                db.delete_pembelian_detail_bahan(no_nota, row_lama['nm_bahan'], row_lama['satuan'])

        # Cek apakah ada bahan baru (tidak ada di data lama)
        for row_baru in data_baru:
            if not any(
                row_baru['nm_bahan'] == row_lama['nm_bahan'] and
                row_baru['satuan'] == row_lama['satuan']
                for row_lama in data_lama
            ):
                db.insert_pembelian_detail(
                    no_nota,
                    row_baru['nm_bahan'],
                    row_baru['jumlah'],
                    row_baru['satuan'],
                    row_baru['harga']
                )
                db.update_stok_setelah_pembelian(
                    row_baru['nm_bahan'],
                    row_baru['jumlah'],
                    row_baru['satuan'],
                    row_baru['harga']
                )


        db.hapus_pembelian_jika_detail_kosong(no_nota)
        flash('Data pembelian berhasil diperbarui', 'success')
        return redirect(url_for('pembelian'))


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
    start_date = request.values.get('start_date')
    end_date = request.values.get('end_date')
    no_nota = request.values.get('no_nota')
    supplier = request.values.get('supplier')


    query = "SELECT * FROM Pembelian WHERE 1=1"
    params = []

    if no_nota:
        query += " AND no_nota LIKE ?"
        params.append(f"%{no_nota}%")

    if supplier:
        query += " AND nama_supplier LIKE ?"
        params.append(f"%{supplier}%")

    if start_date and end_date:
        query += " AND DATE(tanggal) BETWEEN DATE(?) AND DATE(?)"
        params.extend([start_date, end_date])

    query += " ORDER BY tanggal DESC"

    pembelian = db.eksekusi_select(query, tuple(params))

    return render_template("cari_pembelian.html", data=pembelian,
                           start_date=start_date, end_date=end_date,
                           no_nota=no_nota, supplier=supplier)



@app.route('/rincian_pembelian/<no_nota>')
def rincian_pembelian(no_nota):
    hasil = db.eksekusi_select("""
        SELECT nm_bahan, jumlah, satuan, harga FROM PembelianDetail WHERE no_nota = ?
    """, (no_nota,))
    return jsonify(hasil)

@app.route('/tautkan_bahan_resep', methods=['POST'])
def tautkan_bahan_resep():
    nm_menu = request.form['nm_menu']
    nm_bahan_lama = request.form['nm_bahan_lama']
    nm_bahan_baru = request.form['nm_bahan_baru']

    try:
        # Ambil satuan stok dari bahan baru
        semua_bahan = db.ambil_semua_bahan()
        satuan_stok_baru = next((b[1] for b in semua_bahan if b[0] == nm_bahan_baru), None)

        # Update data resep
        conn = db.conn
        cur = conn.cursor()
        cur.execute("""
            UPDATE Resep
            SET nm_bahan = ?, satuan_stok = ?
            WHERE nm_menu = ? AND nm_bahan = ?
        """, (nm_bahan_baru, satuan_stok_baru, nm_menu, nm_bahan_lama))
        conn.commit()

        flash(f"Berhasil menghubungkan '{nm_bahan_lama}' ke stok '{nm_bahan_baru}'", "success")

    except Exception as e:
        flash(f"Gagal menghubungkan bahan: {str(e)}", "danger")

    return redirect(url_for('kelola_resep', nama_menu=nm_menu))

@app.route('/edit_konversi', methods=['POST'])
def edit_konversi():
    nm_menu = request.form['nm_menu']  # tetap dipakai untuk redirect
    nm_bahan = request.form['nm_bahan']
    satuan_pakai = request.form['satuan_pakai']
    satuan_stok = request.form['satuan_stok']
    konversi_baru = request.form['konversi']

    try:
        conn = db.conn
        cur = conn.cursor()

        # 1. Update konversi di tabel Resep
        cur.execute("""
            UPDATE Resep
            SET konversi = ?
            WHERE nm_bahan = ? AND satuan_pakai = ? AND satuan_stok = ?
        """, (konversi_baru, nm_bahan, satuan_pakai, satuan_stok))
        print(f"✅ Updated Resep: {nm_bahan} {satuan_stok}->{satuan_pakai} = {konversi_baru}")

        # 2. Insert or update konversi_satuan
        cur.execute("""
            SELECT COUNT(*) FROM konversi_satuan
            WHERE nm_bahan = ? AND dari_satuan = ? AND ke_satuan = ?
        """, (nm_bahan, satuan_stok, satuan_pakai))
        exists = cur.fetchone()[0]

        if exists:
            # Update faktor konversi jika data sudah ada
            cur.execute("""
                UPDATE konversi_satuan
                SET faktor_konversi = ?
                WHERE nm_bahan = ? AND dari_satuan = ? AND ke_satuan = ?
            """, (konversi_baru, nm_bahan, satuan_stok, satuan_pakai))
            print(f"🔄 Updated konversi_satuan: {nm_bahan} {satuan_stok}->{satuan_pakai} = {konversi_baru}")
        else:
            # Insert data baru jika belum ada
            cur.execute("""
                INSERT INTO konversi_satuan (nm_bahan, dari_satuan, ke_satuan, faktor_konversi)
                VALUES (?, ?, ?, ?)
            """, (nm_bahan, satuan_stok, satuan_pakai, konversi_baru))
            print(f"✅ Inserted konversi_satuan: {nm_bahan} {satuan_stok}->{satuan_pakai} = {konversi_baru}")

        conn.commit()
        flash(f"Konversi untuk bahan '{nm_bahan}' telah diperbarui di Resep dan konversi_satuan.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Gagal memperbarui konversi: {str(e)}", "danger")

    return redirect(url_for('kelola_resep', nama_menu=nm_menu))




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
    conn = db.conn
    cur = conn.cursor()

    try:
        # 1. Ambil semua alias dari nama_standar
        cur.execute("SELECT nama_lama FROM BahanAlias WHERE LOWER(nama_standar) = LOWER(?)", (nm_bahan.lower(),))
        alias_list = [row[0] for row in cur.fetchall()]
        semua_nama = [nm_bahan] + alias_list

        # 2. Format parameter untuk IN clause
        format_q = ",".join("?" for _ in semua_nama)

        # 3. Ambil histori pembelian dari Pembelian + PembelianDetail
        pembelian_rows = cur.execute(f"""
            SELECT jumlah, harga, satuan, nm_bahan
            FROM Pembelian JOIN PembelianDetail USING(no_nota)
            WHERE LOWER(nm_bahan) IN ({format_q}) AND LOWER(satuan) = LOWER(?)
        """, [n.lower() for n in semua_nama] + [satuan.lower()]).fetchall()

        if not pembelian_rows:
            flash(f"Tidak ditemukan data pembelian dengan satuan '{satuan}' untuk '{nm_bahan}' dan aliasnya.", "danger")
            return redirect(url_for('infostok', nm_bahan=nm_bahan))

        # 4. Hitung total dari histori pembelian
        total_jumlah = 0
        total_nilai = 0
        alias_terlibat = set()

        for jumlah, harga, satuan_db, asal in pembelian_rows:
            total_jumlah += jumlah
            total_nilai += jumlah * harga
            alias_terlibat.add(asal)

        harga_rata = total_nilai / total_jumlah if total_jumlah else 0

        # 5. Hapus stok hanya untuk bahan+alias dengan satuan yg sama
        cur.execute(f"""
            DELETE FROM Stok 
            WHERE LOWER(nm_bahan) IN ({format_q}) AND LOWER(satuan) = LOWER(?)
        """, [n.lower() for n in semua_nama] + [satuan.lower()])

        # 6. Insert data baru yang telah dinormalisasi
        cur.execute("""
            INSERT OR REPLACE INTO Stok (nm_bahan, jumlah, satuan, harga_modal)
            VALUES (?, ?, ?, ?)
        """, (nm_bahan, total_jumlah, satuan, harga_rata))

        # 7. Catat ke LogNormalisasi
        cur.execute("""
            INSERT INTO LogNormalisasi (nama_standar, satuan, jumlah_awal, nilai_awal, harga_rata, alias_terlibat)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            nm_bahan,
            satuan,
            total_jumlah,
            total_nilai,
            harga_rata,
            ", ".join(sorted(alias_terlibat))
        ))

        conn.commit()
        flash(f"Normalisasi sukses berdasarkan histori pembelian: {total_jumlah:.2f} {satuan.upper()} ({nm_bahan})", "success")

    except Exception as e:
        flash(f"Gagal normalisasi: {str(e)}", "danger")

    return redirect(url_for('infostok', nm_bahan=nm_bahan))

# Tambahkan di app.py

@app.route('/neraca_rugi_laba', methods=['GET', 'POST'])
def neraca_rugi_laba():
    if request.method == 'POST':
        bulan = request.form['bulan']  # Format: YYYY-MM
        hasil = db.hitung_rugi_laba(bulan)
        if hasil:
            flash(f"Data berhasil dihitung untuk {bulan}", "success")
        else:
            flash("Gagal menghitung data", "danger")
        return redirect(url_for('neraca_rugi_laba'))

    # Tampilkan data neraca rugi laba
    data = db.get_neraca_rugi_laba()
    return render_template('neraca_rugi_laba.html', data=data)

@app.route('/neraca_rugi_laba/hapus/<int:id>', methods=['POST'])
def hapus_neraca(id):
    try:
        db.cursor.execute("DELETE FROM NeracaRugiLaba WHERE id = ?", (id,))
        db.conn.commit()
        flash("Data berhasil dihapus", "success")
    except Exception as e:
        flash(f"Gagal menghapus data: {e}", "danger")
    return redirect(url_for('neraca_rugi_laba'))

@app.template_filter('format_number')
def format_number(value):
    return "{:,.0f}".format(value or 0)

@app.route('/unduh_rugi_laba_excel')
def unduh_rugi_laba_excel():
    data = db.get_neraca_rugi_laba()
    if not data:
        flash("Tidak ada data untuk diunduh", "warning")
        return redirect(url_for('neraca_rugi_laba'))

    import pandas as pd
    import io
    from flask import send_file

    df = pd.DataFrame(data)
    df['pendapatan'] = df['pendapatan'].fillna(0)
    df['hpp'] = df['hpp'].fillna(0)
    df['laba_kotor'] = df['laba_kotor'].fillna(0)
    df['biaya_operasional'] = df['biaya_operasional'].fillna(0)
    df['laba_bersih'] = df['laba_bersih'].fillna(0)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='RugiLaba')

    output.seek(0)
    return send_file(output, as_attachment=True, download_name="laporan_rugi_laba.xlsx", mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/biaya_operasional', methods=['GET', 'POST'])
def form_biaya_operasional():
    if request.method == 'POST' and 'tanggal_pengeluaran' in request.form:
        # Proses tambah data
        tanggal_pengeluaran = request.form['tanggal_pengeluaran']
        keterangan = request.form['keterangan']
        jumlah = float(request.form['jumlah'])

        try:
            db.cursor.execute("""
                INSERT INTO BiayaOperasional (tanggal_pengeluaran, keterangan, jumlah)
                VALUES (?, ?, ?)
            """, (tanggal_pengeluaran, keterangan, jumlah))
            db.conn.commit()
            flash("Biaya operasional berhasil disimpan.", "success")
        except Exception as e:
            flash(f"Gagal menyimpan biaya: {e}", "danger")

        return redirect(url_for('form_biaya_operasional'))

    # Proses filter
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if start_date and end_date:
        histori = db.eksekusi_select("""
            SELECT * FROM BiayaOperasional
            WHERE tanggal_pengeluaran BETWEEN ? AND ?
            ORDER BY tanggal_pengeluaran DESC
        """, (start_date, end_date))
    else:
        histori = db.eksekusi_select("SELECT * FROM BiayaOperasional ORDER BY tanggal_pengeluaran DESC")

    return render_template('biaya_operasional.html', histori=histori, start_date=start_date, end_date=end_date)

@app.route('/hapus_biaya_operasional/<int:id>', methods=['POST'])
def hapus_biaya_operasional(id):
    try:
        db.cursor.execute("DELETE FROM BiayaOperasional WHERE id = ?", (id,))
        db.conn.commit()
        flash("Biaya berhasil dihapus.", "success")
    except Exception as e:
        flash(f"Gagal menghapus: {e}", "danger")
    return redirect(url_for('form_biaya_operasional'))


@app.route('/unduh_biaya_operasional_excel')
def unduh_biaya_operasional_excel():
    import pandas as pd
    import io
    from flask import send_file, request

    # Ambil tanggal filter dari query string
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if start_date and end_date:
        data = db.eksekusi_select("""
            SELECT tanggal_pengeluaran, keterangan, jumlah
            FROM BiayaOperasional
            WHERE tanggal_pengeluaran BETWEEN ? AND ?
            ORDER BY tanggal_pengeluaran DESC
        """, (start_date, end_date))
    else:
        data = db.eksekusi_select("""
            SELECT tanggal_pengeluaran, keterangan, jumlah
            FROM BiayaOperasional
            ORDER BY tanggal_pengeluaran DESC
        """)

    df = pd.DataFrame(data, columns=['Tanggal Pengeluaran', 'Keterangan', 'Jumlah (Rp)'])

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='BiayaOperasional')
    output.seek(0)

    return send_file(output,
                     as_attachment=True,
                     download_name="biaya_operasional.xlsx",
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/arus_kas', methods=['GET', 'POST'])
def arus_kas():
    hasil = detail_masuk = detail_biaya = detail_pembelian = None
    detail_piutang = detail_utang = None  # ← tambahkan inisialisasi di sini
    start_date = end_date = None

    if request.method == 'POST':
        start_date = request.form['start_date']
        end_date = request.form['end_date']
        hasil = db.hitung_arus_kas(start_date, end_date)
        detail_masuk = db.ambil_detail_kas_masuk(start_date, end_date)
        detail_biaya = db.ambil_detail_biaya_operasional(start_date, end_date)
        detail_pembelian = db.ambil_detail_pembelian_lunas(start_date, end_date)
        detail_piutang = db.ambil_detail_pelunasan_piutang(start_date, end_date)
        detail_utang = db.ambil_detail_pelunasan_utang(start_date, end_date)


    return render_template('arus_kas.html',
        hasil=hasil,
        detail_masuk=detail_masuk,
        detail_biaya=detail_biaya,
        detail_pembelian=detail_pembelian,
        detail_piutang=detail_piutang,
        detail_utang=detail_utang,
        start_date=start_date,
        end_date=end_date
    )



@app.route('/unduh_arus_kas_excel')
def unduh_arus_kas_excel():
    import pandas as pd
    import io
    from flask import send_file, request

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    hasil = db.hitung_arus_kas(start_date, end_date)
    detail_masuk = db.ambil_detail_kas_masuk(start_date, end_date)
    detail_biaya = db.ambil_detail_biaya_operasional(start_date, end_date)
    detail_pembelian = db.ambil_detail_pembelian_lunas(start_date, end_date)
    detail_piutang = db.ambil_detail_pelunasan_piutang(start_date, end_date)
    detail_utang = db.ambil_detail_pelunasan_utang(start_date, end_date)

    df_ringkasan = pd.DataFrame([
        ['Kas Masuk - Transaksi Langsung', hasil['kas_masuk']],
        ['Kas Masuk - Pelunasan Piutang', hasil['pelunasan_piutang']],
        ['Kas Keluar - Biaya Operasional', hasil['biaya_operasional']],
        ['Kas Keluar - Pembelian Lunas', hasil['pembelian_lunas']],
        ['Kas Keluar - Pelunasan Hutang', hasil['pelunasan_utang']],
        ['Total Kas Keluar', hasil['kas_keluar']],
        ['Saldo Kas Bersih', hasil['kas_bersih']]
    ], columns=['Kategori', 'Jumlah'])

    df_masuk = pd.DataFrame(detail_masuk, columns=['Tanggal', 'No Nota', 'Jenis Pembayaran', 'Total'])
    df_biaya = pd.DataFrame(detail_biaya, columns=['Tanggal', 'Keterangan', 'Jumlah'])
    df_pembelian = pd.DataFrame(detail_pembelian, columns=['Tanggal', 'No Nota', 'Total'])
    df_piutang = pd.DataFrame(detail_piutang, columns=['Tanggal', 'No Nota', 'Jumlah', 'Keterangan'])
    df_utang = pd.DataFrame(detail_utang, columns=['Tanggal', 'No Nota', 'Jumlah', 'Keterangan'])

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        currency_format = workbook.add_format({'num_format': '#,##0', 'align': 'right'})
        header_format = workbook.add_format({'bold': True, 'bg_color': '#d9eaf7', 'border': 1})
        total_format = workbook.add_format({'bold': True, 'top': 1, 'num_format': '#,##0', 'align': 'right'})
        title_format = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center'})
        kas_bersih_format = workbook.add_format({
            'bold': True, 'align': 'right', 'num_format': '#,##0',
            'font_color': 'green' if hasil['kas_bersih'] >= 0 else 'red'
        })

        def format_sheet(df, sheet_name, money_cols=[]):
            df.to_excel(writer, index=False, sheet_name=sheet_name, startrow=2)
            ws = writer.sheets[sheet_name]

            ws.merge_range(0, 0, 0, len(df.columns)-1, f'Detail {sheet_name}', title_format)

            for col_num, col_name in enumerate(df.columns):
                ws.write(2, col_num, col_name, header_format)
                col_width = max(15, df[col_name].astype(str).map(len).max() + 2)
                ws.set_column(col_num, col_num, col_width)

            for row in range(3, len(df)+3):
                for col in money_cols:
                    ws.write_number(row, col, df.iloc[row-3, col], currency_format)

            if money_cols:
                total_row = len(df) + 3
                for col in money_cols:
                    col_letter = chr(65 + col)
                    ws.write_formula(total_row, col, f"=SUM({col_letter}4:{col_letter}{total_row})", total_format)
                    ws.write(total_row, col - 1, "Total", total_format)

            ws.autofilter(2, 0, len(df)+2, len(df.columns)-1)

        format_sheet(df_masuk, 'Kas Masuk', money_cols=[3])
        format_sheet(df_biaya, 'Biaya Operasional', money_cols=[2])
        format_sheet(df_pembelian, 'Pembelian Lunas', money_cols=[2])
        format_sheet(df_piutang, 'Pelunasan Piutang', money_cols=[2])
        format_sheet(df_utang, 'Pelunasan Utang', money_cols=[2])

        # Sheet Ringkasan
        df_ringkasan.to_excel(writer, index=False, sheet_name='Ringkasan', startrow=2)
        ws = writer.sheets['Ringkasan']
        ws.merge_range('A1:B1', f'Ringkasan Arus Kas Periode {start_date} s.d. {end_date}', title_format)
        ws.write('A3', 'Kategori', header_format)
        ws.write('B3', 'Jumlah', header_format)
        ws.set_column(0, 0, 40)
        ws.set_column(1, 1, 20)

        for i in range(len(df_ringkasan)):
            k = df_ringkasan.iloc[i, 0]
            v = df_ringkasan.iloc[i, 1]
            ws.write(i+3, 0, k)
            if k == 'Saldo Kas Bersih':
                ws.write_number(i+3, 1, v, kas_bersih_format)
            else:
                ws.write_number(i+3, 1, v, currency_format)

    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name=f"arus_kas_{start_date}_sd_{end_date}.xlsx",
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@app.route('/unduh_arus_kas_pdf')
def unduh_arus_kas_pdf():
    from xhtml2pdf import pisa

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    hasil = db.hitung_arus_kas(start_date, end_date)
    detail_masuk = db.ambil_detail_kas_masuk(start_date, end_date)
    detail_biaya = db.ambil_detail_biaya_operasional(start_date, end_date)
    detail_pembelian = db.ambil_detail_pembelian_lunas(start_date, end_date)
    detail_piutang = db.ambil_detail_pelunasan_piutang(start_date, end_date)
    detail_utang = db.ambil_detail_pelunasan_utang(start_date, end_date)

    html = render_template('arus_kas_pdf.html',
                           hasil=hasil,
                           detail_masuk=detail_masuk,
                           detail_biaya=detail_biaya,
                           detail_pembelian=detail_pembelian,
                           detail_piutang=detail_piutang,
                           detail_utang=detail_utang,
                           start_date=start_date,
                           end_date=end_date,
                           now=datetime.now())

    result = io.BytesIO()
    pisa.CreatePDF(io.StringIO(html), dest=result)
    result.seek(0)

    return send_file(result,
                     mimetype='application/pdf',
                     as_attachment=True,
                     download_name=f"arus_kas_{start_date}_sd_{end_date}.pdf")



@app.route('/laporan_stok')
def laporan_stok():
    data = db.get_stok_saat_ini()
    total_modal = sum(row[4] or 0 for row in data)  # row[4] = total_nilai per bahan
    return render_template('laporan_stok.html', data=data, total_modal=total_modal)


@app.route('/histori_stok', methods=['GET', 'POST'])
def histori_stok():
    data = []
    start = end = None

    if request.method == 'POST':
        start = request.form['start_date']
        end = request.form['end_date']
        data = db.get_histori_stok(start, end)

    return render_template('histori_stok.html', data=data, start_date=start, end_date=end)


@app.route('/grafik_bahan', methods=['GET', 'POST'])
def grafik_bahan():
    data = []
    nama_bahan = ''
    start = end = None

    if request.method == 'POST':
        nama_bahan = request.form['bahan']
        start = request.form['start']
        end = request.form['end']
        data = db.get_pergerakan_bahan(nama_bahan, start, end)

    # Ambil list semua bahan
    daftar_bahan = db.ambil_nama_bahan()  # Fungsi: SELECT DISTINCT nm_bahan FROM Stok/PembelianDetail

    return render_template('grafik_bahan.html',
                           data=data,
                           daftar_bahan=daftar_bahan,
                           bahan_terpilih=nama_bahan,
                           start=start,
                           end=end)

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    import datetime
    today = datetime.date.today()
    start = end = today

    if request.method == 'POST':
        start = request.form['start_date']
        end = request.form['end_date']
    else:
        start = today.replace(day=1).isoformat()
        end = today.isoformat()

    # Data berdasarkan filter tanggal
    pendapatan = db.hitung_pendapatan_range(start, end)
    pengeluaran = db.hitung_pengeluaran_range(start, end)
    nilai_stok = db.hitung_nilai_modal_stok()
    chart_rugi_laba = db.get_rugi_laba_per_bulan()
    chart_arus_kas = db.get_arus_kas_per_bulan()
    transaksi_terbaru = db.get_transaksi_terbaru(5)

    return render_template('dashboard.html',
        pendapatan=pendapatan,
        pengeluaran=pengeluaran,
        nilai_stok=nilai_stok,
        chart_rugi_laba=chart_rugi_laba,
        chart_arus_kas=chart_arus_kas,
        transaksi_terbaru=transaksi_terbaru,
        start_date=start,
        end_date=end)


@app.route('/laporan/jurnal')
def laporan_jurnal():
    start = request.args.get('start')
    end = request.args.get('end')
    data = db.get_jurnal_umum(start, end)
    return render_template('jurnal.html', data=data, start=start, end=end)

@app.route('/laporan/buku_besar/<kode_akun>')
def laporan_buku_besar(kode_akun):
    start = request.args.get('start')
    end = request.args.get('end')
    
    # Map kode akun ke nama akun
    if kode_akun == '1000':
        akun = 'Kas'
    elif kode_akun == '1100':
        akun = 'Bank QRIS'
    elif kode_akun == '1200':
        akun = 'Bank Transfer'
    elif kode_akun == '4000':
        akun = 'Pendapatan Usaha'
    else:
        akun = 'Akun Tidak Dikenal'

    # Ambil data buku besar untuk kode akun tertentu
    data = db.get_buku_besar(kode_akun, start, end)
    
    # Kirim data ke template untuk ditampilkan
    return render_template('buku_besar.html', 
                           data=data, 
                           start=start, 
                           end=end, 
                           kode_akun=kode_akun, 
                           akun=akun)

@app.route('/laporan/buku_besar')
def buku_besar_semua():
    start = request.args.get('start', '2025-01-01')
    end = request.args.get('end', '2025-12-31')
    semua_data = db.get_buku_besar_semua(start, end)
    return render_template('buku_besar_semua.html', semua_data=semua_data, start=start, end=end)


@app.route('/export_jurnal')
def export_jurnal():
    from io import BytesIO
    start = request.args.get('start')
    end = request.args.get('end')
    data = db.get_jurnal_umum(start, end)

    # Mengubah data ke format DataFrame untuk export ke Excel
    df = pd.DataFrame(data)

    # Membuat buffer untuk menulis file Excel
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Jurnal')
        writer.save()

    output.seek(0)

    return send_file(output, as_attachment=True, download_name="jurnal_umum.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route('/export_jurnal_pdf')
def export_jurnal_pdf():
    from xhtml2pdf import pisa
    from io import BytesIO
    start = request.args.get('start')
    end = request.args.get('end')
    data = db.get_jurnal_umum(start, end)

    # Mengubah data ke format HTML
    html_content = render_template('jurnal_pdf_template.html', data=data, start=start, end=end)

    result = BytesIO()
    pisa.CreatePDF(html_content, dest=result)
    result.seek(0)

    return send_file(result, as_attachment=True, download_name="jurnal_umum.pdf", mimetype="application/pdf")

@app.route('/export_buku_besar/<kode_akun>')
def export_buku_besar(kode_akun):
    from io import BytesIO
    start = request.args.get('start')
    end = request.args.get('end')
    data = db.get_buku_besar(kode_akun, start, end)

    # Mengubah data ke format DataFrame untuk export ke Excel
    df = pd.DataFrame(data)

    # Membuat buffer untuk menulis file Excel
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Buku Besar')
        writer.save()

    output.seek(0)

    return send_file(output, as_attachment=True, download_name="buku_besar.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route('/export_buku_besar_pdf/<kode_akun>')
def export_buku_besar_pdf(kode_akun):
    from xhtml2pdf import pisa
    from io import BytesIO
    start = request.args.get('start')
    end = request.args.get('end')
    data = db.get_buku_besar(kode_akun, start, end)

    # Mengubah data ke format HTML
    html_content = render_template('buku_besar_pdf_template.html', data=data, start=start, end=end, kode_akun=kode_akun)

    result = BytesIO()
    pisa.CreatePDF(html_content, dest=result)
    result.seek(0)

    return send_file(result, as_attachment=True, download_name="buku_besar.pdf", mimetype="application/pdf")

@app.route('/pelunasan/piutang', methods=['GET', 'POST'])
def pelunasan_piutang():
    data_transaksi = None
    data_piutang_lunas = None
    sisa_hutang = 0
    total_pelunasan = 0
    pencarian_dilakukan = False  # FLAG INI

    if request.method == 'POST':
        pencarian_dilakukan = True  # SET TRUE ketika user submit form
        no_nota = request.form['no_nota'].strip().upper()

        # Ambil data pelunasan sebelumnya
        db.cursor.execute("""
            SELECT no_nota, tanggal, jumlah, keterangan, metode_pembayaran
            FROM PelunasanPiutang
            WHERE no_nota = ?
        """, (no_nota,))
        data_piutang_lunas = db.cursor.fetchall()

        # Hitung total pelunasan
        total_pelunasan = sum(row[2] for row in data_piutang_lunas)

        # Cek data transaksi penjualan
        db.cursor.execute("""
            SELECT t.no_nota, t.tanggal, SUM(td.jumlah * td.harga_satuan) AS total
            FROM Transaksi t
            JOIN TransaksiDetail td ON t.no_nota = td.no_nota
            WHERE UPPER(t.no_nota) = ?
            GROUP BY t.no_nota
        """, (no_nota,))
        result = db.cursor.fetchone()

        if result:
            data_transaksi = {
                'no_nota': result[0],
                'tanggal': result[1],
                'total_piutang': result[2]
            }
            total_hutang = result[2]
            sisa_hutang = total_hutang - total_pelunasan

            if sisa_hutang <= 0:
                flash("Nota sudah lunas, tidak ada hutang yang perlu dibayar lagi.", 'warning')
            else:
                flash(f"Sisa hutang yang harus dibayar: Rp {sisa_hutang:,.0f}", 'info')
        else:
            flash('No Nota tidak ditemukan.', 'danger')

    # Nilai default untuk tampilan awal
    if data_transaksi is None:
        data_transaksi = {'no_nota': '', 'tanggal': '', 'total_piutang': 0}

    return render_template(
        'pelunasan_piutang.html',
        data=data_transaksi,
        piutang_lunas=data_piutang_lunas,
        sisa_hutang=sisa_hutang,
        total_pelunasan=total_pelunasan,
        pencarian_dilakukan=pencarian_dilakukan
    )

@app.route('/pelunasan/piutang/simpan', methods=['POST'])
def simpan_pelunasan_piutang():
    no_nota = request.form['no_nota']
    tanggal = request.form['tanggal']
    jumlah = float(request.form['jumlah'])
    keterangan = request.form.get('keterangan', '')
    metode = request.form['metode_pembayaran']

    # Pastikan kolom metode_pembayaran sudah ada di DB
    db.cursor.execute("""
        INSERT INTO PelunasanPiutang (no_nota, tanggal, jumlah, keterangan, metode_pembayaran)
        VALUES (?, ?, ?, ?, ?)
    """, (no_nota, tanggal, jumlah, keterangan, metode))

    db.conn.commit()
    flash("Pelunasan piutang berhasil disimpan.", "success")
    return redirect(url_for('pelunasan_piutang'))

from flask import Flask, render_template, request, redirect, url_for, flash

@app.route('/konversi_satuan', methods=['GET', 'POST'])
def konversi_satuan():
    if request.method == 'POST':
        nm_bahan = request.form['nm_bahan']
        dari_satuan = request.form['dari_satuan']
        ke_satuan = request.form['ke_satuan']
        faktor_konversi = request.form['faktor_konversi']

        if request.form.get('id'):  # Edit mode
            id = request.form['id']
            db.cursor.execute("""
                UPDATE konversi_satuan
                SET nm_bahan = ?, dari_satuan = ?, ke_satuan = ?, faktor_konversi = ?
                WHERE id = ?
            """, (nm_bahan, dari_satuan, ke_satuan, faktor_konversi, id))
            flash('Data konversi satuan berhasil diupdate.', 'success')
        else:  # Add mode
            db.cursor.execute("""
                INSERT INTO konversi_satuan (nm_bahan, dari_satuan, ke_satuan, faktor_konversi)
                VALUES (?, ?, ?, ?)
            """, (nm_bahan, dari_satuan, ke_satuan, faktor_konversi))
            flash('Data konversi satuan berhasil ditambahkan.', 'success')

        db.conn.commit()
        return redirect(url_for('konversi_satuan'))

    # GET method
    db.cursor.execute("SELECT * FROM konversi_satuan ORDER BY nm_bahan")
    data_konversi = db.cursor.fetchall()
    return render_template('konversi_satuan.html', data_konversi=data_konversi)


@app.route('/konversi_satuan/delete/<int:id>', methods=['GET'])
def delete_konversi_satuan(id):
    db.cursor.execute("DELETE FROM konversi_satuan WHERE id = ?", (id,))
    db.conn.commit()
    flash('Data konversi satuan berhasil dihapus.', 'success')
    return redirect(url_for('konversi_satuan'))


@app.route('/konversi_satuan/edit/<int:id>', methods=['GET'])
def edit_konversi_satuan(id):
    db.cursor.execute("SELECT * FROM konversi_satuan WHERE id = ?", (id,))
    row = db.cursor.fetchone()

    db.cursor.execute("SELECT * FROM konversi_satuan ORDER BY nm_bahan")
    data_konversi = db.cursor.fetchall()

    return render_template('konversi_satuan.html', edit_row=row, data_konversi=data_konversi)

if __name__ == '__main__':
    app.run(debug=True)
