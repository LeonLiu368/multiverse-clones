import re, sys, pathlib
raw = ""
p = pathlib.Path("/workspace/answer.txt")
if p.exists():
    raw = p.read_text().strip()

def norm(s: str) -> str:
    s = s.strip().lower()
    m = re.search(r'(\d{1,2}):(\d{2})', s)            # HH:MM (optionally with am/pm)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 'pm' in s and h < 12: h += 12
        if 'am' in s and h == 12: h = 0
        return f"{h:02d}:{mi:02d}"
    m = re.search(r'(\d{1,2})\s*([ap])\.?m', s)        # 6pm / 6 pm
    if m:
        h = int(m.group(1))
        if m.group(2) == 'p' and h < 12: h += 12
        if m.group(2) == 'a' and h == 12: h = 0
        return f"{h:02d}:00"
    m = re.fullmatch(r'(\d{2})(\d{2})', s)             # 1800
    if m:
        return f"{m.group(1)}:{m.group(2)}"
    return ""

ans = norm(raw)
ok = ans == "18:00"
print(f"answer={raw!r} normalized={ans!r}")
print("reward=1" if ok else "reward=0")
sys.exit(0 if ok else 1)
