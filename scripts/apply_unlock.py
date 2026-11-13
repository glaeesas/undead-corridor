from pathlib import Path
import gzip
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'Build' / 'undead-corridor-v26041701.data.unityweb'
TMP = Path('/tmp/undead_corridor.data')
OUT = Path('/tmp/undead_corridor_out')

TMP.write_bytes(gzip.decompress(SRC.read_bytes()))

import UnityPy

env = UnityPy.load(str(TMP))
level0 = None
for obj in env.objects:
    if obj.type.name == 'MonoBehaviour' and obj.path_id == 39:
        raw = obj.get_raw_data()
        if len(raw) >= 28 and raw[20:28] == (2692).to_bytes(8, 'little'):
            level0 = obj.assets_file
            break
if level0 is None:
    raise SystemExit('Could not locate GMSDK component')

overlay = next(obj for obj in env.objects if getattr(obj, 'assets_file', None) is level0 and obj.type.name == 'GameObject' and obj.path_id == 2)
raw = overlay.get_raw_data()
overlay.set_raw_data(raw[:-1] + b'\x00')

gmsoft = next(obj for obj in env.objects if getattr(obj, 'assets_file', None) is level0 and obj.type.name == 'GameObject' and obj.path_id == 3)
raw = gmsoft.get_raw_data()
count = struct.unpack('<I', raw[:4])[0]
components = []
for i in range(count):
    off = 4 + i * 12
    components.append((struct.unpack('<i', raw[off:off + 4])[0], struct.unpack('<q', raw[off + 4:off + 12])[0]))
components = [(fid, pid) for fid, pid in components if pid != 39]
rebuilt = struct.pack('<I', len(components))
for fid, pid in components:
    rebuilt += struct.pack('<i', fid) + struct.pack('<q', pid)
rebuilt += raw[4 + count * 12:]
gmsoft.set_raw_data(rebuilt)

if OUT.exists():
    for child in OUT.iterdir():
        child.unlink()
OUT.mkdir(parents=True, exist_ok=True)
env.save(pack='none', out_path=str(OUT))
files = [p for p in OUT.iterdir() if p.is_file()]
if not files:
    raise SystemExit('UnityPy produced no output file')
uncompressed = max(files, key=lambda p: p.stat().st_size).read_bytes()

compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
body = compressor.compress(uncompressed) + compressor.flush()
header = b'\x1f\x8b\x08\x18' + struct.pack('<I', 0) + b'\x02\x03'
header += b'build.data\x00'
header += b'UnityWeb Compressed Content (gzip)\x00'
footer = struct.pack('<II', zlib.crc32(uncompressed) & 0xffffffff, len(uncompressed) & 0xffffffff)
SRC.write_bytes(header + body + footer)

index = ROOT / 'index.html'
html = index.read_text()
tag = '<script id="gmsoft-jssdk" src="https://api.azgame.io/static/gmsdkv1.js"></script>'
if 'gmsoft-jssdk' not in html:
    html = html.replace('</head>', tag + '\n</head>')
    index.write_text(html)

print('Patched', SRC, SRC.stat().st_size, 'from', len(uncompressed), 'bytes')
