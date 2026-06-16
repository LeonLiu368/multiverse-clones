import re, sys, pathlib
raw = ""
p = pathlib.Path("/workspace/answer.txt")
if p.exists(): raw = p.read_text().strip()
m = re.search(r'\d+', raw)
got = m.group(0) if m else ""
ok = got == "3"   # 2 baked "testing" messages + 1 overlay = 3
print(f"answer={raw!r} parsed={got!r} expected=3")
sys.exit(0 if ok else 1)
