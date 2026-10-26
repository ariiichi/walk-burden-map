"""都営4線の両方向・全運行routeと駅カタログを照合し、東京メトロ・JRの駅リストへ統合する。

OSM原レスポンス・クエリ・日時はraw/expansionへ保存。形状や乗換経路は補わない。
"""
import argparse
import copy
import gzip
import json
from build_area import D, RAW, ENDPOINT, overpass, normalized, point, inside, read, write, log

TOEI_NAMES={'A':'浅草線','I':'三田線','S':'新宿線','E':'大江戸線'}
# 一覧の編集規則。接続・通行可否の根拠にはしない。
MERGES={'新線新宿':'新宿','新宿西口':'新宿','春日':'後楽園',
        '小川町':'淡路町','上野御徒町':'御徒町','三田':'田町',
        '大門':'浜松町','国立競技場':'千駄ケ谷'}
BBOX=[35.60,139.67,35.75,139.79]


def raw(label):
    return json.loads(gzip.decompress((RAW/(label+'.json.gz')).read_bytes()))['elements']


def elements_ref(member,by_id,catalog):
    e=by_id.get(member['osm_id'])
    if e is None:e=next((e for e in catalog if e['type']==member.get('osm_type','node') and e['id']==member['osm_id']),{})
    return e.get('tags',{}).get('ref','')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint',default=ENDPOINT)
    args=parser.parse_args()
    previous=read('raw/expansion/metro-jr-stations.json')
    query='[out:json][timeout:25];rel["route"="subway"]["ref"~"^(A|I|S|E)$"](35.60,139.67,35.75,139.79);out body;'
    catalog=overpass('toei-route-catalog',query,args.endpoint)['elements']
    routes=[r for r in catalog if r.get('tags',{}).get('ref') in TOEI_NAMES and r.get('tags',{}).get('network')=='都営地下鉄']
    assert {r['tags']['ref'] for r in routes}==set(TOEI_NAMES)
    refs=sorted({m['ref'] for r in routes for m in r['members'] if m.get('role')=='stop' and m['type']=='node'})
    stop_labels=['jr-inner-stops','metro-station-groups']
    by_id={e['id']:e for label in stop_labels for e in raw(label) if e['type']=='node'}
    missing=sorted(set(refs)-by_id.keys())
    for i in range(0,len(missing),30):
        label='toei-stop-batch-'+str(i//30)
        obj=overpass(label,'[out:json][timeout:25];node(id:'+','.join(map(str,missing[i:i+30]))+');out body;',args.endpoint)
        stop_labels.append(label)
        by_id.update({e['id']:e for e in obj['elements']})
    assert set(refs)<=by_id.keys(), '停止点取得未了'
    station_catalog=raw('jr-station-catalog')
    toei={}
    # 駅番号の若い方向を基準にする。全routeの停止点は捨てず、順序は駅番号を優先。
    for r in sorted(routes,key=lambda r:r['id']):
        line=TOEI_NAMES[r['tags']['ref']]
        for order,m in enumerate(m for m in r['members'] if m.get('role')=='stop'):
            assert m['type']=='node'
            e=by_id[m['ref']];name=normalized(e['tags']['name'])
            s=toei.setdefault(name,{'name':name,'lines':[],'orders':{},'members':[]})
            if line not in s['lines']:s['lines'].append(line)
            s['orders'].setdefault(line,order)
            member={'name':name,'pos':point(e),'osm_id':e['id'],'lines':[line]}
            if member not in s['members']:s['members'].append(member)
    # 駅番号のあるOSM駅ノードでstop欠落・順序を照合。元座標・IDを保持。
    for e in station_catalog:
        t=e.get('tags',{});name=normalized(t.get('name',''))
        codes=[v for v in t.get('ref','').split(';') if v[:1] in TOEI_NAMES and v[1:].isdigit()]
        if not codes or not name:continue
        s=toei.setdefault(name,{'name':name,'lines':[],'orders':{},'members':[]})
        lines=[TOEI_NAMES[v[0]] for v in codes]
        member={'name':name,'pos':point(e),'osm_id':e['id'],'osm_type':e['type'],'lines':lines,'catalog':True}
        if member not in s['members']:s['members'].append(member)
        for code in codes:
            line=TOEI_NAMES[code[0]]
            if line not in s['lines']:s['lines'].append(line)
            s['orders'][line]=int(code[1:])
    rows=copy.deepcopy(previous['stations'])
    boundary_names={normalized(n) for s in previous['jr_stations'] if 'JR山手線' in s['lines'] for n in [s['name']]}
    for r in routes:
        ref=r['tags']['ref'];line=TOEI_NAMES[ref]
        ordered=[by_id[m['ref']] for m in r['members'] if m.get('role')=='stop']
        for e in ordered:
            for code in e.get('tags',{}).get('ref','').split(';'):
                if code.startswith(ref) and code[1:].isdigit():
                    toei[normalized(e['tags']['name'])]['orders'][line]=int(code[1:])
    # 駅番号がない停止点だけは、全駅停車routeの隣接する既知番号間の一覧順を使う。
    # この補間は表示順のみ。位置・形状・階・設備は補わない。
    for ref,line in TOEI_NAMES.items():
        route=max((r for r in routes if r['tags']['ref']==ref),key=lambda r:sum(m.get('role')=='stop' for m in r['members']))
        names=[normalized(by_id[m['ref']]['tags']['name']) for m in route['members'] if m.get('role')=='stop']
        known={n:toei[n]['orders'][line] for n in names if any(v.startswith(ref) and v[1:].isdigit() for m in toei[n]['members'] for v in elements_ref(m,by_id,station_catalog).split(';'))}
        for i,name in enumerate(names):
            if name in known:continue
            neighbors=[(j,known[n]) for j,n in enumerate(names) if n in known]
            left=next(((j,v) for j,v in reversed(neighbors) if j<i),None)
            right=next(((j,v) for j,v in neighbors if j>i),None)
            if left and right:toei[name]['orders'][line]=left[1]+(right[1]-left[1])*(i-left[0])/(right[0]-left[0])
    included=[];excluded=[]
    for name,s in toei.items():
        target=MERGES.get(name,name)
        row=next((r for r in rows if target in [r['name']]+r.get('aliases',[])),None)
        boundary_match=target in boundary_names
        interior=any(inside(m['pos'],previous['boundary']) for m in s['members'])
        if not boundary_match and not interior:
            excluded.append({**s,'reason':'山手線停止点多角形の外側・同名/統合先の山手線駅との一致なし'})
            continue
        included.append(copy.deepcopy(s))
        if row is None:
            m=next((m for m in s['members'] if m.get('catalog') and m.get('osm_type')=='node'),s['members'][0])
            row={'id':f'osm-{m["osm_id"]}','name':name,'pos':m['pos'],'lines':[],'orders':{},'members':[]}
            rows.append(row)
        if name not in [row['name']]+row.get('aliases',[]):
            row['aliases']=row.get('aliases',[row['name']])+[name]
            row['name']='・'.join(row['aliases'])
            row['integration_note']='一覧上の同名・近接する別名乗換駅の統合。元の駅名・位置を保持。構内接続・通行可否は未検証。'
        row['lines']=list(dict.fromkeys(row['lines']+s['lines']))
        row['orders'].update(s['orders'])
        for m in s['members']:
            if m not in row['members']:row['members'].append(m)
        row['toei_names']=list(dict.fromkeys(row.get('toei_names',[])+[name]))
        row['scope']='山手線上（同名・一覧統合先の駅名照合）' if boundary_match else '山手線内（停止点多角形）'
    # 範囲外駅も含む全路線で駅番号を調べたため、内側だけの番号ずれは起こさない。
    for row in rows:
        row['member_positions']=[list(p) for p in dict.fromkeys(tuple(m['pos']) for m in row['members'])]
    result={**previous,'source':'東京メトロ・JRとOSM都営4線全route停止点・OSM駅カタログ。',
            'toei_line_names':TOEI_NAMES,'toei_route_ids':[r['id'] for r in routes],
            'toei_raw_discovery':['data/raw/expansion/'+n+'.json.gz' for n in ['toei-route-catalog','jr-station-catalog']+stop_labels],
            'toei_merge_aliases':MERGES,'toei_stations':included,'toei_excluded':excluded,'stations':rows}
    write(D/'station-list.json',result)
    log(f'都営対象確定：都営{len(included)}駅名、累計{len(rows)}駅群。範囲外{len(excluded)}駅名。')
    for line in TOEI_NAMES.values():print(line,' / '.join(s['name'] for s in sorted(included,key=lambda s:s['orders'].get(line,1e6)) if line in s['lines']))


if __name__=='__main__':main()
