import re, sys, pathlib
raw = ""
p = pathlib.Path("/workspace/answer.txt")
if p.exists():
    raw = p.read_text().lower()
def field(key):
    m = re.search(rf"{key}\s*=\s*(.+)", raw)
    return (m.group(1).strip() if m else "")
rd = field("release_date")
au = field("author")
# release date: accept "december 22", "dec 22", "12/22", "12-22", "22 december"
rd_ok = bool(re.search(r"(december|dec|12)\D*22|22\D*(december|dec)", rd))
au_ok = ("alex" in au and "okafor" in au)
print(f"release_date={rd!r} ok={rd_ok} | author={au!r} ok={au_ok}")
sys.exit(0 if (rd_ok and au_ok) else 1)
