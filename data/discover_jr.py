"""東京メトロの駅リストとOSM山手線全駅・内側のJR駅を統合する。

原入力の取得はOverpass・10秒以上の間隔。駅名の統合は一覧上のみ。
python data/discover_jr.py
"""
import copy
import gzip
import json
from build_area import D, RAW, read, write, normalized, point, inside, log, LINE_NAMES

ROUTE_INPUTS = ['discovery', 'jr-ochanomizu-routes']
JR_NAMES = {'JY':'JR山手線','JB':'JR中央・総武線','JC':'JR中央線快速'}
MERGES = {'原宿':'明治神宮前〈原宿〉','御徒町':'上野広小路・仲御徒町'}


def raw(label):
    return json.loads(gzip.decompress((RAW/(label+'.json.gz')).read_bytes()))['elements']


def main():
    previous=read('raw/expansion/metro-stations.json')
    rows=copy.deepcopy(previous['stations'])
    routes={r['id']:r for label in ROUTE_INPUTS for r in raw(label)
            if r['type']=='relation' and r.get('tags',{}).get('ref') in JR_NAMES}
    stop_labels=['jr-inner-stops']+(['jr-route-stops'] if (RAW/'jr-route-stops.json.gz').exists() else [])
    stops={e['id']:e for label in ['discovery']+stop_labels for e in raw(label) if e['type']=='node'}
    catalog=raw('jr-station-catalog')
    boundary=previous['boundary']
    loop=routes[previous['yamanote_relation']]
    boundary_names={normalized(stops[m['ref']]['tags']['name']) for m in loop['members'] if m.get('role')=='stop'}
    assert len(boundary_names)==30, '山手線30駅の照合が必要'
    jr={};outside_stop_refs=set()
    for r in sorted(routes.values(),key=lambda r:(r['id'] not in (1972920,10312043,10363876),r['id'])):
        line=JR_NAMES[r['tags']['ref']]
        for order,m in enumerate(m for m in r['members'] if m.get('role')=='stop'):
            if m['type']!='node':raise ValueError(f'ノード以外の停止点: {m}')
            if m['ref'] not in stops:
                outside_stop_refs.add(m['ref']);continue # 原routeは保持。停止点取得は明示した対象外接矩形内。
            e=stops[m['ref']];name=normalized(e['tags']['name']);pos=point(e)
            s=jr.setdefault(name,{'name':name,'lines':[],'orders':{},'members':[]})
            if line not in s['lines']:s['lines'].append(line)
            s['orders'].setdefault(line,order)
            member={'name':name,'pos':pos,'osm_id':e['id'],'lines':[line]}
            if member not in s['members']:s['members'].append(member)
    # 路線にstopが欠落していてもJR operator/refが明記された駅を捨てない。
    for e in catalog:
        t=e.get('tags',{});name=normalized(t.get('name',''))
        refs=[ref[:2] for ref in t.get('ref','').split(';') if ref[:2] in JR_NAMES]
        if not name or not (refs or any(x in t.get('operator','') for x in ('東日本旅客鉄道','東海旅客鉄道'))):continue
        s=jr.setdefault(name,{'name':name,'lines':[],'orders':{},'members':[]})
        member={'name':name,'pos':point(e),'osm_id':e['id'],'osm_type':e['type'],'lines':[JR_NAMES[ref] for ref in refs],'catalog':True}
        if member not in s['members']:s['members'].append(member)
        for ref in refs:
            line=JR_NAMES[ref]
            if line not in s['lines']:s['lines'].append(line)
            s['orders'].setdefault(line,1000000)
    included=[];excluded=[]
    for name,s in jr.items():
        match=name in boundary_names
        if not match and not any(inside(m['pos'],boundary) for m in s['members']):
            excluded.append({**s,'reason':'山手線停止点多角形の外側・山手線駅名の一致なし'});continue
        if not s['lines']:raise ValueError(f'路線未確認のJR対象駅: {name}')
        included.append(copy.deepcopy(s))
        target=MERGES.get(name,name)
        row=next((r for r in rows if target==r['name'] or target in r.get('aliases',[])),None)
        if row is None:
            m=next((m for m in s['members'] if m.get('catalog') and m.get('osm_type')=='node'),s['members'][0])
            row={'id':f'osm-{m["osm_id"]}','name':name,'pos':m['pos'],'lines':[],'orders':{},'members':[]}
            rows.append(row)
        aliases=row.get('aliases',[row['name']])
        if name not in aliases:
            row['aliases']=aliases+[name];row['name']='・'.join(row['aliases'])
            row['integration_note']='一覧上の同名・別名駅統合。OSM駅名・位置を保持。構内接続・通行可否は未検証。'
        row['lines']=list(dict.fromkeys(row['lines']+s['lines']))
        row['orders'].update(s['orders'])
        for m in s['members']:
            if m not in row['members']:row['members'].append(m)
        row['jr_names']=list(dict.fromkeys(row.get('jr_names',[])+[name]))
        row['scope']='山手線上（駅名照合）' if match else '山手線内（停止点多角形）'
    for row in rows:
        row['member_positions']=[list(p) for p in dict.fromkeys(tuple(m['pos']) for m in row['members'])]
    result={'source':'OSM山手線両方向・中央/総武線両方向のJR route停止点と駅カタログ。東京メトロの駅リストを保持。',
            'boundary_method':previous['boundary_method'],'boundary':boundary,'yamanote_relation':previous['yamanote_relation'],
            'raw_discovery':['data/raw/expansion/'+label+'.json.gz' for label in ROUTE_INPUTS+stop_labels+['jr-station-catalog']],
            'stop_catalog_bbox':[35.60,139.67,35.75,139.79],'route_stop_refs_not_in_bbox_catalog':sorted(outside_stop_refs),
            'jr_line_names':JR_NAMES,'jr_route_ids':sorted(routes),'jr_stations':included,'jr_excluded':excluded,
            'merge_aliases':MERGES,'stations':rows}
    write(D/'raw/expansion/metro-jr-stations.json',result)
    log(f'JR対象確定：JR {len(included)}駅（山手線30駅＋内側{len(included)-30}駅）、地下鉄との統合後は累計{len(rows)}駅群。')
    print('JR対象:', ' / '.join(s['name'] for s in included))


if __name__=='__main__':main()
