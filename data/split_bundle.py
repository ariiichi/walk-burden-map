"""道路・坂・出口を約1kmの区画に分割。build_area.pyから呼ぶ共通処理。"""
import json
import gzip
import math
from pathlib import Path

D = Path(__file__).resolve().parent
# 緯度約1km、東京で経度約1km。地物は区画と交わる線分ごとに保存。
DY, DX = .009, .011

def read(name):
    return json.loads((D / name).read_text())

def write_bytes(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.tmp')
    temporary.write_bytes(value)
    temporary.replace(path)

def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n'
    write_bytes(path,text.encode())
    return len(text.encode())

def cell(p):
    return math.floor(p[0] / DY), math.floor(p[1] / DX)

def bounds(key):
    y, x = key
    return [[round(y * DY, 8), round(x * DX, 8)], [round((y + 1) * DY, 8), round((x + 1) * DX, 8)]]

def clip(a, b, box):
    """Liang–Barsky。区画を横切る長い線分も欠落させない。"""
    lo, hi = 0., 1.
    for i in (0, 1):
        delta = b[i] - a[i]
        if abs(delta) < 1e-14:
            if not box[0][i] <= a[i] <= box[1][i]:
                return None
        else:
            u, v = (box[0][i] - a[i]) / delta, (box[1][i] - a[i]) / delta
            lo, hi = max(lo, min(u, v)), min(hi, max(u, v))
            if hi <= lo:
                return None
    return [[round(a[i] + t * (b[i] - a[i]), 7) for i in (0, 1)] for t in (lo, hi)]

def partition(data):
    chunks = {}
    def chunk(k):
        return chunks.setdefault(k, {name: [] for name in ('roads', 'context', 'boundaries', 'slopes', 'stations', 'subplatforms', 'subcorridors', 'subentrances')})
    for kind in ('roads', 'context', 'boundaries', 'slopes', 'subplatforms', 'subcorridors'):
        for index, item in enumerate(data.get(kind, [])):
            pts = item['points']
            if not pts:
                continue
            if kind == 'context' and item['kind'] != 'rail':
                # 閉じた面は形状を変えず、その外接矩形に重なる区画へ。画面側でID重複除去。
                a, b = cell([min(p[0] for p in pts), min(p[1] for p in pts)]), cell([max(p[0] for p in pts), max(p[1] for p in pts)])
                for y in range(a[0], b[0] + 1):
                    for x in range(a[1], b[1] + 1):
                        chunk((y, x))[kind].append({**item, '_key': f'{kind}:{index}'})
                continue
            fragments = {}
            for a, b in zip(pts, pts[1:]):
                low = cell([min(a[0], b[0]), min(a[1], b[1])])
                high = cell([max(a[0], b[0]), max(a[1], b[1])])
                for y in range(low[0], high[0] + 1):
                    for x in range(low[1], high[1] + 1):
                        k = (y, x)
                        segment = clip(a, b, bounds(k))
                        if segment:
                            paths = fragments.setdefault(k, [])
                            if paths and paths[-1][-1] == segment[0]:
                                paths[-1].append(segment[1])
                            else:
                                paths.append(segment)
            for k, paths in fragments.items():
                for n, path in enumerate(paths):
                    chunk(k)[kind].append({**item, 'points': path, '_key': f'{kind}:{index}:{k}:{n}'})
    for kind in ('stations','subentrances'):
        for item in data.get(kind, []):
            chunk(cell(item['pos']))[kind].append(item)
    entries = []
    for (y, x), value in sorted(chunks.items()):
        name = f'{y}_{x}'
        path = D / 'areas' / f'{name}.json'
        size = write(path, value)
        if size > 3_000_000:
            raise ValueError(f'{path} is too large: {size}')
        entries.append({'id': name, 'bounds': bounds((y, x)), 'url': f'data/areas/{name}.json', 'bytes': size})
    current_ids={e['id'] for e in entries}
    for old in (D/'areas').glob('*.json'):
        if old.stem not in current_ids:old.unlink() # 自動生成した未参照区画だけを片付ける
    write(D / 'area-index.json', {'version': 1, 'grid': {'lat': DY, 'lon': DX}, 'areas': entries})
    return entries

def bootstrap():
    """現行駅索引と線路概観から起動用データだけを作る。区画・駅は更新しない。"""
    stations = read('station-index.json')['stations']
    positions = [s['pos'] for s in stations]
    subway = read('osm/subway.json')
    value = {'bounds': [[min(p[i] for p in positions) for i in (0, 1)],
                        [max(p[i] for p in positions) for i in (0, 1)]],
             'roads': [], 'context': [], 'boundaries': [], 'stations': [],
             'slopes': {'slopes': []},
             'subway': {**subway, 'platforms': [], 'corridors': [], 'entrances': []},
             'areaIndex': 'data/area-index.json', 'stationIndex': 'data/station-index.json'}
    write_bytes(D.parent/'data.js', ('window.MAP_DATA = '+json.dumps(value, ensure_ascii=False, separators=(',', ':'))+';\n').encode())


def build():
    # 駅別の計算済み入力を統合し、同じOSM道路区間を重複表示しない。
    active_ids = {s['id'] for s in read('station-index.json')['stations']}
    roads, slopes, stations = {}, {}, {}
    for path in sorted(list((D/'processed').glob('*.json')) + list((D/'processed').glob('*.json.gz'))):
        value = json.loads(gzip.decompress(path.read_bytes()) if path.suffix == '.gz' else path.read_text())
        roads.update({r['id']: r for r in value.get('roads', [])})
        for slope in value.get('slopes', []):
            slopes[json.dumps([slope['road'], slope['points']], sort_keys=True)] = slope
        if path.name.removesuffix('.gz').removesuffix('.json') in active_ids:
            for station in value.get('exits', []):
                stations[station.get('source', station['name'])] = station
    subway = read('osm/subway.json')
    entries = partition({'roads': list(roads.values()), 'slopes': list(slopes.values()),
                         'stations': list(stations.values()), 'subplatforms': subway['platforms'],
                         'subcorridors': subway['corridors'], 'subentrances': subway['entrances']})
    bootstrap()
    print(f'分割 {len(entries)}区画 / 最大 {max(e["bytes"] for e in entries):,} bytes / data.js {(D.parent / "data.js").stat().st_size:,} bytes')


if __name__ == '__main__':
    build()
