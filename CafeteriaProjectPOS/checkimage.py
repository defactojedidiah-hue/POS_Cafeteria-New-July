"""
check_images.py — Run this to see all products with/without image URLs
Place in your project folder and run once.
"""
import sqlite3

conn = sqlite3.connect("offline_cache.db")
cur  = conn.cursor()

cur.execute("SELECT name, store, image_url FROM products_cache ORDER BY store, name")
rows = cur.fetchall()

print(f"\n{'='*60}")
print(f"Total products: {len(rows)}")
print(f"{'='*60}\n")

has_url   = [(n,s,u) for n,s,u in rows if u and u.strip()]
no_url    = [(n,s,u) for n,s,u in rows if not u or not u.strip()]

print(f"✅ Products WITH image URL: {len(has_url)}")
for name, store, url in has_url:
    print(f"   [{store}] {name}")

print(f"\n❌ Products WITHOUT image URL: {len(no_url)}")
for name, store, url in no_url:
    print(f"   [{store}] {name}")

conn.close()
print("\nDone!")