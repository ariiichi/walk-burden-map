"""JR駅の範囲・原停止点・重複統合・模式階の根拠を保存済みOSMで検証。"""
import gzip
import hashlib
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'data'))
from build_area import inside, normalized, platform_floor

def read(path):return json.loads((ROOT/path).read_text())
def raw(path):
 body=gzip.decompress((ROOT/path).read_bytes())
 meta=read(path.replace('.json.gz','.metadata.json'))
 assert hashlib.sha256(body).hexdigest()==meta['sha256_uncompressed']
 assert meta['retrieved_at'] and (ROOT/path).with_name(meta['query_file']).is_file()
 return json.loads(body)['elements']

c=read('data/station-list.json');index=read('data/station-index.json')['stations']
assert {s['id'] for s in c['stations']}<={s['id'] for s in index}
assert len(index)==len({s['name'] for s in index})
jr=c['jr_stations']
assert len(jr)==37
assert len([s for s in jr if 'JR山手線' in s['lines']])==30
assert {s['name'] for s in jr if 'JR山手線' not in s['lines']}=={'千駄ケ谷','信濃町','四ツ谷','市ケ谷','飯田橋','水道橋','御茶ノ水'}
aliases={normalized(a):s for s in index for a in [s['name']]+s.get('aliases',[])}
for s in jr:
 current=aliases[normalized(s['name'])]
 assert set(s['lines'])<=set(current['lines'])
 for m in s['members']:assert m['pos'] in current['member_positions']
 if 'JR山手線' not in s['lines']:assert any(inside(m['pos'],c['boundary']) for m in s['members'])
assert not {'浅草橋','大久保','新日本橋','馬喰町','八丁堀'}&{s['name'] for s in jr}
elements={}
for name in c['raw_discovery']:elements.update({(e['type'],e['id']):e for e in raw(name)})
for s in jr:
 for m in s['members']:
  e=elements[m.get('osm_type','node'),m['osm_id']]
  assert normalized(e['tags']['name'])==s['name']
tracks=raw('data/raw/expansion/jr-platform-tracks.json.gz')
routes={e['id']:e for e in elements.values() if e['type']=='relation'}
track_by={e['id']:e for e in tracks}
estimated=nonnegative=0
for s in index:
 for f in read(s['url'])['features']:
  p=f['properties']
  if p.get('level_method')=='osm_surface_track_schematic':
   estimated+=1
   ctx=p['surface_context'];assert ctx['original_tags']==track_by[ctx['osm_id']]['tags'] and ctx['distance_m']<=30
   assert p['levels'] in ([0],[1]) and p['kind']=='platform' and '推定' in p['level_note']
  if p['kind']=='platform' and any(n>=0 for n in p['levels']):nonnegative+=1
assert estimated and nonnegative>=30
print(f'PASS: JR37駅（山手線30＋内側7）、別名統合・原OSM照合・模式階{estimated}地物/地上高架ホーム{nonnegative}地物')
