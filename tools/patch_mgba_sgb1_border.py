#!/usr/bin/env python3
import base64
import re
import struct
import sys
import zlib
from pathlib import Path

EXPECTED_REV = "6dce57eef127dc4cc292644f38196e0e7c58590c"

PAL_Z = "eNpjYLiRFBq1zjHb9JiCoJewwnwGZQee1C6FMxYMYAAAnn0IDg=="
TILEMAP_Z = "eNrt1clyAVEYhmGNIMaXJIh5FsQUJGaJWQxx/1eTXpzeKIseVNl0vdvv2fyLcySku2bFhl1nD7J34MSls0fh3SKPyrxir3ifyKIyv9ibXvEBgx7z/qbX7IMGfciQf+LZgH8hTET2UV6JieIqS5AkRVq8wBmyGsuRv+EPUKBIiTJvVKhS4506DZq0aPNBhy49Pvmiz+CKHjJizIQpM775Yc6CJSvWbNiy45c9B46c+OMsry/7B7q3V1M="
CHARDATA_Z = "eNqFVl9IW1cY/+7NnbkyZ446qIW0XrWjW1/q2o1mBMy1Sk2h0MFeBnuobR86GHQOB7HYLX+U6oZYC3towTjHXvboU9Ou2kTMjIzM9GUblNibLKMRVk1sijc2iWffvdeb9Gprz48bPOd3zne+832/7xwB9m50B/bmtxgjy+BY1pJqXBLGO5qvXRzt5pVRMzSBA9wIdRVVrdKKfaNNSzbSeJyrZmEu0ZxQ7ScgD0V4Dg+hgDsawYARZ4kRFF4KunNXzR+gCcaIAhih+21c96o+vKYf3LX+dQjuwMtn5dpKVxcWfL5ffdt9KMGCzXfV1/W9b8FX6trk57dn+r5esJVgE/S+8fQp1nj6PKTYFJtU8VvVPDfP5XHsOSi/WXiGeEEbmLP8Ls+GeQUWcrStSWgSHOIKrEAIHoAHpvATjepCCzvX52Ed/ZpjBzlTjbmxSVDmlNCDZ2jnAdqgHrdnL/1qqqnwmmoqTddNZOSiZ1qc6dHnudWvaVd10D1HdvMOw1ngFfnbwmh6gGFO1xrHFvBLgM/EVJkbz/U4Qsq4EuV/YRwEXAHgEI3nF9XRSlsjT2uKpgrfBLXA7CrynWeoNA7L2VSssEWs7uwLfHe/cf+2XfdH3lyoqkAdNFVAgWT+/jxtS1tlq+SUehRaiECapHlZoIJEwZx3L56YBmofHYgORBXe07/Yn4fwwBBC27VkMhVnu0ut/j5tV5bhTexddvmCX81BaLklQSIt0VapRWFDIIQsGZt0PK7Y19Dzo/8f6Xz8Z91vjKIfHpniOt+YTrWn39q4pfOdAPNEZjYoXO+lmIOrg4Vr8qhrUSV7oXewl8vx8ohLXx/Lyo32qD2sr28L8dmwLWxD39kCJ/NbsEoooZziO2fizYylvhasYMWcM3NMRUUh/LOdhkLl+L6ZwXWSQA/dOxPgczVgIRbAUgMHZxf7+D4METeAVSKPyJ77izMdQ6ahwaFhtSyvd1zvHLvXFXAG+ADIaPsJ/C50DTqHnRFnjI9BrEH6cDkACm4zt5n71RmSIc6YgtNLziVxicRIrMChVwnNN4VXr4a85htJkIRkCfYEzwadCB5vL1FwoGQdog3RL+IT4RAlJlP/Bffl0KVG+b2/mj0eIUlSP+TGXZ40n65eurK0xa4JgTNKsilL2aErDK2jzmE8h6qfR82Zum/qT4wEw5L30U/LU80hkvStL/ZBUAjCJDtJUUTKramp1OPGckqIIfBoVeLeUYfdd4zqvfOa1xFA0fQmlzeXefSJNVX4WG/m00BNW6zMY1ydEUuZVzRtH628joqmwwP5Mu/vm/1k9pPzkzrP+hVU7McPRw9HjtkiOt8afz/+bqwsD7Cmllv8F5IHdT5khbgwYS3zG7dkf26iWtZ5ZgPkmtzT8hXhWnRFC9dm+nSed424uFzntM7bw/ZozhrJ67yiaT7bVnagAJSjJFNPeblm8w28T6yKqkktWHhzFcYpeHJWjLb+0RqcoiDjcyu2n2xvsB47IKI5XsYMjVCYO7DcQsX74hYmDTNI21MwB3OMl/ECzHTM1t9lN7GGcpwJq6dz7GT8VLyqyOVr8kUM40O8RzfgW7gMl8lB9OedErNZveldv7F+I5lMAjwhq2S1fpWNChlUCkBDrH6JREn8uEQk5UBHt/+jsBBV3RBKaOfKJhQlYf2do8Q97h7/qgkd86qSwur39I6tq4KDx3WPb1z67hL/H5Fa2kWA/Wv71266bspvp4V5r1e5H7GCOJd3LFlicx8o+uFMYB6xfDzJFnn0X5o6d+izKemQBuQnPBNaDFXA3VN/HlEQtmvxP/XRkToW0bAd/4BT5vf9sm+l+47GO6cX21bICtGF/j9hsbyF"

def unpack(s):
    return zlib.decompress(base64.b64decode(s))

def fmt_u8(data, per=16):
    vals = [f"0x{b:02X}" for b in data]
    return "\n".join("\t" + ", ".join(vals[i:i+per]) + "," for i in range(0, len(vals), per))

def fmt_u16le(data, per=8):
    vals = [f"0x{struct.unpack_from('<H', data, i)[0]:04X}" for i in range(0, len(data), 2)]
    return "\n".join("\t" + ", ".join(vals[i:i+per]) + "," for i in range(0, len(vals), per))

def replace_one(src, pattern, replacement, label):
    out, n = re.subn(pattern, replacement, src, count=1, flags=re.S)
    if n != 1:
        raise SystemExit(f"ERROR: expected exactly one {label} array, found {n}")
    return out

def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_mgba_sgb1_border.py PATH_TO_src/gb/video.c")
    p = Path(sys.argv[1])
    src = p.read_text(encoding="utf-8")
    if "ORIGINAL_SGB1_HOST_BORDER" in src:
        print("patch already present")
        return

    pal = unpack(PAL_Z)
    tm = unpack(TILEMAP_Z)
    char = unpack(CHARDATA_Z)
    if (len(pal), len(tm), len(char)) != (32, 1792, 2592):
        raise SystemExit(f"ERROR: bad embedded data lengths: {len(pal)}, {len(tm)}, {len(char)}")

    palette = (
        "/* ORIGINAL_SGB1_HOST_BORDER: exact 256x224 Super Game Boy 1 host frame */\n"
        "static const uint16_t _defaultBorderPalette[16] = {\n"
        + fmt_u16le(pal) + "\n};"
    )
    tilemap = "static const uint8_t _defaultBorderTilemap[] = {\n" + fmt_u8(tm) + "\n};"
    chardata = "static const uint8_t _defaultBorderChardata[] = {\n" + fmt_u8(char) + "\n};"

    src = replace_one(
        src,
        r"static const uint16_t _defaultBorderPalette\[16\]\s*=\s*\{.*?\n\};",
        palette,
        "_defaultBorderPalette",
    )
    src = replace_one(
        src,
        r"static const uint8_t _defaultBorderTilemap\[\]\s*=\s*\{.*?\n\};",
        tilemap,
        "_defaultBorderTilemap",
    )
    src = replace_one(
        src,
        r"static const uint8_t _defaultBorderChardata\[\]\s*=\s*\{.*?\n\};",
        chardata,
        "_defaultBorderChardata",
    )

    p.write_text(src, encoding="utf-8")
    print("Integrated original SGB1 host border")
    print("revision:", EXPECTED_REV)
    print("palette: 16 colors; tilemap: 1792 bytes; char data: 2592 bytes / 81 tiles")

if __name__ == "__main__":
    main()
