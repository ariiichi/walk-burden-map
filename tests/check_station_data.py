"""データの来歴・形状保存・同梱資産を通信なしで確認する。"""
import hashlib
import io
import json
import math
import re
import sys
from http.server import SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'data'))
from station_geometry import levels


def read(path):
    return json.loads((ROOT / path).read_text())


index = read('data/station-index.json')['stations']
catalog = read('data/station-list.json')['stations']
assert len(index) == len(catalog) == 96
assert {s['id'] for s in index} == {s['id'] for s in catalog}
assert levels('-1;-3') == [-1, -3]
assert levels('') == levels(None) == levels('-3--1') == []
features = 0
for station in index:
    data = read(station['url'])
    assert data['stations'][0]['name'] == station['name']
    assert len({f['id'] for f in data['features']}) == len(data['features'])
    for feature in data['features']:
        props = feature['properties']
        assert props['station'] == station['name']
        assert props['level_raw'] == props['original_tags'].get('level')
        if props.get('level_method') != 'osm_surface_track_schematic':
            assert props['levels'] == levels(props['level_raw'])
        geom = feature['geometry']
        coords = geom['coordinates']
        if geom['type'] == 'Point': coords = [coords]
        elif geom['type'] == 'Polygon': coords = [p for ring in coords for p in ring]
        assert geom['type'] in ('Point', 'LineString', 'Polygon')
        assert all(len(p) == 2 and all(math.isfinite(v) for v in p) for p in coords)
        features += 1

# ソケットを開かず、標準HTTPハンドラで同梱ファイルの応答を調べる。
class MemoryConnection:
    def __init__(self, path):
        self.input = io.BytesIO(f'GET /{path} HTTP/1.0\r\n\r\n'.encode())
        self.output = bytearray()

    def makefile(self, *args, **kwargs):
        return self.input

    def sendall(self, content):
        self.output.extend(content)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


html = (ROOT / 'index.html').read_text()
paths = re.findall(r'(?:src|href)="([^"#]+)"', html)
paths += ['data/station-index.json', 'data/station-list.json', 'data/area-index.json', 'README.md']
paths += [s['url'] for s in index]
for path in paths:
    if '://' in path:
        continue
    request = MemoryConnection(path)
    QuietHandler(request, ('127.0.0.1', 0), None, directory=str(ROOT))
    assert bytes(request.output).startswith(b'HTTP/1.0 200 '), path
print(f'PASS: {len(index)}駅・{features}地物の形状・階タグ・欠測、同梱資産のHTTPハンドラ応答')
