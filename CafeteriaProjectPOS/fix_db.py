import sqlite3
conn = sqlite3.connect("offline_cache.db")
cur  = conn.cursor()
cur.execute("SELECT name, image_url FROM products_cache WHERE image_url != '' AND image_url IS NOT NULL")
for r in cur.fetchall():
    print(r)
conn.close()