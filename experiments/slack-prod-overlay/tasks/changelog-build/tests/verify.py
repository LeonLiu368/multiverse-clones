import re, sys, pathlib
raw = ""
p = pathlib.Path("/workspace/answer.txt")
if p.exists(): raw = p.read_text().strip()
m = re.search(r'-?\d+', raw)
got = m.group(0) if m else ""
ok = got == "19"   # v8.5.0 shipped as build #10 (prod) + "9 builds after" (overlay) = 19
print(f"answer={raw!r} parsed={got!r} expected=19")
sys.exit(0 if ok else 1)
