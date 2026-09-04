import sqlite3

DB = r"C:\Users\Javier Cuicas\Desktop\papeleria_app\dist\papeleria (1).db"

conn = sqlite3.connect(DB)
cursor = conn.cursor()

print("\n=== FOREIGN KEYS DE detalle_ventas ===")

cursor.execute("PRAGMA foreign_key_list(detalle_ventas)")
for fila in cursor.fetchall():
    print(fila)

print("\n=== TRIGGERS ===")

cursor.execute("""
    SELECT name, sql
    FROM sqlite_master
    WHERE type = 'trigger'
""")

for nombre, sql in cursor.fetchall():
    print("\nTRIGGER:", nombre)
    print(sql)

print("\n=== TABLAS ===")

cursor.execute("""
    SELECT name
    FROM sqlite_master
    WHERE type = 'table'
    ORDER BY name
""")

for tabla in cursor.fetchall():
    print(tabla[0])

conn.close()