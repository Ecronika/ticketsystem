import sqlite3
import os

db_path = r'c:\Users\tpaul\.gemini\antigravity\scratch\azubi_werkzeug\azubi_werkzeug\werkzeug.db'

def inspect_db():
    if not os.path.exists(db_path):
        print(f"File not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("--- Tables ---")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    print(tables)

    if 'alembic_version' in tables:
        print("\n--- alembic_version ---")
        cursor.execute("SELECT version_num FROM alembic_version;")
        print(cursor.fetchall())
    else:
        print("\n--- alembic_version table MISSING ---")

    if 'check' in tables:
        print("\n--- check table info ---")
        cursor.execute("PRAGMA table_info('check');")
        for col in cursor.fetchall():
            print(col)
    
    conn.close()

if __name__ == "__main__":
    inspect_db()
