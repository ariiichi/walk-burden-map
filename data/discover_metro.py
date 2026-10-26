"""東京メトロ7路線の全停止点と欠落終点を照合する。

python data/discover_metro.py
原入力はOverpassのレスポンス・クエリ・取得日時とともに保存する。
別名駅の統合は一覧の編集規則であり、構内接続の存在を推定しない。
"""
from build_area import D, RAW, ENDPOINT, overpass, normalized, point, inside, read, write, log, LINE_NAMES

FORWARD = [443269,443272,443281,443284,5371620,5375678,7730199]
REVERSE = [11371520,8026155,8026074,8026050,8026141,8026168,8026070]
# 形状や歩行経路の補完には使わない。元の駅名・座標をmembersへ保存。
GROUPS = [
    ['永田町','赤坂見附'], ['国会議事堂前','溜池山王'],
    ['淡路町','新御茶ノ水'], ['日比谷','有楽町'],
    ['虎ノ門','虎ノ門ヒルズ'], ['上野広小路','仲御徒町'],
    ['銀座','銀座一丁目'], ['築地','新富町'],
]
BOUNDARY_ALIASES = {'明治神宮前〈原宿〉':'原宿','上野広小路':'御徒町','仲御徒町':'御徒町'}


def route_query(ids):
    return '[out:json][timeout:10];rel(id:'+','.join(map(str,ids))+')->.routes;.routes out body;node(r.routes:"stop");out body;way(r.routes:"platform");out center;'


def main():
    import gzip,json
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint',default=ENDPOINT)
    parser.add_argument('--overpass-method',choices=['POST','GET'],default='POST')
    args=parser.parse_args();endpoint=args.endpoint
    import build_area
    build_area.OVERPASS_METHOD=args.overpass_method
    core_config=build_area.discover(endpoint)
    catalog=json.loads(gzip.decompress((RAW/'metro-route-catalog.json.gz').read_bytes()))
    reverse_routes=[r for r in catalog['elements'] if r['id'] in REVERSE]
    stop_ids=sorted({m['ref'] for r in reverse_routes for m in r['members'] if m.get('role')=='stop' and m['type']=='node'})
    # 路線再帰の504を避け、保存済みrelationに明記されたノードだけを問い合わせる。
    reverse_stops=overpass('metro-reverse-stops','[out:json][timeout:10];node(id:'+','.join(map(str,stop_ids))+');out body;',endpoint)
    objects=[overpass('metro-discovery',route_query(FORWARD),endpoint),reverse_stops,{'elements':reverse_routes}]
    extra_routes=[r for r in catalog['elements'] if r['tags'].get('network')=='東京メトロ' and r['tags'].get('type')=='route' and r['id'] not in FORWARD+REVERSE]
    known={e['id'] for obj in objects for e in obj['elements'] if e['type']=='node'}
    extra_ids=sorted({m['ref'] for r in extra_routes for m in r['members'] if m.get('role')=='stop' and m['type']=='node'}-known)
    extra_stops=overpass('metro-additional-stops','[out:json][timeout:10];node(id:'+','.join(map(str,extra_ids))+');out body;',endpoint) if extra_ids else {'elements':[]}
    objects.extend([extra_stops,{'elements':extra_routes}])
    elements={(e['type'],e['id']):e for obj in objects for e in obj['elements']}
    routes={e['id']:e for e in elements.values() if e['type']=='relation'}
    rows={s['name']:{**s,'lines':list(s['lines']),'orders':dict(s.get('orders',{})),'members':[{'name':s['name'],'pos':s['pos'],'osm_id':s.get('osm_stop',s.get('osm_station')),'lines':s['lines']}]} for s in core_config['stations']}
    boundary=core_config['boundary']
    old=json.loads(gzip.decompress((RAW/'discovery.json.gz').read_bytes()))['elements']
    old_by={(e['type'],e['id']):e for e in old}
    loop=old_by['relation',core_config['yamanote_relation']]
    boundary_names={normalized(old_by[m['type'],m['ref']]['tags']['name']) for m in loop['members'] if m.get('role')=='stop'}
    missing_terminals=[]
    for forward_id,reverse_id in zip(FORWARD,REVERSE):
        forward,reverse=routes[forward_id],routes[reverse_id]
        line=LINE_NAMES[forward['tags']['ref']]
        ordered=[m for m in forward['members'] if m.get('role')=='stop']
        stops=[(elements[m['type'],m['ref']],i) for i,m in enumerate(ordered)]
        forward_names={normalized(e['tags']['name']) for e,_ in stops}
        forward_order={normalized(e['tags']['name']):i for e,i in stops}
        reverse_stops=[elements[m['type'],m['ref']] for m in reverse['members'] if m.get('role')=='stop']
        # 逆方向でのみ収録された停止点も捨てない。順序は逆方向を反転して対応。
        for i,e in enumerate(reversed(reverse_stops)):
            name=normalized(e['tags']['name'])
            stops.append((e,forward_order.get(name,i)));forward_names.add(name)
        for terminal,order in [(forward['tags']['from'],-1),(forward['tags']['to'],len(ordered)+1)]:
            if any(normalized(e['tags']['name'])==normalized(terminal) for e,_ in stops):continue
            obj=overpass('metro-terminal-'+terminal,'[out:json][timeout:10];node["railway"="station"]["name"="'+terminal+'"];out body;',endpoint)
            prefix=forward['tags']['ref']
            candidates=[e for e in obj['elements'] if any(ref.strip().startswith(prefix) and ref.strip()[len(prefix):].isdigit() for ref in e.get('tags',{}).get('ref','').split(';'))]
            if len(candidates)!=1:raise RuntimeError(f'終点を一意に照合できません: {terminal} / {candidates}')
            stops.append((candidates[0],order));missing_terminals.append({'name':terminal,'line':line,'osm_id':candidates[0]['id'],'reason':'両方向routeのstop欠落を終点タグと同名・同路線refの駅ノードで照合'})
        for e,order in stops:
            name=normalized(e['tags']['name']);pos=point(e)
            row=rows.setdefault(name,{'id':f'osm-{e["id"]}','name':name,'pos':pos,'lines':[],'orders':{},'members':[]})
            if line not in row['lines']:row['lines'].append(line)
            row['orders'][line]=order
            member={'name':name,'pos':pos,'osm_id':e['id'],'lines':[line]}
            if member not in row['members']:row['members'].append(member)
    # 支線・短区間・他の運行routeの全停止点も対象判定する（北綾瀬等）。
    for route in extra_routes:
        line=LINE_NAMES[route['tags']['ref']]
        for m in route['members']:
            if m.get('role')!='stop':continue
            e=elements[m['type'],m['ref']];name=normalized(e['tags']['name']);pos=point(e)
            row=rows.setdefault(name,{'id':f'osm-{e["id"]}','name':name,'pos':pos,'lines':[],'orders':{},'members':[]})
            if line not in row['lines']:row['lines'].append(line)
            row['orders'].setdefault(line,1000000)
            member={'name':name,'pos':pos,'osm_id':e['id'],'lines':[line]}
            if member not in row['members']:row['members'].append(member)
    # グループの先頭にある既存駅のID・取得矩形を継承する。
    for aliases in GROUPS:
        available=[rows.pop(n) for n in aliases if n in rows]
        if not available:continue
        row={**available[0],'name':'・'.join(aliases),'aliases':aliases,'lines':[],'orders':{},'members':[]}
        for s in available:
            row['lines']=list(dict.fromkeys(row['lines']+s['lines']))
            row['orders'].update(s['orders']);row['members'].extend(s['members'])
        row['integration_note']='一覧上の別名乗換駅の手動統合。駅名・位置はOSM。構内接続・通行可否は未検証。'
        rows[row['name']]=row
    selected=[];excluded=[]
    for row in rows.values():
        members=row['members'];names={m['name'] for m in members}
        boundary_matches=sorted({BOUNDARY_ALIASES.get(n,n) for n in names}&boundary_names)
        interior=any(inside(m['pos'],boundary) for m in members)
        row['member_positions']=list(dict.fromkeys(tuple(m['pos']) for m in members))
        row['member_positions']=[list(p) for p in row['member_positions']]
        if boundary_matches or interior:
            row['scope']='山手線上（同名・別名境界駅）' if boundary_matches else '山手線内（停止点多角形）'
            if boundary_matches:row['boundary_matches']=boundary_matches
            selected.append(row)
        else:
            row['reason']='山手線停止点多角形の外側・境界駅との一致なし';excluded.append(row)
    value={'source':'OSM路線の両方向停止点・支線・短区間route・不足終点はOSM駅ノード。山手線の停止点多角形を使用。','boundary_method':core_config['boundary_method']+' 別名境界駅を照合し、統合駅は一方が対象なら含める。','yamanote_relation':core_config['yamanote_relation'],'boundary':boundary,'raw_discovery':['data/raw/expansion/'+n+'.json.gz' for n in ['discovery','metro-route-catalog','metro-discovery','metro-reverse-stops','metro-additional-stops','metro-station-groups']],'transfer_groups':GROUPS,'boundary_aliases':BOUNDARY_ALIASES,'missing_terminals':missing_terminals,'stations':selected,'excluded':excluded}
    write(D/'raw/expansion/metro-stations.json',value)
    log(f'東京メトロ対象確定：累計{len(selected)}駅（別名乗換駅統合）、範囲外{len(excluded)}駅群。')
    for ref in ('G','H','T','C','Y','N','F'):
        line=LINE_NAMES[ref];print(line, ' / '.join(s['name'] for s in sorted(selected,key=lambda s:s['orders'].get(line,1e6)) if line in s['lines']))


if __name__=='__main__':main()
