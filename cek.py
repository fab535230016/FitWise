import sqlite3
from pathlib import Path
from pypdf import PdfReader

con = sqlite3.connect(r"data\chroma_db\chroma.sqlite3")

rows = con.execute(
    "SELECT string_value, COUNT(*) FROM embedding_metadata "
    "WHERE key='source' GROUP BY string_value ORDER BY string_value"
).fetchall()

chars = dict(con.execute(
    "SELECT em2.string_value, SUM(LENGTH(em.string_value)) "
    "FROM embedding_metadata em "
    "JOIN embeddings e ON e.id = em.id "
    "JOIN embedding_metadata em2 ON em2.id = em.id AND em2.key = 'source' "
    "WHERE em.key = 'chroma:document' GROUP BY em2.string_value"
).fetchall())

print(f"{'dokumen':<52}{'hal':>5}{'potongan':>10}{'karakter':>10}")
total_h = total_p = total_c = 0
for source, count in rows:
    pdf = Path("data/knowledge_base") / source
    pages = len(PdfReader(str(pdf)).pages) if pdf.exists() else 0
    c = chars.get(source, 0)
    print(f"{source:<52}{pages:>5}{count:>10}{c:>10,}")
    total_h += pages
    total_p += count
    total_c += c
print("-" * 77)
print(f"{'TOTAL':<52}{total_h:>5}{total_p:>10}{total_c:>10,}")