import sqlite3

def migrate(db_path="dbBone.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Cek apakah kolom sudah ada
    cursor.execute("PRAGMA table_info(Resep)")
    columns = [row[1] for row in cursor.fetchall()]

    needed_columns = {
        "Satuan_pakai": "TEXT",
        "Konversi": "REAL",
        "Satuan_stok": "TEXT"
    }

    for col, col_type in needed_columns.items():
        if col not in columns:
            print(f"Menambah kolom {col} ke tabel Resep")
            cursor.execute(f"ALTER TABLE Resep ADD COLUMN {col} {col_type}")

    conn.commit()
    conn.close()
    print("Migrasi selesai.")

if __name__ == "__main__":
    migrate()
