"""都営4線の全停止点・原入力・範囲・既存駅統合と収録状況表を検証。"""
import gzip
import hashlib
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'data'))
from build_area import inside, normalized
from discover_toei import TOEI_NAMES, MERGES
from build_coverage import main as build_coverage


def read(path):return json.loads((ROOT/path).read_text())
def raw(path):
    body=gzip.decompress((ROOT/path).read_bytes())
    meta=read(path.replace('.json.gz','.metadata.json'))
    assert hashlib.sha256(body).hexdigest()==meta['sha256_uncompressed']
    assert meta['retrieved_at'] and meta['endpoint'] and (ROOT/path).with_name(meta['query_file']).is_file()
    return json.loads(body)['elements']

c=read('data/station-list.json');index=read('data/station-index.json')['stations']
assert {s['id'] for s in index}=={s['id'] for s in c['stations']}
assert len(index)==len({s['id'] for s in index})==len({s['name'] for s in index})
aliases={normalized(a):s for s in index for a in [s['name']]+s.get('aliases',[])}
all_rows={s['name']:s for s in c['toei_stations']+c['toei_excluded']}
selected={s['name']:s for s in c['toei_stations']}
elements={}
for path in c['toei_raw_discovery']:
    elements.update({(e['type'],e['id']):e for e in raw(path)})
routes=[elements['relation',i] for i in c['toei_route_ids']]
assert {r['tags']['ref'] for r in routes}==set(TOEI_NAMES)
for route in routes:
    for m in route['members']:
        if m.get('role')!='stop':continue
        e=elements[m['type'],m['ref']];name=normalized(e['tags']['name']);row=all_rows[name]
        assert TOEI_NAMES[route['tags']['ref']] in row['lines']
        assert any(p['osm_id']==e['id'] and p['pos']==[e['lat'],e['lon']] for p in row['members'])
for name,row in all_rows.items():
    target=MERGES.get(name,name)
    on_boundary=any(s['name']==target and 'JR山手線' in s['lines'] for s in c['jr_stations'])
    assert (name in selected)==(on_boundary or any(inside(m['pos'],c['boundary']) for m in row['members'])),name
    if name in selected:
        current=aliases[name]
        assert set(row['lines'])<=set(current['lines'])
        for m in row['members']:assert m in current['members']
for a,b in MERGES.items():
    if a in selected:assert aliases[a]['id']==aliases[b]['id'],(a,b)
for name in ['白山','千石','巣鴨','水道橋','若松河田','牛込柳町','牛込神楽坂','芝公園','御成門','赤羽橋','高輪台','泉岳寺','曙橋']:
    assert name in selected,name
assert not {'都庁前','汐留','西巣鴨','浅草橋','岩本町'}&selected.keys()
assert aliases['泉岳寺']['id']!=aliases['高輪ゲートウェイ']['id']
seen_lines=set()
for s in index:
    for f in read(s['url'])['features']:
        p=f['properties']
        if p['kind']=='platform':seen_lines.update(set(p.get('line_names',[]))&set(TOEI_NAMES.values()))
assert seen_lines==set(TOEI_NAMES.values())
p=ROOT/'docs/STATIONS_COVERAGE.md';before=p.read_text();build_coverage();assert p.read_text()==before
for s in index:assert f'[{s["name"]}](../{s["url"]})' in before
assert read('data/raw/expansion/dem-usage.json')['temporary_errors']==[]
print(f'PASS: 都営4線{len(routes)}route全停止点・対象{len(selected)}駅名・累計{len(index)}駅群・統合・収録表・原入力SHA')
