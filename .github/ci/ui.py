"""에뮬레이터 화면에서 글자로 요소를 찾아 누른다 (임시 점검용)."""
import re, subprocess, sys, time
def dump():
    subprocess.run(["adb", "shell", "uiautomator", "dump", "/sdcard/ui.xml"], capture_output=True)
    return subprocess.run(["adb", "shell", "cat", "/sdcard/ui.xml"], capture_output=True, text=True).stdout
def find(pat, attr="text|content-desc|hint"):
    x = dump()
    for m in re.finditer(r'<node [^>]*>', x):
        n = m.group(0)
        for a in attr.split("|"):
            v = re.search(a + r'="([^"]*)"', n)
            if v and re.search(pat, v.group(1)):
                b = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', n)
                if b:
                    x1, y1, x2, y2 = map(int, b.groups())
                    if x2 - x1 < 2 or y2 - y1 < 2: continue  # 화면 밖 요소
                    return (x1 + x2) // 2, (y1 + y2) // 2
    return None
cmd, pat = sys.argv[1], sys.argv[2]
for _ in range(int(sys.argv[3]) if len(sys.argv) > 3 else 10):
    p = find(pat)
    if p:
        if cmd in ("tap", "tapscroll"): subprocess.run(["adb", "shell", "input", "tap", str(p[0]), str(p[1])])
        print("found", pat, p); sys.exit(0)
    if cmd == "tapscroll": subprocess.run(["adb", "shell", "input", "swipe", "160", "520", "160", "220", "300"])
    time.sleep(2)
print("NOT FOUND", pat); sys.exit(1)
