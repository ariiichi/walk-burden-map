"""地下鉄の線路・ホーム・地下通路・出入口を OpenStreetMap（Overpass API の JSON）から抽出し、
地図用の data/osm/subway.json を作る。build_bundle.py が data.js に同梱する。

使い方: python3 data/build_subway.py 取得したOSM.json
  取得クエリ例（範囲は南,西,北,東）:
    way["railway"="subway"]; way["railway"="platform"]; way["public_transport"="platform"];
    way["highway"~"footway|corridor|steps|elevator|pedestrian"]["level"]; way["indoor"="corridor"];
    node["railway"="subway_entrance"]; node["railway"="station"]; node["public_transport"="station"]
    → out body; >; out skel qt;

推測でホームや線路を作らない。OSMに無い駅・通路は「データなし」として扱う。
- 線路: 路線名（name）で色分け。tunnel/layer から地下・地上・高架を判定（layer は他の構造物との上下の順番で、深さのメートルではない）
- ホーム: level（階）タグをそのまま使う。路線はホームの名前・ref、無ければ最も近い線路（30m以内）から判定
- 地下通路: level 付きの歩道・通路・階段（地上の level=0 だけの道は除く）。駅から300m以内に限る
- 出入口→ホームの距離: 直線距離（構内の実際の歩行距離ではない）
"""
import json, math, sys
from pathlib import Path

D = Path(__file__).resolve().parent
els = json.load(open(sys.argv[1]))['elements']
nodes = {}
for x in els:  # 同じノードが「タグ付き」と「位置だけ（skel）」で2回出るため、タグ付きを優先する
    if x['type'] == 'node' and (x['id'] not in nodes or x.get('tags')): nodes[x['id']] = x
ways = [x for x in els if x['type'] == 'way']
pt = lambda i: [round(nodes[i]['lat'], 6), round(nodes[i]['lon'], 6)] if i in nodes and 'lat' in nodes[i] else None
def dist(a, b): return math.hypot((a[0] - b[0]) * 111000, (a[1] - b[1]) * 111000 * math.cos(math.radians(a[0])))
def seg_dist(p, a, b):
    # 点と線分の距離（メートル、平面近似）
    k = math.cos(math.radians(p[0]))
    ax, ay, bx, by, px, py = a[1] * k, a[0], b[1] * k, b[0], p[1] * k, p[0]
    dx, dy = bx - ax, by - ay
    t = 0 if dx == dy == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy)) * 111000
def line_dist(p, pts): return min(seg_dist(p, a, b) for a, b in zip(pts, pts[1:])) if len(pts) > 1 else dist(p, pts[0])
def centroid(pts): return [round(sum(q[0] for q in pts) / len(pts), 6), round(sum(q[1] for q in pts) / len(pts), 6)]

# 東京メトロ・都営地下鉄の路線色（各社の公式ラインカラー）
LINES = [('丸ノ内', '丸ノ内線', '#F62E36'), ('南北', '南北線', '#00AC9B'), ('半蔵門', '半蔵門線', '#8F76D6'), ('有楽町', '有楽町線', '#C1A470'),
         ('東西', '東西線', '#009BBF'), ('千代田', '千代田線', '#00BB85'), ('銀座', '銀座線', '#FF9500'), ('日比谷', '日比谷線', '#9CAEB7'),
         ('副都心', '副都心線', '#9C5E31'), ('三田', '三田線', '#0079C2'), ('大江戸', '大江戸線', '#B6007A'), ('新宿', '新宿線', '#6CBB5A'), ('浅草', '浅草線', '#E85298')]
REF = {'M': '丸ノ内線', 'N': '南北線', 'Z': '半蔵門線', 'Y': '有楽町線', 'T': '東西線', 'C': '千代田線', 'G': '銀座線', 'H': '日比谷線', 'F': '副都心線', 'I': '三田線', 'E': '大江戸線', 'S': '新宿線', 'A': '浅草線'}
COLOR = {n: c for _, n, c in LINES}
def line_of(text):
    for key, name, _ in LINES:
        if key in (text or ''): return name
    return None

tracks = []
for w in ways:
    t = w.get('tags', {})
    if t.get('railway') != 'subway': continue
    pts = [p for p in (pt(i) for i in w['nodes']) if p]
    name = line_of(t.get('name', '')) or line_of(t.get('line', ''))
    if len(pts) < 2: continue
    layer = int(t['layer']) if t.get('layer', '').lstrip('-').isdigit() else 0
    under = t.get('tunnel') in ('yes', 'building_passage') and layer <= 0 or layer < 0
    tracks.append({'id': w['id'], 'line': name, 'color': COLOR.get(name, '#777777'), 'layer': layer, 'under': bool(under),
                   'elevated': t.get('bridge') == 'yes' or layer > 0, 'points': pts})

stations = {}
for x in nodes.values():
    t = x.get('tags', {})
    if not t.get('name') or 'lat' not in x: continue
    if t.get('railway') == 'station' or t.get('public_transport') == 'station':
        if t.get('station') == 'subway' or t.get('subway') == 'yes' or any(k in (t.get('network', '') + t.get('operator', '')) for k in ['メトロ', '都営', 'Metro', 'Toei']) or (t.get('ref', '')[:1] in REF and t.get('ref', '')[1:].isdigit()):
            nm = t['name'].replace('ケ', 'ヶ') if False else t['name']
            stations.setdefault(nm, []).append({'pos': [round(x['lat'], 6), round(x['lon'], 6)], 'ref': t.get('ref'), 'line': REF.get((t.get('ref') or ' ')[0]) if (t.get('ref') or '')[1:2].isdigit() else line_of(t.get('network', '') + t.get('name:ja', '')), 'osm': x['id']})
station_pts = [(n, s['pos']) for n, ss in stations.items() for s in ss]
def near_station(p, r):
    best = min(station_pts, key=lambda s: dist(s[1], p)) if station_pts else None
    return best[0] if best and dist(best[1], p) <= r else None

platforms = []
for w in ways:
    t = w.get('tags', {})
    if not (t.get('railway') == 'platform' or t.get('public_transport') == 'platform'): continue
    if t.get('highway') == 'bus_stop' or t.get('bus') == 'yes': continue
    pts = [p for p in (pt(i) for i in w['nodes']) if p]
    if len(pts) < 2: continue
    c = centroid(pts)
    st = near_station(c, 350)
    if not st: continue
    line = line_of(t.get('name', '') + t.get('description', '') + t.get('line', ''))
    if not line and t.get('ref', '')[:1] in REF and t.get('ref', '')[1:2].isdigit(): line = REF[t['ref'][0]]
    if not line:  # 30m以内で最も近い地下鉄の線路
        cand = sorted(((line_dist(c, tr['points']), tr['line']) for tr in tracks if tr['line']), key=lambda z: z[0])
        if cand and cand[0][0] <= 30: line = cand[0][1]
    level = t.get('level')
    platforms.append({'id': w['id'], 'station': st, 'line': line, 'color': COLOR.get(line, '#777777'), 'level': level,
                      'closed': pts[0] == pts[-1], 'points': pts, 'name': t.get('name', ''), 'ref': t.get('ref', '')})

corridors = []
for w in ways:
    t = w.get('tags', {})
    if t.get('railway') in ('subway', 'platform') or t.get('public_transport') == 'platform': continue
    lv = t.get('level', '')
    if not (t.get('highway') in ('footway', 'corridor', 'steps', 'elevator', 'pedestrian') or t.get('indoor') == 'corridor'): continue
    if lv in ('', '0') and t.get('indoor') != 'corridor': continue
    pts = [p for p in (pt(i) for i in w['nodes']) if p]
    if len(pts) < 2 or not near_station(centroid(pts), 300): continue
    try: first = float(lv.split(';')[0])
    except ValueError: first = None
    corridors.append({'id': w['id'], 'level': lv, 'lvl': first, 'kind': t.get('highway') or 'corridor', 'points': pts})

entrances = []
for x in nodes.values():
    t = x.get('tags', {})
    if t.get('railway') != 'subway_entrance' or 'lat' not in x: continue
    p = [round(x['lat'], 6), round(x['lon'], 6)]
    st = near_station(p, 450)
    ref = t.get('ref') or ''
    name = t.get('name', '')
    # 出入口の名前に駅名があればそれを優先（隣の駅の代表点の方が近い場合の取り違え防止）
    for n in stations:
        if n and n in name: st = n
    if not st: continue
    near = {}
    for pf in platforms:
        if pf['station'] != st or not pf['line']: continue
        d0 = line_dist(p, pf['points'])
        if pf['line'] not in near or d0 < near[pf['line']]['m']: near[pf['line']] = {'m': round(d0 / 5) * 5, 'level': pf['level']}
    entrances.append({'id': x['id'], 'station': st, 'ref': ref, 'name': name, 'pos': p, 'level': t.get('level'),
                      'wheelchair': t.get('wheelchair'), 'elevator': t.get('highway') == 'elevator' or 'EV' in name or 'エレベーター' in name,
                      'to_platform': near})

# 駅ごとの上下の構造（ホームの階）。OSMの level の数字を「階」として扱う（1=地上1階、-1=地下1階）。
structure = {}
for st in sorted({p['station'] for p in platforms} | {e['station'] for e in entrances}):
    pf = [p for p in platforms if p['station'] == st]
    floors = {}
    for p in pf:
        if p['level'] is None or not p['line']: continue
        for lv in str(p['level']).split(';'):
            floors.setdefault(lv, set()).add(p['line'])
    lines_here = sorted({p['line'] for p in pf if p['line']} | {s['line'] for s in stations.get(st, []) if s.get('line')})
    structure[st] = {'floors': [{'level': k, 'lines': sorted(v)} for k, v in sorted(floors.items(), key=lambda kv: -float(kv[0]) if kv[0].lstrip('-').replace('.', '').isdigit() else 0)],
                     'lines': lines_here, 'platforms': len(pf), 'entrances': sum(1 for e in entrances if e['station'] == st),
                     'corridors': 0, 'pos': stations[st][0]['pos'] if st in stations else None}
for c in corridors:
    st = near_station(centroid(c['points']), 300)
    if st in structure: structure[st]['corridors'] += 1

out = {'source': 'OpenStreetMap（Overpass API、2026-10-13取得）', 'colors': COLOR, 'tracks': tracks, 'platforms': platforms,
       'corridors': corridors, 'entrances': entrances, 'structure': structure}
(D / 'osm' / 'subway.json').write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')))
print('tracks', len(tracks), 'platforms', len(platforms), 'corridors', len(corridors), 'entrances', len(entrances), 'stations', len(structure))
