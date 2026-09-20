import sqlite3, os
p = os.path.join('site', 'site.db')
c = sqlite3.connect(p)
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("TABLES:", tables)
for t in tables:
    try:
        cols = [r[1] for r in c.execute(f"PRAGMA table_info({t})")]
        print(t, "->", cols)
    except Exception as e:
        print(t, "ERR", e)