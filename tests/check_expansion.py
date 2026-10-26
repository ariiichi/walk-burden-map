"""分割境界・計算済み坂の保持・駅別公開データ・出典を通信なしで検証。"""
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'data'))
from split_bundle import clip
from build_area import platform_relation_geometry
LINE_NAMES=dict(zip('MZGHTCYNF',('丸ノ内線','半蔵門線','銀座線','日比谷線','東西線','千代田線','有楽町線','南北線','副都心線')))
LINE_NAMES.update({'A':'浅草線','I':'三田線','S':'新宿線','E':'大江戸線'})
LINE_NAMES.update({'JY':'JR山手線','JB':'JR中央・総武線','JC':'JR中央線快速'})

assert clip([0,0],[2,2],[[.5,.5],[1,1]])==[[.5,.5],[1.,1.]]
assert clip([0,0],[0,2],[[.5,.5],[1,1]]) is None

def read(path):return json.loads((ROOT/path).read_text())

index=read('data/area-index.json')
assert len(index['areas'])>1
actual_slopes=set()
for entry in index['areas']:
 path=ROOT/entry['url']
 assert path.stat().st_size==entry['bytes']<3_000_000
 data=json.loads(path.read_text())
 for key in ('roads','contours','slopes'):
  for item in data.get(key, []):
   for p in item['points']:
    assert all(entry['bounds'][0][i]-1e-7<=p[i]<=entry['bounds'][1][i]+1e-7 for i in (0,1)),(entry['id'],key,p)
 actual_slopes.update(s['road'] for s in data['slopes'])
computed_slopes=set()
for path in (ROOT/'data/processed').glob('*.json.gz'):
 computed_slopes.update(s['road'] for s in json.loads(gzip.decompress(path.read_bytes())).get('slopes',[]))
assert computed_slopes<=actual_slopes
assert (ROOT/'data.js').stat().st_size<300_000
stations=read('data/station-index.json')['stations']
assert len(stations)==len({s['name'] for s in stations})
config=read('data/station-list.json')
assert {s['name'] for s in stations}=={s['name'] for s in config['stations']}
aliases={alias:s['name'] for s in config['stations'] for alias in s.get('aliases',[s['name']])}
for s in stations:
 expected=next(row for row in config['stations'] if row['name']==s['name'])
 assert set(s['lines'])==set(expected['lines']),s['name']
 assert s['orders']==expected['orders'],s['name']
assert all(s['id'].startswith('osm-') for s in stations)
feature_owners={}
platform_lines={}
for label in ('discovery','metro-discovery','metro-route-catalog','jr-ochanomizu-routes','toei-route-catalog'):
 path=ROOT/'data/raw/expansion'/f'{label}.json.gz'
 if not path.exists():continue
 for route in json.loads(gzip.decompress(path.read_bytes()))['elements']:
  ref=route.get('tags',{}).get('ref')
  if route['type']!='relation' or ref not in LINE_NAMES or (label=='toei-route-catalog' and route['tags'].get('network')!='都営地下鉄'):continue
  for member in route['members']:
   if member.get('role')=='platform':platform_lines.setdefault((member['type'],member['ref']),set()).add(LINE_NAMES[ref])
for s in stations:
 data=read(s['url']);assert data['stations'][0]['name']==s['name']
 fs=data['features']
 for f in fs:
  assert f['id'] not in feature_owners,(f['id'],s['name'],feature_owners.get(f['id']))
  feature_owners[f['id']]=s['name']
 for k in ('platform','corridor','stairs','exit','elevator','escalator','gate'):
  assert s['counts'][k]==sum(f['properties']['kind']==k for f in fs)
 assert s['levels']==sorted({lv for f in fs if f['properties']['kind']!='exit' for lv in f['properties']['levels']},reverse=True)
 if data.get('new_overpass_download'):
  source={}
  for raw_name in data.get('raw_sources',[data.get('raw')]):
   raw_path=ROOT/raw_name;body=gzip.decompress(raw_path.read_bytes())
   meta=read(str(raw_path.relative_to(ROOT)).replace('.json.gz','.metadata.json'))
   assert hashlib.sha256(body).hexdigest()==meta['sha256_uncompressed']
   source.update({(e['type'],e['id']):e for e in json.loads(body)['elements']})
  for f in fs:
   p=f['properties'];e=source[p['osm_type'],p['osm_id']]
   assert p['level_raw']==e.get('tags',{}).get('level')
   assert p['original_tags']==e['tags']
   if p['kind']=='platform':assert e['tags'].get('railway')=='platform' or e['tags'].get('subway')=='yes' or e['tags'].get('train')=='yes'
   expected_lines=platform_lines.get((p['osm_type'],p['osm_id']))
   if expected_lines:
    assert p.get('line_method')=='osm_route_membership'
    assert set(p.get('line_names',p['line'].split('・')))==expected_lines,(s['name'],f['id'],p.get('line'),expected_lines)
   if e['type']=='relation':assert f['geometry']==platform_relation_geometry(e,{i:v for (t,i),v in source.items() if t=='way'})
   elif e['type']=='node':assert f['geometry']['coordinates']==[e['lon'],e['lat']]
   else:
    cs=f['geometry']['coordinates'];cs=cs[0] if f['geometry']['type']=='Polygon' else cs
    assert cs==[[g['lon'],g['lat']] for g in e['geometry']]
for png in (ROOT/'data/raw/expansion/dem').glob('*.png'):
 meta=json.loads(png.with_suffix('.metadata.json').read_text());assert meta['http_status']==200
 assert meta['sha256']==hashlib.sha256(png.read_bytes()).hexdigest()
print(f'PASS: {len(index["areas"])}区画のサイズ・分割境界・計算済み坂保持、{len(stations)}駅の件数・階・新規OSM原データ照合')
