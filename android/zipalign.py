"""base.apk 에 classes.dex 를 넣고, 압축하지 않은 항목을 4바이트(.so는 4096)에 맞춰 다시 쓴다 (zipalign -p 대용)."""
import sys, zipfile
src, dex, out = sys.argv[1:4]
zin = zipfile.ZipFile(src)
entries = [(i, zin.read(i.filename)) for i in zin.infolist()]
entries.append((zipfile.ZipInfo("classes.dex", date_time=(2026, 1, 1, 0, 0, 0)), open(dex, "rb").read()))
with open(out, "wb") as f, zipfile.ZipFile(f, "w") as z:
    for info, data in entries:
        zi = zipfile.ZipInfo(info.filename, date_time=info.date_time if info.date_time[0] >= 1980 else (2026, 1, 1, 0, 0, 0))
        store = info.filename == "resources.arsc" or info.compress_type == zipfile.ZIP_STORED or info.filename.endswith((".png", ".jpg"))
        zi.compress_type = zipfile.ZIP_STORED if store else zipfile.ZIP_DEFLATED
        zi.external_attr = info.external_attr
        if store:
            align = 4096 if info.filename.endswith(".so") else 4
            off = f.tell() + 30 + len(zi.filename.encode())
            zi.extra = b"\0" * ((align - off % align) % align)
        z.writestr(zi, data)
print("aligned", out)
