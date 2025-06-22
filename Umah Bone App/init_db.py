import sqlite3

conn = sqlite3.connect('dbBone.db')
c = conn.cursor()

# Buat tabel bahan
c.execute('''
CREATE TABLE IF NOT EXISTS bahan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nama TEXT NOT NULL,
    stok REAL NOT NULL,
    satuan TEXT NOT NULL
)
''')

# Buat tabel resep
c.execute('''
CREATE TABLE IF NOT EXISTS resep (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nama TEXT NOT NULL
)
''')

# Buat tabel penghubung resep dan bahan
c.execute('''
CREATE TABLE IF NOT EXISTS resep_bahan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resep_id INTEGER NOT NULL,
    bahan_id INTEGER NOT NULL,
    jumlah REAL NOT NULL,
    FOREIGN KEY (resep_id) REFERENCES resep(id),
    FOREIGN KEY (bahan_id) REFERENCES bahan(id)
)
''')

# Tambahkan data contoh
c.execute("INSERT INTO bahan (nama, stok, satuan) VALUES ('Tepung Terigu', 1000, 'gram')")
c.execute("INSERT INTO bahan (nama, stok, satuan) VALUES ('Telur', 30, 'butir')")
c.execute("INSERT INTO bahan (nama, stok, satuan) VALUES ('Gula', 500, 'gram')")

c.execute("INSERT INTO resep (nama) VALUES ('Pancake')")
resep_id = c.lastrowid
c.execute("INSERT INTO resep_bahan (resep_id, bahan_id, jumlah) VALUES (?, ?, ?)", (resep_id, 1, 200))  # Tepung
c.execute("INSERT INTO resep_bahan (resep_id, bahan_id, jumlah) VALUES (?, ?, ?)", (resep_id, 2, 2))    # Telur
c.execute("INSERT INTO resep_bahan (resep_id, bahan_id, jumlah) VALUES (?, ?, ?)", (resep_id, 3, 50))   # Gula

conn.commit()
conn.close()

print("Database berhasil dibuat dan diisi.")
