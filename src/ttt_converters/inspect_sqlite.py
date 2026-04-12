import sys
import sqlite3
from pathlib import Path

input_file = Path(sys.argv[1]) if len(sys.argv) > 1 else None
if not input_file or not input_file.exists():
    sys.exit("Usage: python inspect_sqlite.py <input.bbl.mybible>")

conn = sqlite3.connect(str(input_file))
cursor = conn.cursor()

print("Tables found:")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [row[0] for row in cursor.fetchall()]
for table in tables:
    print(f" - {table}")
    try:
        cursor.execute(f"PRAGMA table_info('{table}')")
        cols = [col[1] for col in cursor.fetchall()]
        print("   Columns:", cols)
        cursor.execute(f"SELECT * FROM {table} LIMIT 3")
        for row in cursor.fetchall():
            print("   Row:", row)
    except Exception as e:
        print("   (Could not query rows)", e)
    print()

conn.close()
