"""numpy/Pillow環境で実行。欠測を平地扱いしない・構造物を坂にしないことを確認。"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'data'))
from build_area import slopes_for

class Profile:
 def __init__(self,grade):self.grade=grade;self.calls=0
 def get(self,pos):
  self.calls+=1
  return {'h': None if self.grade is None else (pos[0]-35)*111000*self.grade/100}

road={'id':1,'name':'検証用','kind':'residential','tags':{},'points':[[35,139],[35.002,139]]}
s,coverage=slopes_for([road],Profile(10))
assert s and all(9.9<=v['g']<=10.1 for v in s[1:-1])
assert coverage['sampled_roads']==1 and coverage['computed_road_ids']==[1]
s,coverage=slopes_for([road],Profile(None))
assert not s and coverage['missing_roads']==1 and not coverage['computed_road_ids']
s,coverage=slopes_for([road],Profile(0))
assert not s and coverage['sampled_roads']==1 and coverage['computed_road_ids']==[1]
profile=Profile(10)
s,coverage=slopes_for([{**road,'tags':{'bridge':'yes'}}],profile)
assert not s and profile.calls==0 and coverage['excluded_roads']==1
s,coverage=slopes_for([{**road,'kind':'primary'}],Profile(20))
assert not s
profile=Profile(10)
s,coverage=slopes_for([{**road,'points':[[35,139],[35.00005,139]]}],profile)
assert not s and coverage['short_roads']==1 and coverage['missing_roads']==0 and profile.calls==0
print('PASS: 坂の傾き、欠測と平地の区別、橋の除外、幹線道路の異常勾配除外')

# 生成済み駅へ路線を追加したときも索引・駅JSONへ反映し、別名は1駅にする。
import tempfile,gzip,json
from unittest.mock import patch
import build_area as builder
with tempfile.TemporaryDirectory() as directory:
 root=Path(directory)
 old={'id':'s1','name':'旧駅・旧別名','lines':['丸ノ内線'],'orders':{'丸ノ内線':0}}
 builder.write(root/'station-index.json',{'stations':[old]})
 builder.write(root/'stations/s1.json',{'stations':[old],'features':[]})
 builder.write_bytes(root/'processed/s1.json.gz',gzip.compress(b'{}'))
 merged={'id':'s1','name':'統合駅','aliases':['旧駅','別名駅'],'pos':[35,139],'lines':['丸ノ内線','千代田線'],'orders':{'丸ノ内線':0,'千代田線':5}}
 built=[]
 def extract(s,*args):
  built.append(s)
  return {'stations':[{**s,'counts':{}}],'features':[]},{'roads':[],'slopes':[]}
 with patch.object(builder,'D',root),patch.object(builder,'RAW',root/'raw'),patch.object(builder,'read',lambda p:json.loads((root/p).read_text())),patch.object(builder,'log'),patch.object(builder,'split_build'),patch.object(builder,'fetch_station',return_value={}),patch.object(builder,'extract',side_effect=extract):
  assert builder.run([merged],[merged],'unused')==[]
  index=json.loads((root/'station-index.json').read_text())['stations']
  assert len(index)==1 and index[0]['name']=='統合駅' and index[0]['lines']==merged['lines']
  assert built and built[0]['orders']==merged['orders']
  builder.run([merged],[merged],'unused')
  assert len(built)==1 # 同じ入力の再開は取得・再生成しない
  builder.write(root/'station-index.json',{'stations':[old]})
  with patch.object(builder,'fetch_station',side_effect=RuntimeError('通信失敗')):
   assert builder.run([merged],[merged],'unused',rebuild=True)==['統合駅']
  assert json.loads((root/'station-index.json').read_text())['stations']==[old]
print('PASS: 生成済み駅の路線追加・別名統合・再開の重複回避')

# 重なった取得矩形で全体を覆えるときだけ原入力を再利用する。穴を創作しない。
import re
with tempfile.TemporaryDirectory() as directory:
 root=Path(directory);raw=root/'raw/expansion';raw.mkdir(parents=True)
 station={'name':'検証駅','pos':[35,139]}
 south,west,north,east=map(float,re.search(r'\[bbox:([\d.,-]+)\]',builder.station_query(station)).group(1).split(','))
 def fixture(n,box):
  label=f'osm-{n}'
  query='[out:json][bbox:'+','.join(map(str,box))+'];(way["highway"];nwr["public_transport"="platform"];);out body geom;'
  (raw/(label+'.overpass')).write_text(query)
  body={'elements':[{'type':'node','id':n,'lat':35,'lon':(box[1]+box[3])/2},{'type':'node','id':100+n,'lat':north+.01,'lon':139}]}
  builder.write_bytes(raw/(label+'.json.gz'),gzip.compress(json.dumps(body).encode()))
  builder.write(raw/(label+'.metadata.json'),{'retrieved_at':str(n)})
 fixture(1,(south,west,north,139));fixture(2,(south,139,north,east))
 with patch.object(builder,'D',root),patch.object(builder,'RAW',raw),patch.object(builder,'read',lambda p:json.loads((root/p).read_text())),patch.object(builder,'log'):
  obj=builder.reuse_covering_sources(station)
  assert {e['id'] for e in obj['elements']}=={1,2} and len(obj['_raw_labels'])==2
  fixture(2,(south,139,north-.0000001,east))
  assert builder.reuse_covering_sources(station) is None
print('PASS: 原入力矩形の完全被覆・範囲外要素の除外・微小な未取得範囲の検出')

# 共通施設を使った駅を通常再開しても、駅別施設を新たに要求しない。
with tempfile.TemporaryDirectory() as directory:
 root=Path(directory);raw=root/'raw/expansion';raw.mkdir(parents=True)
 station={'id':'osm-999','name':'検証駅','pos':[35,139]}
 box=builder.station_box(station)
 fixtures={
  'metro-shared-facilities':(builder.facilities_query(box),{'elements':[{'type':'node','id':3,'lat':35,'lon':139}]}),
  'osm-999-roads':('[out:json];way["highway"];out body geom;',{'elements':[{'type':'way','id':4,'geometry':[{'lat':35,'lon':139},{'lat':35.0001,'lon':139}]}]})
 }
 for label,(query,body) in fixtures.items():
  (raw/(label+'.overpass')).write_text(query)
  builder.write_bytes(raw/(label+'.json.gz'),gzip.compress(json.dumps(body).encode()))
 requested=[]
 def cached(label,query,endpoint):
  requested.append(label)
  assert label in fixtures,'保存されていない施設の問い合わせを要求した'
  return fixtures[label][1]
 with patch.object(builder,'RAW',raw),patch.object(builder,'overpass',side_effect=cached):
  obj=builder.fetch_station(station,'unused')
 assert requested==['osm-999-roads','metro-shared-facilities']
 assert {e['id'] for e in obj['elements']}=={3,4}
print('PASS: 共通施設原入力の通常再開・再生成での再利用')

# 4分割しても、全体を覆う共通施設を重複取得しない。
with tempfile.TemporaryDirectory() as directory:
 raw=Path(directory);station={'id':'osm-999','name':'検証駅','pos':[35,139]}
 box=builder.station_box(station)
 (raw/'jr-shared-facilities.json.gz').write_bytes(gzip.compress(b'{}'))
 (raw/'jr-shared-facilities.overpass').write_text(builder.facilities_query(box))
 requested=[]
 def split_cached(label,query,endpoint):
  requested.append(label)
  if label=='jr-shared-facilities':
   return {'elements':[{'type':'node','id':10,'lat':35,'lon':139},{'type':'node','id':11,'lat':36,'lon':139}]}
  assert label in ['osm-999-'+part+'-roads' for part in ('sw','se','nw','ne')]
  assert 'way["highway"]' in query
  return {'elements':[{'type':'way','id':len(requested),'geometry':[{'lat':35,'lon':139},{'lat':35.0001,'lon':139}]}]}
 with patch.object(builder,'RAW',raw),patch.object(builder,'overpass',side_effect=split_cached):
  obj=builder.fetch_station(station,'unused',split=True)
 assert requested==['osm-999-'+part+'-roads' for part in ('sw','se','nw','ne')]+['jr-shared-facilities']
 assert len(obj['_raw_labels'])==5 and {e['id'] for e in obj['elements']}=={1,2,3,4,10}
 with patch.object(builder,'RAW',raw),patch.object(builder,'overpass',return_value={'elements':[]}) as request:
  builder.fetch_station(station,'unused',split=True,shared=('jr-shared-facilities',[35,139,35,139]))
 assert [call.args[0] for call in request.call_args_list]==['osm-999-'+part+'-'+kind for part in ('sw','se','nw','ne') for kind in ('roads','facilities')]
print('PASS: 分割道路取得と共通施設の再利用・範囲外施設の除外・原入力来歴')

# 道路だけの保存入力も完全被覆を検査して再利用し、施設は別に取得する。
with tempfile.TemporaryDirectory() as directory:
 root=Path(directory);raw=root/'raw/expansion';raw.mkdir(parents=True)
 station={'id':'osm-999','name':'検証駅','pos':[35,139]};box=builder.station_box(station)
 for n,part in [(1,[box[0],box[1],box[2],139]),(2,[box[0],139,box[2],box[3]])]:
  label=f'osm-{n}-roads';bbox=','.join(map(str,part))
  (raw/(label+'.overpass')).write_text('[out:json];way["highway"]('+bbox+');out body geom;')
  body={'elements':[{'type':'way','id':n,'tags':{'highway':'residential'},'geometry':[{'lat':35,'lon':(part[1]+part[3])/2},{'lat':35.0001,'lon':(part[1]+part[3])/2}]}]}
  builder.write_bytes(raw/(label+'.json.gz'),gzip.compress(json.dumps(body).encode()))
  builder.write(raw/(label+'.metadata.json'),{'retrieved_at':str(n)})
 (raw/'metro-shared-facilities.overpass').write_text(builder.facilities_query(box))
 requested=[]
 def facility(label,*args):
  requested.append(label);assert label=='metro-shared-facilities'
  return {'elements':[{'type':'node','id':10,'lat':35,'lon':139,'tags':{'railway':'subway_entrance'}}]}
 with patch.object(builder,'D',root),patch.object(builder,'RAW',raw),patch.object(builder,'read',lambda p:json.loads((root/p).read_text())),patch.object(builder,'log'),patch.object(builder,'overpass',side_effect=facility):
  assert builder.reuse_covering_sources(station) is None # 道路だけで施設を充足しない
  obj=builder.fetch_elements(station,'unused',('metro-shared-facilities',box))
  assert requested==['metro-shared-facilities'] and {e['id'] for e in obj['elements']}=={1,2,10}
  assert set(obj['_raw_labels'])=={'osm-1-roads','osm-2-roads','metro-shared-facilities'}
  (raw/'osm-2-roads.json.gz').unlink()
  assert builder.reuse_covering_sources(station,roads_only=True) is None
print('PASS: 道路専用入力の完全被覆・施設との分離・原入力来歴・未取得部分の検出')

# 駅リスト省略時は現行駅リスト、明示時は指定ファイルを使う。
with tempfile.TemporaryDirectory() as directory:
 root=Path(directory)
 station={'id':'s1','name':'対象駅','lines':['丸ノ内線','JR山手線']}
 custom={'id':'s2','name':'指定駅','lines':['南北線']}
 builder.write(root/'station-list.json',{'stations':[station]})
 builder.write(root/'custom.json',{'stations':[custom]})
 with patch.object(builder,'D',root),patch.object(builder,'read',lambda p:json.loads((root/p).read_text())),patch.object(builder,'run',return_value=[]) as run:
  with patch.object(sys,'argv',['build_area.py','--stations','対象駅']):builder.main()
  assert run.call_args.args[:2]==([station],[station])
  with patch.object(sys,'argv',['build_area.py','--stations-file',str(root/'custom.json')]):builder.main()
  assert run.call_args.args[:2]==([custom],[custom])
print('PASS: 現行駅リストの省略時選択・指定ファイル読み込み')

# JRホームの階推定は同路線の近傍線路に限定し、地下・不明は補わない。
import copy
route={1:{'tags':{'ref':'JY'},'members':[{'type':'way','ref':10,'role':'platform'},{'type':'way','ref':20,'role':''}]}}
track={'type':'way','id':20,'tags':{'railway':'rail'},'geometry':[{'lat':35,'lon':139},{'lat':35.001,'lon':139}]}
base={'osm_type':'way','osm_id':10,'original_tags':{'railway':'platform'},'level_raw':None,'levels':[]}
for tags,expected in [({},[0]),({'bridge':'yes','layer':'2'},[1]),({'tunnel':'yes'},[]),({'location':'underground'},[])]:
 props=copy.deepcopy(base)
 builder.platform_floor(props,[35.0005,139],route,[{**track,'tags':{'railway':'rail',**tags}}])
 assert props['levels']==expected,(tags,props)
 assert props['level_raw'] is None and props['original_tags']==base['original_tags']
 if expected:assert props['level_method']=='osm_surface_track_schematic' and props['surface_context']['osm_id']==20
props={**copy.deepcopy(base),'level_raw':'-1','levels':[-1],'original_tags':{'railway':'platform','level':'-1'}}
builder.platform_floor(props,[35.0005,139],route,[track])
assert props['levels']==[0] and props['level_raw']=='-1' and props['original_tags']['level']=='-1'
for routes,pos in [({},[35.0005,139]),(route,[35.0005,139.01])]:
 props=copy.deepcopy(base);builder.platform_floor(props,pos,routes,[track]);assert props['levels']==[]
props={**copy.deepcopy(base),'levels':[2],'level_raw':'2'}
builder.platform_floor(props,[35.0005,139],route,[track]);assert props['levels']==[2] and 'level_method' not in props
print('PASS: JR地上/高架の模式階・原level保持・地下非補完・近傍/同路線限定')

props={**copy.deepcopy(base),'original_tags':{'railway':'platform','train':'yes'}}
builder.platform_floor(props,[35.0005,139],route,[track],jr_station=True)
assert props['levels']==[0] # 明示的なplatformメンバー
no_platform={1:{'tags':{'ref':'JY'},'members':[{'type':'way','ref':20,'role':''}]}}
for extra,position,expected in [({},[35.0005,139],[0]),({},[35.0005,139.0002],[]),({'subway':'yes'},[35.0005,139],[]),({'layer':'-1'},[35.0005,139],[])]:
 props={**copy.deepcopy(base),'original_tags':{'railway':'platform','train':'yes',**extra}}
 builder.platform_floor(props,position,no_platform,[track],jr_station=True)
 assert props['levels']==expected,(position,extra,props)
 if expected:assert props['surface_context']['association']=='nearest_jr_track_estimated' and '未確認' in props['level_note'] and not props.get('line')
print('PASS: 路線メンバー欠落時の10m限定推定・路線色を補わない・地下/負layerの除外')

# ホームの面リレーションは原way端点だけを結合し、穴も保持する。
def member(role,coords):return {'type':'way','role':role,'geometry':[{'lon':x,'lat':y} for x,y in coords]}
outer=[[0,0],[4,0],[4,4],[0,4],[0,0]];hole=[[1,1],[2,1],[2,2],[1,1]]
rel={'type':'relation','tags':{'type':'multipolygon'},'members':[member('outer',outer[:3]),member('outer',list(reversed(outer[2:]))),member('inner',hole)]}
geom=builder.platform_relation_geometry(rel)
assert geom=={'type':'Polygon','coordinates':[outer,hole]}
broken=copy.deepcopy(rel);broken['members'][1]['geometry'][0]['lon']=.01
assert builder.platform_relation_geometry(broken) is None
broken=copy.deepcopy(rel);broken['members'][1]['geometry'][0]=None
assert builder.platform_relation_geometry(broken) is None
multi=copy.deepcopy(rel);multi['members'].append(member('outer',[[10,0],[11,0],[11,1],[10,0]]))
assert builder.platform_relation_geometry(multi)['type']=='MultiPolygon'
assert len(builder.platform_relation_geometry(multi)['coordinates'])==2
orphan=copy.deepcopy(rel);orphan['members'][-1]=member('inner',[[9,9],[10,9],[10,10],[9,9]])
assert builder.platform_relation_geometry(orphan) is None
print('PASS: ホーム面の端点一致結合・穴保持・複数面・欠落/隙間/所属不明穴の非補完')

with tempfile.TemporaryDirectory() as directory:
 raw=Path(directory);label='cached';query='[out:json][timeout:10];node(1);out body;'
 (raw/(label+'.overpass')).write_text(query)
 builder.write_bytes(raw/(label+'.json.gz'),gzip.compress(b'{"elements":[]}'))
 with patch.object(builder,'RAW',raw),patch.object(builder.fcntl,'flock',side_effect=AssertionError('保存済み入力で通信待機を要求した')):
  assert builder.overpass(label,query)['elements']==[]
  try:builder.overpass(label,query.replace('node(1)','node(2)'))
  except ValueError:pass
  else:raise AssertionError('クエリ不一致を検出しない')
print('PASS: 通信待機中の成功入力の再利用・クエリ不一致の検出')

# 応答に20秒かかっても、その直後に次の問い合わせを送らない。
from types import SimpleNamespace
with tempfile.TemporaryDirectory() as directory:
 clock=[100.0];starts=[]
 def response(*args,**kwargs):
  starts.append(clock[0]);clock[0]+=20
  return SimpleNamespace(returncode=0,stdout=b'{"elements":[]}\n200',stderr=b'')
 def pause(seconds):clock[0]+=seconds
 with patch.object(builder,'RAW',Path(directory)),patch.object(builder.subprocess,'run',side_effect=response),patch.object(builder.time,'time',side_effect=lambda:clock[0]),patch.object(builder.time,'sleep',side_effect=pause):
  builder.overpass('first','[out:json];node(1);out body;')
  builder.overpass('second','[out:json];node(2);out body;')
 assert starts==[100,130],starts
print('PASS: 長い応答の完了後にもOverpass問い合わせの最低10秒間隔を確保')
