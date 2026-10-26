"""駅リスト→OSM道路・構内→GSI標高・勾配→区画/駅JSONを作る唯一の入口。

python data/build_area.py --discover                 # 対象駅をOSMから判定
python data/build_area.py --stations-file data/station-list.json
python data/build_area.py --stations 東京 渋谷 # 登録済み駅を追加/再開
python data/build_area.py --rebuild                  # 保存済み入力で再生成
numpy / Pillow が必要。OSM生JSONはgzip（内容は無変更）、DEMは原PNGを保存。
Overpassは直列・最小10秒間隔。失敗・途中停止後も保存済み駅を再利用する。
公式構内図の参照・形状補完・階の推測はしない。近接による駅所属は画面に明記。
"""
import argparse
import datetime as dt
import fcntl
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import subprocess
import time
import urllib.parse
from functools import lru_cache
import numpy as np
from PIL import Image
from split_bundle import D, write, write_bytes, read, build as split_build
from station_geometry import levels, distance

RAW = D / 'raw/expansion'
ENDPOINT = 'https://maps.mail.ru/osm/tools/overpass/api/interpreter'
OVERPASS_METHOD = 'POST'
HEADERS = ['-H', 'User-Agent: WalkBurdenMap/1.0 (static public geography project)']
LINE_NAMES = {'M':'丸ノ内線','Z':'半蔵門線','G':'銀座線','H':'日比谷線','T':'東西線','C':'千代田線','Y':'有楽町線','N':'南北線','F':'副都心線'}
LINE_NAMES.update({'A':'浅草線','I':'三田線','S':'新宿線','E':'大江戸線'})
LINE_NAMES.update({'JY':'JR山手線','JB':'JR中央・総武線','JC':'JR中央線快速'})


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def log(message):
    print(message, flush=True)


def overpass(label, query, endpoint=ENDPOINT):
    # 再開・接続先切替で二つ起動しても、原入力と問い合わせ間隔を競合させない。
    RAW.mkdir(parents=True, exist_ok=True)
    # 成功入力は原子的に保存され、以後は変更しない。通信の待機中も
    # 保存済み入力だけの再生成は進められるよう、読み出しは排他の外に置く。
    if (RAW/f'{label}.json.gz').exists():return _overpass(label,query,endpoint)
    with (RAW/'overpass.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        return _overpass(label,query,endpoint)


def _overpass(label, query, endpoint):
    RAW.mkdir(parents=True, exist_ok=True)
    target = RAW / f'{label}.json.gz'
    qfile = RAW / f'{label}.overpass'
    if target.exists():
        signature=lambda q:re.sub(r'\[(?:timeout|maxsize):[^\]]+\]','',q).strip()
        if signature(qfile.read_text()) != signature(query):
            raise ValueError(f'保存済みクエリと不一致: {label}。別ラベルで取得してください。')
        return json.loads(gzip.decompress(target.read_bytes()))
    # プロセスを再開しても直前の問い合わせから間隔を空ける。
    stamp = RAW / 'last-request.txt'
    if stamp.exists():
        time.sleep(max(0, 10 - (time.time() - float(stamp.read_text()))))
    if qfile.exists() and qfile.read_text()!=query:
        with (RAW/'attempts.jsonl').open('a') as f:f.write(json.dumps({'at':now(),'label':label,'previous_query':qfile.read_text(),'previous_metadata':json.loads((RAW/f'{label}.metadata.json').read_text()) if (RAW/f'{label}.metadata.json').exists() else None},ensure_ascii=False)+'\n')
    qfile.write_text(query)
    stamp.write_text(str(time.time()))
    command = ['curl', '--fail-with-body', '-L', '-sS', '--compressed', '--connect-timeout', '15', '--max-time', '90', *HEADERS, '-w', '\n%{http_code}', endpoint]
    if OVERPASS_METHOD=='GET':command.append('-G')
    command.extend(['--data-urlencode', f'data@{qfile}'])
    started=time.monotonic()
    result = subprocess.run(command, capture_output=True)
    body,_,code=result.stdout.rpartition(b'\n')
    meta = {'retrieved_at': now(), 'endpoint': endpoint, 'query_file': qfile.name, 'command_exit': result.returncode, 'method': OVERPASS_METHOD,'http_status':int(code) if code.isdigit() else 0,'duration_seconds':round(time.monotonic()-started,2)}
    try:
        if result.returncode:
            raise RuntimeError(result.stderr.decode(errors='replace'))
        obj = json.loads(body)
        if obj.get('remark') or 'elements' not in obj:
            raise RuntimeError(obj.get('remark', 'elementsなし'))
    except Exception as e:
        meta['error'] = str(e)
        if body:meta['response_excerpt']=body[:1000].decode(errors='replace')
        write(RAW / f'{label}.metadata.json', meta)
        with (RAW/'attempts.jsonl').open('a') as f:f.write(json.dumps({**meta,'query':query},ensure_ascii=False)+'\n')
        backoff_path=RAW/'capacity-backoff.json'
        backoffs=json.loads(backoff_path.read_text()) if backoff_path.exists() else {}
        failures=backoffs.get(endpoint,0)+1
        backoffs[endpoint]=failures;write(backoff_path,backoffs)
        delay=min(300,30*2**min(failures-1,4))
        stamp.write_text(str(time.time()+delay-10))
        log(f'Overpass待機：次回取得まで最低{delay}秒（接続先の連続失敗{failures}回）')
        raise RuntimeError(f'Overpass失敗 {label}: {e}')
    meta.update({'sha256_uncompressed': hashlib.sha256(body).hexdigest(), 'osm_base': obj.get('osm3s', {}), 'bytes_uncompressed': len(body)})
    write(RAW / f'{label}.metadata.json', meta)
    write_bytes(target,gzip.compress(body,mtime=0))
    # 長い問い合わせの直後にも間隔を確保する。開始時刻だけでは連続実行になる。
    stamp.write_text(str(time.time()))
    backoff_path=RAW/'capacity-backoff.json'
    if backoff_path.exists():
        backoffs=json.loads(backoff_path.read_text());backoffs.pop(endpoint,None);write(backoff_path,backoffs)
    return obj


def normalized(name):
    return name.removesuffix('駅').replace('ヶ', 'ケ')


def point(e):
    if 'lat' in e: return [e['lat'], e['lon']]
    if 'center' in e: return [e['center']['lat'], e['center']['lon']]
    geom = e.get('geometry', [])
    if geom: return [sum(p[k] for p in geom) / len(geom) for k in ('lat', 'lon')]
    if e['type']=='relation':
        geom=[p for m in e.get('members',[]) if m.get('role')=='outer' for p in m.get('geometry',[]) if p and 'lat' in p]
        if geom:return [sum(p[k] for p in geom)/len(geom) for k in ('lat','lon')]


def inside(p, polygon):
    y, x = p
    result = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        if (a[0] > y) != (b[0] > y) and x < (b[1] - a[1]) * (y - a[0]) / (b[0] - a[0]) + a[1]: result = not result
    return result


def discover(endpoint):
    query = '[out:json][timeout:120];\n(rel(443282);rel(443279);rel["route"="train"]["ref"="JY"];)->.routes;\n.routes out body;\nnode(r.routes:"stop");out body;\nway(r.routes:"platform");out center;\n'
    obj = overpass('discovery', query, endpoint)
    elements = {(e['type'], e['id']): e for e in obj['elements']}
    routes = [e for e in obj['elements'] if e['type'] == 'relation']
    loops = [r for r in routes if r['tags'].get('route') == 'train' and len([m for m in r['members'] if m.get('role') == 'stop']) >= 29]
    if not loops: raise RuntimeError('山手線の停止点を取得できません。範囲を推測しません。')
    loop = max(loops, key=lambda r: len(r['members']))
    polygon = [point(elements[(m['type'], m['ref'])]) for m in loop['members'] if m.get('role') == 'stop' and (m['type'], m['ref']) in elements]
    # ループの停止点を結ぶ近似多角形。境界駅は駅名一致で採用。線路の曲線との差を記録する。
    boundary_names = {normalized(elements[(m['type'], m['ref'])].get('tags', {}).get('name', '')) for m in loop['members'] if m.get('role') == 'stop' and (m['type'], m['ref']) in elements}
    selected, excluded = {}, []
    for rid, line in [(443282, '丸ノ内線'), (443279, '半蔵門線')]:
        route = elements[('relation', rid)]
        for position,member in enumerate(route['members']):
            if member.get('role') != 'stop': continue
            e = elements.get((member['type'], member['ref']))
            if not e: raise RuntimeError(f'停止点が欠落: {member}')
            name, pos = normalized(e.get('tags', {}).get('name', '')), point(e)
            if not name or pos is None: raise RuntimeError(f'駅名/位置なし: {e}')
            include = inside(pos, polygon) or name in boundary_names
            if not include:
                excluded.append({'name': name, 'line': line, 'pos': pos, 'reason': '山手線停止点多角形の外側'})
                continue
            row = selected.setdefault(name, {'id': f'osm-{e["id"]}', 'name': name, 'pos': pos, 'lines': [], 'osm_stop': e['id']})
            if line not in row['lines']: row['lines'].append(line)
            row.setdefault('orders',{})[line]=position
            row['scope'] = '山手線上（駅名照合）' if name in boundary_names else '山手線内（停止点多角形）'
    for rid,line in [(443282,'丸ノ内線'),(443279,'半蔵門線')]:
        route=elements[('relation',rid)]
        stop_names={normalized(elements[(m['type'],m['ref'])].get('tags',{}).get('name','')) for m in route['members'] if m.get('role')=='stop' and (m['type'],m['ref']) in elements}
        for terminal in (route['tags']['from'],route['tags']['to']):
            if any(n==normalized(terminal) or n.startswith(normalized(terminal)+'〈') or n.startswith(normalized(terminal)+'（') for n in stop_names):continue
            q=f'[out:json][timeout:45];node["railway"="station"]["name"="{terminal}"];out body;'
            label='terminal-ikebukuro' if terminal=='池袋' else 'terminal-'+str(rid)+'-'+terminal
            supplement=overpass(label,q,endpoint)
            candidates=[e for e in supplement['elements'] if e.get('tags',{}).get('station')=='subway' and e.get('tags',{}).get('ref','').startswith(route['tags']['ref'])]
            if len(candidates)!=1:raise RuntimeError(f'欠落した端駅を一意に照合できません: {terminal}')
            e=candidates[0];name=normalized(terminal);pos=point(e)
            if inside(pos,polygon) or name in boundary_names:
                selected[name]={'id':f'osm-{e["id"]}','name':name,'pos':pos,'lines':[line],'orders':{line:len(route['members'])},'osm_station':e['id'],'scope':'山手線上（駅名照合）' if name in boundary_names else '山手線内（停止点多角形）','discovery_note':'routeのstop欠落。from/toタグと同名・同路線refのOSM駅ノードで照合。'}
    value = {'source': 'OSM Overpass route 443282/443279・山手線route', 'boundary_method': '山手線の順序付き停止点を結ぶ多角形＋同名境界駅。線路の曲線・駅施設の敷地境界ではない。', 'yamanote_relation': loop['id'], 'boundary': polygon, 'stations': list(selected.values()), 'excluded': excluded}
    write(D / 'raw/expansion/metro-core-stations.json', value)
    log(f'対象駅をOSMから判定：{len(selected)}駅、対象外{len(excluded)}駅。山手線relation {loop["id"]}')
    return value


class Elevations:
    def __init__(self):
        self.memo = {}
        self.used = set()
        self.failures = []
        (RAW / 'dem').mkdir(parents=True, exist_ok=True)

    def tile(self, kind, z, x, y):
        key = f'{kind}/{z}/{x}/{y}'
        self.used.add(key)
        if key in self.memo: return self.memo[key]
        path = RAW / 'dem' / f'{kind}_{z}_{x}_{y}.png'
        meta_path = path.with_suffix('.metadata.json')
        if not path.exists() and (not meta_path.exists() or json.loads(meta_path.read_text()).get('http_status')!=404):
            url = f'https://cyberjapandata.gsi.go.jp/xyz/{key}.png'
            result = subprocess.run(['curl', '-L', '-sS', '--max-time', '30', *HEADERS, '-w', '\n%{http_code}', url], capture_output=True)
            body, _, code = result.stdout.rpartition(b'\n')
            status = int(code) if code.isdigit() else 0
            meta = {'url': url, 'retrieved_at': now(), 'http_status': status}
            if status == 200 and body.startswith(b'\x89PNG'):
                meta['sha256'] = hashlib.sha256(body).hexdigest()
                write(meta_path, meta)
                write_bytes(path,body)
            elif status == 404:
                write(meta_path, meta)
            else:
                self.failures.append({'tile': key, 'status': status})
                # 一時障害を永久的な「データなし」として保存しない。
            time.sleep(.08)
        if not path.exists():
            self.memo[key] = None
            return None
        array = np.array(Image.open(path).convert('RGB'), dtype=np.int64)
        v = array[..., 0] * 65536 + array[..., 1] * 256 + array[..., 2]
        h = np.where(v < 2**23, v*.01, (v-2**24)*.01).astype(float)
        h[v == 2**23] = np.nan
        self.memo[key] = h
        return h

    def sample(self, lat, lon, kind, z):
        n = 2**z
        px = (lon + 180) / 360 * n * 256 - .5
        py = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n * 256 - .5
        x0, y0 = math.floor(px), math.floor(py)
        fx, fy = px-x0, py-y0
        result = 0
        for dx, dy, w in [(0,0,(1-fx)*(1-fy)),(1,0,fx*(1-fy)),(0,1,(1-fx)*fy),(1,1,fx*fy)]:
            if w == 0: continue
            x,y=x0+dx,y0+dy
            tile = self.tile(kind,z,x//256,y//256)
            if tile is None or np.isnan(tile[y%256,x%256]): return None
            result += float(tile[y%256,x%256])*w
        return result

    def get(self, pos):
        for kind,z,src in [('dem1a_png',17,'DEM1A（1m）'),('dem5a_png',15,'DEM5A（5m）')]:
            h = self.sample(*pos, kind,z)
            if h is not None: return {'h': round(h,2), 'src': src, 'method': '国土地理院標高タイルの双線形補間（地表）'}
        return {'h': None, 'src': '未取得/欠測'}


def densify(points):
    result = [points[0]]
    for a,b in zip(points,points[1:]):
        n=max(1,math.ceil(distance(a,b)/5))
        result.extend([[a[i]+(b[i]-a[i])*k/n for i in (0,1)] for k in range(1,n+1)])
    return result


def slopes_for(roads, dem):
    slopes=[];sampled=missing=excluded=short=0;computed_roads=[]
    show={'trunk','primary','secondary','tertiary','unclassified','residential','living_street','pedestrian'}
    for r in roads:
        t=r['tags']
        if (r['kind'] not in show and not (r['name'] and r['kind'] in ('footway','path'))) or any(t.get(k) not in (None,'no','0') for k in ('bridge','tunnel','indoor','covered','layer')):
            excluded+=1;continue
        pts=densify(r['points'])
        if len(pts)<5:
            short+=1;continue
        hs=[dem.get(p)['h'] for p in pts]
        if None in hs:
            missing+=1;continue
        sampled+=1;computed_roads.append(r['id'])
        hs=np.convolve(np.pad(hs,2,mode='edge'),np.ones(5)/5,mode='valid')
        i=0
        while i<len(pts)-1:
            j,run=i,0
            while j<len(pts)-1 and run<20:
                run+=distance(pts[j],pts[j+1]);j+=1
            if run>=12:
                g=float((hs[j]-hs[i])/run*100)
                limit=12 if r['kind'] in ('trunk','primary','secondary') else 25
                if 4<=abs(g)<=limit:
                    slopes.append({'road':r['id'],'name':r['name'],'g':round(abs(g),1),'rise':round(abs(float(hs[j]-hs[i])),1),'len':round(run),'points':[[round(a,6),round(b,6)] for a,b in pts[i:j+1]],'up':[pts[i],pts[j]] if g>0 else [pts[j],pts[i]],'source':'国土地理院 DEM1A/DEM5A × OSM'})
            i=j
    return slopes, {'sampled_roads':sampled,'missing_roads':missing,'excluded_roads':excluded,'short_roads':short,'slope_segments':len(slopes),'computed_road_ids':computed_roads}


def station_query(station, box=None):
    lat,lon=station['pos']
    dy=800/111000;dx=800/(111000*math.cos(math.radians(lat)))
    bbox=','.join(f'{v:.7f}' for v in box) if box else f'{lat-dy:.7f},{lon-dx:.7f},{lat+dy:.7f},{lon+dx:.7f}'
    return f'''[out:json][timeout:10][maxsize:67108864][bbox:{bbox}];
(way["highway"];node["railway"~"^(station|subway_entrance|platform)$"];way["railway"="station"];way["railway"="platform"];nwr["public_transport"="platform"];node["highway"="elevator"];node["barrier"="ticket_gate"];);
out body geom;
'''


def station_box(station):
    lat,lon=station['pos'];dy=800/111000;dx=800/(111000*math.cos(math.radians(lat)))
    return [float(f'{v:.7f}') for v in (lat-dy,lon-dx,lat+dy,lon+dx)]


def facilities_query(box):
    bbox=','.join(f'{v:.7f}' for v in box)
    selectors=['node["railway"~"^(station|subway_entrance|platform)$"]','way["railway"~"^(station|platform)$"]','node["public_transport"="platform"]','way["public_transport"="platform"]','node["highway"="elevator"]','node["barrier"="ticket_gate"]']
    return '[out:json][timeout:10][maxsize:67108864][bbox:'+bbox+'];('+''.join(s+';' for s in selectors)+');out body geom;\n'


def shared_facilities(stations,endpoint,label='metro-shared-facilities'):
    boxes=[station_box(s) for s in stations]
    box=[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]
    try:overpass(label,facilities_query(box),endpoint)
    except RuntimeError as error:log(f'共通施設入力の取得未了（駅別取得へ切替）：{error}');return None
    return label,box


def fetch_elements(station,endpoint,shared=None):
    box=station_box(station);bbox=','.join(f'{v:.7f}' for v in box)
    reused=reuse_covering_sources(station,roads_only=True) if not (RAW/f'{station["id"]}-roads.json.gz').exists() else None
    queries=[] if reused else [(station['id']+'-roads','[out:json][timeout:10][maxsize:67108864];way["highway"]('+bbox+');out body geom;\n')]
    if shared and all(shared[1][i]<=box[i] for i in (0,1)) and all(shared[1][i]>=box[i] for i in (2,3)):
        queries.append((shared[0],(RAW/(shared[0]+'.overpass')).read_text()))
    else:queries.append((station['id']+'-facilities',facilities_query(box)))
    elements={(e['type'],e['id']):e for e in reused['elements']} if reused else {}
    sources=list(reused['_raw_labels']) if reused else []
    for label,query in queries:
        obj=overpass(label,query,endpoint);sources.append(label)
        for e in obj['elements']:
            coords=[e] if e['type']=='node' else e.get('geometry',[])
            if any(p and 'lat' in p and box[0]<=p['lat']<=box[2] and box[1]<=p['lon']<=box[3] for p in coords):elements[e['type'],e['id']]=e
    return {'elements':list(elements.values()),'_raw_labels':sources}


def reuse_covering_sources(station,roads_only=False):
    """矩形全体を既存の成功入力で覆える場合だけ、追加通信なしで再利用する。"""
    lat,lon=station['pos'];dy=800/111000;dx=800/(111000*math.cos(math.radians(lat)))
    south,west,north,east=[float(f'{v:.7f}') for v in (lat-dy,lon-dx,lat+dy,lon+dx)]
    candidates=[]
    for qfile in sorted(RAW.glob('osm-*.overpass')):
        label=qfile.stem
        if not (RAW/f'{label}.json.gz').exists():continue
        query=qfile.read_text()
        # 全種別入力か道路専用入力かを区別し、施設のない原入力で施設を充足しない。
        if roads_only:
            if 'way["highway"]' not in query:continue
        elif 'way["highway"];' not in query or 'nwr["public_transport"="platform"]' not in query:continue
        match=re.search(r'\[bbox:([\d.,-]+)\]',query)
        if not match and roads_only:match=re.search(r'way\["highway"\]\(([\d.,-]+)\)',query)
        if not match:continue
        a,b,c,d=map(float,match.group(1).split(','))
        if c>south and a<north and d>west and b<east:
            candidates.append((label,(a,b,c,d)))
    if not candidates:return None
    ys=sorted({south,north}|{v for _,box in candidates for v in (box[0],box[2]) if south<v<north})
    xs=sorted({west,east}|{v for _,box in candidates for v in (box[1],box[3]) if west<v<east})
    selected=set()
    for y1,y2 in zip(ys,ys[1:]):
        for x1,x2 in zip(xs,xs[1:]):
            y,x=(y1+y2)/2,(x1+x2)/2
            covering=[(label,box) for label,box in candidates if box[0]<=y<=box[2] and box[1]<=x<=box[3]]
            if not covering:return None # わずかな未取得部分も補完しない
            selected.add(min(covering,key=lambda item:(item[0] not in selected,abs((item[1][0]+item[1][2])/2-lat)+abs((item[1][1]+item[1][3])/2-lon),item[0]))[0])
    # 元の矩形クエリと同じく、範囲内のnode／頂点を持つwayを採る。形状は切らない。
    elements={}
    sources=sorted(selected,key=lambda label:read(f'raw/expansion/{label}.metadata.json')['retrieved_at'])
    for label in sources:
        obj=json.loads(gzip.decompress((RAW/f'{label}.json.gz').read_bytes()))
        for e in obj['elements']:
            if roads_only and not (e['type']=='way' and e.get('tags',{}).get('highway')):continue
            coords=[e] if e['type']=='node' else e.get('geometry',[])
            if any(p and 'lat' in p and south<=p['lat']<=north and west<=p['lon']<=east for p in coords):elements[e['type'],e['id']]=e
    log(f'原入力再利用：{station["name"]}の{"道路" if roads_only else "全種別"}取得矩形全体を既存{len(sources)}入力で確認（追加OSM通信なし）')
    return {'elements':list(elements.values()),'_raw_labels':sources}


def fetch_station(station,endpoint,split=False,shared=None,elements_only=False):
    # 共通施設で生成した駅も、通常の再開・--rebuildで同じ原入力を使う。
    if shared is None:
        for label in ('toei-shared-facilities','jr-shared-facilities','metro-shared-facilities'):
            if not (RAW/(label+'.json.gz')).exists():continue
            query=(RAW/(label+'.overpass')).read_text()
            match=re.search(r'\[bbox:([\d.,-]+)\]',query)
            if match:
                box=list(map(float,match.group(1).split(',')));own=station_box(station)
                if all(box[i]<=own[i] for i in (0,1)) and all(box[i]>=own[i] for i in (2,3)):
                    shared=(label,box);break
    labels=[station['id']+'-'+suffix for suffix in ('sw','se','nw','ne')]
    has_parts=any(RAW.glob(station['id']+'-*.json.gz'))
    has_elements=any((RAW/f'{station["id"]}-{kind}.json.gz').exists() for kind in ('roads','facilities'))
    if not split and not (RAW/f'{station["id"]}.json.gz').exists() and (has_elements or ((elements_only or shared) and not has_parts)):
        reused=reuse_covering_sources(station)
        return reused if reused is not None else fetch_elements(station,endpoint,shared)
    if not split and not (RAW/f'{station["id"]}.json.gz').exists() and not has_parts:
        reused=reuse_covering_sources(station)
        if reused is not None:return reused
    if not split and ((RAW/f'{station["id"]}.json.gz').exists() or not has_parts):
        return overpass(station['id'],station_query(station),endpoint)
    lat,lon=station['pos'];dy=800/111000;dx=800/(111000*math.cos(math.radians(lat)))
    boxes=[(lat-dy,lon-dx,lat,lon),(lat-dy,lon,lat,lon+dx),(lat,lon-dx,lat+dy,lon),(lat,lon,lat+dy,lon+dx)]
    own=station_box(station)
    shared_covers=shared and all(shared[1][i]<=own[i] for i in (0,1)) and all(shared[1][i]>=own[i] for i in (2,3))
    elements={};failures=[];sources=[]
    for label,box in zip(labels,boxes):
        if (RAW/f'{label}.json.gz').exists():
            # 保存済みの全種類の入力を保持。道路・施設を分けた新規取得と同じ要素区分を含む。
            saved_query=(RAW/f'{label}.overpass').read_text()
            expected=','.join(f'{v:.7f}' for v in box)
            if f'[bbox:{expected}]' not in saved_query:raise RuntimeError(f'保存済み区画の範囲が不一致: {label}')
            queries=[(label,saved_query)]
        else:
            bbox=','.join(f'{v:.7f}' for v in box)
            head='[out:json][timeout:10][maxsize:67108864];'
            roads=f'{head}way["highway"]({bbox});out body geom;\n'
            selectors=['node["railway"~"^(station|subway_entrance|platform)$"]','way["railway"~"^(station|platform)$"]','node["public_transport"="platform"]','way["public_transport"="platform"]','node["highway"="elevator"]','node["barrier"="ticket_gate"]']
            facilities=head+'('+''.join(selector+'('+bbox+');' for selector in selectors)+');out body geom;\n'
            # 構内描画で処理しないrelationを問い合わせず、道路と施設を分けて小さくする。
            queries=[(label+'-roads',roads)] if shared_covers else [(label+'-roads',roads),(label+'-facilities',facilities)]
        for source_label,query in queries:
            try:obj=overpass(source_label,query,endpoint)
            except RuntimeError as error:
                log(str(error));failures.append(source_label);continue
            sources.append(source_label)
            for e in obj['elements']:elements[(e['type'],e['id'])]=e
    if failures:raise RuntimeError('分割取得が未了：'+ '・'.join(failures))
    if shared_covers:
        # 施設は駅全体を覆う成功入力を再利用し、各小矩形で取り直さない。
        obj=overpass(shared[0],(RAW/(shared[0]+'.overpass')).read_text(),endpoint)
        sources.append(shared[0])
        for e in obj['elements']:
            coords=[e] if e['type']=='node' else e.get('geometry',[])
            if any(p and 'lat' in p and own[0]<=p['lat']<=own[2] and own[1]<=p['lon']<=own[3] for p in coords):
                elements[e['type'],e['id']]=e
    return {'elements':list(elements.values()),'_raw_labels':sources}


@lru_cache(maxsize=4)
def rail_context(raw_directory):
    path=Path(raw_directory)/'jr-platform-tracks.json.gz'
    if not path.exists():return []
    return json.loads(gzip.decompress(path.read_bytes()))['elements']


def platform_relation_geometry(element, way_lookup=None):
    """OSMの端点が一致するwayだけを結合。欠けた輪郭・不明な穴は補わない。"""
    if element.get('tags',{}).get('type')!='multipolygon':return None
    rings={}
    for role in ('outer','inner'):
        parts=[]
        for member in element.get('members',[]):
            if member.get('role')!=role:continue
            gs=member.get('geometry') or (way_lookup or {}).get(member['ref'],{}).get('geometry',[])
            if member['type']!='way' or len(gs)<2 or any(not g or 'lat' not in g or 'lon' not in g for g in gs):return None
            parts.append([[g['lon'],g['lat']] for g in gs])
        closed=[]
        while parts:
            chain=parts.pop(0)
            while chain[0]!=chain[-1]:
                found=False
                for i,part in enumerate(parts):
                    if chain[-1]==part[0]:chain+=part[1:]
                    elif chain[-1]==part[-1]:chain+=part[-2::-1]
                    elif chain[0]==part[-1]:chain=part[:-1]+chain
                    elif chain[0]==part[0]:chain=part[:0:-1]+chain
                    else:continue
                    parts.pop(i);found=True;break
                if not found:return None
            if len(chain)<4:return None
            closed.append(chain)
        rings[role]=closed
    if not rings['outer']:return None
    polygons=[[ring] for ring in rings['outer']]
    for ring in rings['inner']:
        owners=[p for p in polygons if inside(ring[0],p[0])]
        if len(owners)!=1:return None
        owners[0].append(ring)
    return {'type':'Polygon','coordinates':polygons[0]} if len(polygons)==1 else {'type':'MultiPolygon','coordinates':polygons}


def platform_floor(props, pos, routes, tracks, jr_station=False):
    """JRホームと同じ路線の最寄り線路で地上/高架を模式化。原levelは保持。

    路線が不明、30m以内に線路がない、トンネル/地下なら階を補わない。
    layerは階数ではない。高架のlevel 1は模式値とし、原階とは区別する。
    """
    tags=props['original_tags']
    if tags.get('location')=='underground' or tags.get('tunnel') not in (None,'no','building_passage'):return
    member_routes=[r for r in routes.values() if r.get('tags',{}).get('ref') in ('JY','JB','JC') and any(m['type']==props['osm_type'] and m['ref']==props['osm_id'] and m.get('role')=='platform' for m in r['members'])]
    inferred_membership=False
    if not member_routes:
        # routeにplatformメンバーがないJR駅もある。階なし・train明記の
        # ホームのみ10m以内のJR線路で模式化し、路線所属は未確認のまま。
        if not jr_station or tags.get('train')!='yes' or tags.get('subway')=='yes' or props['levels'] or props.get('line_names'):return
        if re.fullmatch(r'-?\d+(?:\.\d+)?',tags.get('layer','0')) and float(tags.get('layer','0'))<0:return
        member_routes=[r for r in routes.values() if r.get('tags',{}).get('ref') in ('JY','JB','JC')]
        inferred_membership=True
    ids={m['ref'] for r in member_routes for m in r['members'] if m['type']=='way' and m.get('role') in ('','forward','backward')}
    kx=111320*math.cos(math.radians(pos[0]));ky=110574
    closest=None
    for track in tracks:
        if track['id'] not in ids:continue
        geom=track.get('geometry',[])
        for a,b in zip(geom,geom[1:]):
            if not a or not b:continue
            ax,ay=(a['lon']-pos[1])*kx,(a['lat']-pos[0])*ky
            bx,by=(b['lon']-pos[1])*kx,(b['lat']-pos[0])*ky
            dx,dy=bx-ax,by-ay
            u=max(0,min(1,-(ax*dx+ay*dy)/(dx*dx+dy*dy))) if dx or dy else 0
            d=math.hypot(ax+u*dx,ay+u*dy)
            if closest is None or d<closest[0]:closest=(d,track)
    if closest is None or closest[0]>(10 if inferred_membership else 30):return
    d,track=closest;t=track.get('tags',{})
    if t.get('tunnel') not in (None,'no','building_passage') or t.get('location')=='underground':return
    # 元の正の階はそのまま利用。切通し等の負階は地表基準の模式階へ分離する。
    if props['levels'] and min(props['levels'])>=0:return
    elevated=t.get('bridge') not in (None,'no') or tags.get('bridge') not in (None,'no')
    elevated=elevated or any(float(v)>0 for v in (t.get('layer','0'),tags.get('layer','0')) if re.fullmatch(r'-?\d+(?:\.\d+)?',v))
    props['levels']=[1 if elevated else 0]
    props['level_method']='osm_surface_track_schematic'
    props['level_note']='JRホーム近傍の同路線OSM線路から地上・高架を推定。表示階は模式値で実測階ではありません。原levelは別記。'
    if inferred_membership:props['level_note']='近傍10m以内のJR線路から地上・高架を推定。ホームの路線所属は未確認。表示階は模式値で、原levelは別記。'
    props['surface_context']={'osm_type':'way','osm_id':track['id'],'distance_m':round(d,2),'original_tags':t,'raw_source':'data/raw/expansion/jr-platform-tracks.json.gz'}
    props['surface_context']['association']='nearest_jr_track_estimated' if inferred_membership else 'same_route_track'


def extract(station, obj, all_stations, dem):
    features=[];roads=[]
    routes={}
    for name in ('discovery','metro-discovery','metro-discovery-reverse','metro-route-catalog','jr-ochanomizu-routes','toei-route-catalog'):
        path=RAW/f'{name}.json.gz'
        if path.exists():
            for e in json.loads(gzip.decompress(path.read_bytes()))['elements']:
                if e['type']=='relation' and e.get('tags',{}).get('ref') in LINE_NAMES and (name!='toei-route-catalog' or e.get('tags',{}).get('network')=='都営地下鉄'):routes[e['id']]=e
    aliases={normalized(alias):s['name'] for s in all_stations for alias in [s['name']]+s.get('aliases',[])}
    # 各路線の停止点も使い、長い乗換駅の一方を別駅に割り当てない。
    nearby=[(aliases.get(normalized(e.get('tags',{}).get('name','')),normalized(e.get('tags',{}).get('name',''))),point(e)) for e in obj['elements'] if e.get('tags',{}).get('railway')=='station' and point(e)]
    nearby.extend((s['name'],p) for s in all_stations for p in s.get('member_positions',[s['pos']]))
    nearby=[(name,p) for name,p in nearby if name]
    def belongs(pos):
        choices=sorted((distance(pos,p),name) for name,p in nearby)
        return bool(choices and choices[0][1]==station['name'] and choices[0][0]<=450)
    for e in obj['elements']:
        tags=e.get('tags',{})
        if any(g is None or 'lat' not in g or 'lon' not in g for g in e.get('geometry',[])):continue # 欠けた頂点をまたいで線を補わない
        coords=[[g['lat'],g['lon']] for g in e.get('geometry',[])]
        if e['type']=='way' and tags.get('highway') and len(coords)>1:
            roads.append({'id':e['id'],'name':tags.get('name',''),'kind':tags['highway'],'points':coords,'tags':tags})
        kind=None
        if tags.get('railway')=='subway_entrance':kind='exit'
        elif tags.get('railway')=='platform' or (tags.get('public_transport')=='platform' and (tags.get('subway')=='yes' or tags.get('train')=='yes')):kind='platform'
        elif tags.get('barrier')=='ticket_gate':kind='gate'
        elif tags.get('highway')=='elevator':kind='elevator'
        elif tags.get('highway')=='steps' and (tags.get('level') is not None or tags.get('indoor')=='yes' or tags.get('tunnel')=='yes'):
            kind='escalator' if tags.get('conveying') not in (None,'no') else 'stairs'
        elif tags.get('highway') in ('footway','corridor','pedestrian') and (tags.get('indoor')=='yes' or tags.get('tunnel')=='yes' or (levels(tags.get('level')) and any(l<0 for l in levels(tags.get('level'))))):kind='corridor'
        if not kind:continue
        if e['type']=='relation' and (kind!='platform' or platform_relation_geometry(e) is None):continue
        pos=point(e)
        if pos is None or not belongs(pos):continue
        if e['type']=='relation':geom=platform_relation_geometry(e)
        elif e['type']=='node':geom={'type':'Point','coordinates':pos[::-1]}
        elif len(coords)>1:
            xy=[p[::-1] for p in coords]
            geom={'type':'Polygon','coordinates':[xy]} if coords[0]==coords[-1] and (tags.get('area')=='yes' or kind=='platform') else {'type':'LineString','coordinates':xy}
        else:continue
        props={'station':station['name'],'kind':kind,'osm_type':e['type'],'osm_id':e['id'],'level_raw':tags.get('level'),'levels':levels(tags.get('level')),'ref':tags.get('ref',''),'assignment':'nearest_station_within_450m_estimated','elevator':tags.get('highway')=='elevator' or tags.get('wheelchair')=='yes' and tags.get('entrance')=='elevator','original_tags':tags}
        # 路線は元の明記タグがある場合のみ。複数路線駅で色を推測しない。
        if tags.get('line'):props['line']=tags['line']
        props['color']=tags.get('colour','#777777')
        memberships={LINE_NAMES[r['tags']['ref']]:r['tags'].get('colour','#777777') for r in routes.values() if any(m['type']==e['type'] and m['ref']==e['id'] and m.get('role')=='platform' for m in r['members'])}
        if memberships:
            props['line_names']=sorted(memberships);props['line']='・'.join(props['line_names']);props['color']=next(iter(memberships.values())) if len(memberships)==1 else '#777777';props['line_method']='osm_route_membership'
        if kind=='platform':platform_floor(props,pos,routes,rail_context(str(RAW)),bool(station.get('jr_names')))
        if kind=='exit':props['elevation']=dem.get(pos)
        features.append({'type':'Feature','id':f'{e["type"]}/{e["id"]}','geometry':geom,'properties':props})
    counts={k:sum(f['properties']['kind']==k for f in features) for k in ['platform','corridor','stairs','exit','gate','concourse','elevator','escalator']}
    counts['elevator_exit']=sum(bool(f['properties'].get('elevator')) and f['properties']['kind']=='exit' for f in features)
    counts['exit_elevation']=sum(f['properties']['kind']=='exit' and f['properties']['elevation']['h'] is not None for f in features)
    ls=sorted({n for f in features if f['properties']['kind']!='exit' for n in f['properties']['levels']},reverse=True)
    warnings=['OSM収録分のみ。未収録は設備がないという意味ではありません。','駅所属は周辺の駅代表点から450m以内の最近接による推定。接続・改札内外・路線所属は未確認です。','元のlevelタグを保持。JRの地上・高架の模式階を除き、階の無い設備の深さは推測しません。']
    if any(f['properties'].get('level_method')=='osm_surface_track_schematic' for f in features):
        warnings.append('JRホームの地上・高架は近傍OSM線路から推定した模式階を含みます。路線所属未確認のものは詳細に明記します。原levelを保持し、実測の床高・道路との高低差は表しません。')
    if len(station.get('aliases',[]))>1:warnings.append('一覧では'+ '・'.join(station['aliases'])+'を1駅に統合。乗換接続・通行可否は未検証です。')
    if station['name']=='本郷三丁目':warnings.append('階タグに不整合の可能性があります。原タグを修正せず表示します。')
    info={**station,'counts':counts,'levels':ls,'warnings':warnings}
    slopes,coverage=slopes_for(roads,dem)
    computed_ids=coverage.pop('computed_road_ids')
    info['terrain']=coverage
    raw_labels=obj.get('_raw_labels',[station['id']])
    source_metas=[read(f'raw/expansion/{label}.metadata.json') for label in raw_labels]
    dates=sorted({m['retrieved_at'] for m in source_metas})
    acquired=dates[0] if len(dates)==1 else dates[0]+'〜'+dates[-1]
    interior={'type':'FeatureCollection','license':'ODbL-1.0','license_url':'https://opendatacommons.org/licenses/odbl/1-0/','source':'© OpenStreetMap contributors / ODbL-1.0','input_source_note':f'Overpass API取得原入力（保存済み入力の再利用を含む） {acquired}。駅所属は近接による推定。','new_overpass_download':True,'stations':[info],'features':features,'raw_sources':[f'data/raw/expansion/{label}.json.gz' for label in raw_labels]}
    exits=[{'name':f'{station["name"]}駅 {f["properties"]["ref"] or "番号未収録"}','group':station['name'],'pos':f['geometry']['coordinates'][::-1],'elev':f['properties']['elevation'],'source':f'https://www.openstreetmap.org/{f["id"]}','method':'OSM出口位置・駅所属は近接推定'} for f in features if f['properties']['kind']=='exit' and f['geometry']['type']=='Point']
    return interior,{'computed_road_ids':computed_ids,'roads':[{k:v for k,v in r.items() if k!='tags'} for r in roads if r['kind'] in {'trunk','primary','secondary','tertiary','unclassified','residential','living_street','pedestrian'} and not any(r['tags'].get(k) not in (None,'no','0') for k in ('tunnel','indoor','covered','layer'))],'slopes':slopes,'exits':exits}


def run(stations, all_stations, endpoint, rebuild=False, split_query=False,shared=None,elements_only=False):
    dem=Elevations()
    index=read('station-index.json')['stations'] if (D/'station-index.json').exists() else []
    by_name={s['name']:s for s in index}
    def update_index(station,info):
        # 統合した駅を生成できてから旧名を外し、失敗時は既存駅を維持する。
        for name,old in list(by_name.items()):
            if old['id']==station['id'] and name!=station['name']:by_name.pop(name)
        for alias in station.get('aliases',[]):
            if alias!=station['name']:by_name.pop(alias,None)
        by_name[station['name']]={**info,'url':f'data/stations/{station["id"]}.json'}
        write(D/'station-index.json',{'version':1,'stations':list(by_name.values())})
    failed=[]
    for station in stations:
        prior=by_name.get(station['name'],{})
        station={**station,'lines':list(dict.fromkeys(prior.get('lines',[])+station['lines'])),'orders':{**prior.get('orders',{}),**station.get('orders',{})}}
        target=D/'stations'/f'{station["id"]}.json'
        processed=D/'processed'/f'{station["id"]}.json.gz'
        if target.exists() and processed.exists() and not rebuild:
            saved=read(str(target.relative_to(D)))
            # 路線追加・別名統合・所属判定変更を「生成済み」として取りこぼさない。
            desired={k:station.get(k) for k in ('name','lines','orders','aliases','member_positions')}
            if any(saved['stations'][0].get(k)!=v for k,v in desired.items()):
                log(f'更新：{station["name"]}の路線・統合情報を保存済み入力から再生成')
            else:
                update_index(station,saved['stations'][0])
                log(f'再開：{station["name"]}は生成済み。保持して次へ。');continue
        log(f'着手：{station["name"]}（周囲800m）')
        try:
            obj=fetch_station(station,endpoint,split_query,shared,elements_only)
        except RuntimeError as error:
            log(f'取得未了：{station["name"]} / {error}。他の駅へ進み、再実行でここから取得する。')
            failed.append(station['name']);continue
        # JRのホームには複数wayで輪郭を構成するmultipolygonがある。
        # 保存した原relationを加え、欠けた輪郭を補わず結合できるものだけ抽出する。
        for relation_label in ('jr-platform-relations','jr-platform-parts'):
            relation_path=RAW/(relation_label+'.json.gz')
            if not relation_path.exists():continue
            by_id={(e['type'],e['id']):e for e in obj['elements']}
            parts=json.loads(gzip.decompress(relation_path.read_bytes()))['elements']
            ways={e['id']:e for e in parts if e['type']=='way'}
            for element in parts:
                if element['type']=='relation':
                    element={**element,'members':[{**m,**({'geometry':ways[m['ref']]['geometry']} if m['type']=='way' and m['ref'] in ways and 'geometry' in ways[m['ref']] else {})} for m in element['members']]}
                by_id[element['type'],element['id']]=element
            obj={**obj,'elements':list(by_id.values()),'_raw_labels':list(dict.fromkeys(obj.get('_raw_labels',[station['id']])+[relation_label]))}
        interior,area=extract(station,obj,all_stations,dem)
        if write(target,interior)>3_000_000:raise ValueError(f'駅JSONが3MB超: {station["name"]}')
        processed.parent.mkdir(parents=True,exist_ok=True);write_bytes(processed,gzip.compress(json.dumps(area,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode(),mtime=0))
        update_index(station,interior['stations'][0])
        log(f'完了：{station["name"]} / {interior["stations"][0]["counts"]} / 道路{len(area["roads"])}本・坂{len(area["slopes"])}区間')
    write(RAW/'dem-usage.json',{'updated_at':now(),'tiles_used_in_last_run':sorted(dem.used),'temporary_errors':dem.failures,'source':'国土地理院 標高タイル DEM1A / DEM5A','note':'各タイルの原PNG・URL・取得日時・SHA256・404もdem/に保存。'})
    split_build()
    return failed


def main():
    global OVERPASS_METHOD
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--discover',action='store_true')
    parser.add_argument('--stations-file',type=Path)
    parser.add_argument('--stations',nargs='+')
    parser.add_argument('--rebuild',action='store_true')
    parser.add_argument('--split-query',action='store_true',help='周辺の取得を4つの小さな矩形に分ける。全原レスポンスを別々に保存。')
    parser.add_argument('--endpoint',default=ENDPOINT)
    parser.add_argument('--overpass-method',choices=['POST','GET'],default='POST')
    parser.add_argument('--split-elements',action='store_true',help='道路と施設を別々に問い合わせる。')
    parser.add_argument('--shared-facilities',action='store_true',help='対象全駅の施設を一度だけ取得し、駅周辺道路は別取得する。')
    args=parser.parse_args()
    OVERPASS_METHOD=args.overpass_method
    if args.discover:
        discover(args.endpoint)
        if not args.stations and not args.stations_file and not args.rebuild:return
    default_config='station-list.json'
    config=json.loads(args.stations_file.read_text()) if args.stations_file else read(default_config)
    stations=config['stations'] if isinstance(config,dict) else config
    selected=[s for s in stations if not args.stations or s['name'] in args.stations]
    if args.stations and set(args.stations)-{s['name'] for s in selected}:raise ValueError('未登録駅。--stations-fileに駅名・id・pos・linesを追加してください。')
    shared=shared_facilities(stations,args.endpoint,'toei-shared-facilities' if isinstance(config,dict) and 'toei_stations' in config else 'jr-shared-facilities' if isinstance(config,dict) and 'jr_stations' in config else 'metro-shared-facilities') if args.shared_facilities else None
    failed=run(selected,stations,args.endpoint,args.rebuild,args.split_query,shared,args.split_elements or args.shared_facilities)
    if failed:
        log('今回の取得未了：'+ '・'.join(failed))
        raise SystemExit(1)

if __name__=='__main__':
    main()
