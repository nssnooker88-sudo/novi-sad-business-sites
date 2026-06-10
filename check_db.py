import sqlite3, os
db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database", "businesses.sqlite")
db = sqlite3.connect(db_path)
db.row_factory = sqlite3.Row
r = db.execute("SELECT COUNT(*) total, SUM(CASE WHEN email IS NOT NULL AND email != '' THEN 1 ELSE 0 END) has_email, SUM(CASE WHEN pib IS NOT NULL AND pib != '' THEN 1 ELSE 0 END) has_pib, SUM(CASE WHEN lead_status='HIGH_PRIORITY' THEN 1 ELSE 0 END) hp FROM businesses").fetchone()
print("Stats:", dict(r))
print("\nHIGH_PRIORITY sample:")
rows = db.execute("SELECT business_name, pib, phone, email FROM businesses WHERE lead_status='HIGH_PRIORITY' LIMIT 15").fetchall()
for row in rows:
    print(dict(row))
print("\nHP without email and with PIB:")
rows2 = db.execute("SELECT COUNT(*) c FROM businesses WHERE lead_status='HIGH_PRIORITY' AND (email IS NULL OR email='') AND pib IS NOT NULL AND pib != ''").fetchone()
print(dict(rows2))
print("\nHP without email and without PIB:")
rows3 = db.execute("SELECT COUNT(*) c FROM businesses WHERE lead_status='HIGH_PRIORITY' AND (email IS NULL OR email='') AND (pib IS NULL OR pib='')").fetchone()
print(dict(rows3))
