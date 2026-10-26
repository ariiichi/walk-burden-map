"""7路線の全運行route・両方向・支線・終点の対象判定と別名統合を原OSMで検証。"""
import gzip,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'data'))
from build_area import normalized,inside,LINE_NAMES

def raw(label):
 path=ROOT/'data/raw/expansion'/f'{label}.json.gz'
 body=gzip.decompress(path.read_bytes())
 meta=json.loads(path.with_name(label+'.metadata.json').read_text())
 assert hashlib.sha256(body).hexdigest()==meta['sha256_uncompressed']
 assert (path.with_name(label+'.overpass')).is_file() and meta['retrieved_at'] and meta['endpoint']
 return json.loads(body)['elements']

config=json.loads((ROOT/'data/raw/expansion/metro-stations.json').read_text())
index=json.loads((ROOT/'data/station-index.json').read_text())['stations']
selected=config['stations'];excluded=config['excluded'];all_rows=selected+excluded
assert len(selected)==len({s['id'] for s in selected})
assert {s['id'] for s in selected}<={s['id'] for s in index}
current_aliases={normalized(a):s for s in index for a in s.get('aliases',[s['name']])}
for s in selected:
 current=current_aliases[normalized(s['name'])] if normalized(s['name']) in current_aliases else next(i for i in index if i['id']==s['id'])
 assert current['id']==s['id'] and set(s['lines'])<=set(current['lines'])
aliases={normalized(alias):s for s in all_rows for alias in s.get('aliases',[s['name']])}
elements={}
for name in config['raw_discovery']:
 label=Path(name).name.removesuffix('.json.gz')
 elements.update({(e['type'],e['id']):e for e in raw(label)})
for missing in config['missing_terminals']:
 elements.update({(e['type'],e['id']):e for e in raw('metro-terminal-'+missing['name'])})
catalog=raw('metro-route-catalog')
refs=set()
for r in catalog:
 if r['tags'].get('network')!='東京メトロ' or r['tags'].get('type')!='route':continue
 ref=r['tags']['ref'];refs.add(ref)
 for m in r['members']:
  if m.get('role')!='stop':continue
  e=elements[m['type'],m['ref']];name=normalized(e['tags']['name'])
  row=aliases[name]
  assert LINE_NAMES[ref] in row['lines'],(name,ref)
  assert any(member['osm_id']==e['id'] for member in row['members']),(name,e['id'])
assert refs==set('GHTCYNF')
for row in selected:
 assert row.get('boundary_matches') or any(inside(m['pos'],config['boundary']) for m in row['members']),row['name']
for row in excluded:
 assert not row.get('boundary_matches') and not any(inside(m['pos'],config['boundary']) for m in row['members']),row['name']
for pair in config['transfer_groups']:
 assert len({aliases[n]['id'] for n in pair})==1,pair
assert aliases['目黒'] in selected and aliases['北綾瀬'] in excluded
assert aliases['明治神宮前〈原宿〉']['boundary_matches']==['原宿']
assert aliases['仲御徒町']['boundary_matches']==['御徒町']
print(f'PASS: 7路線の全route停止点・支線・終点補足、{len(selected)}対象駅群・{len(excluded)}除外駅群・別名統合・原入力SHA')
