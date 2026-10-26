"""背景のカラー地図（OpenFreeMap / OpenStreetMap）を、この地図の範囲だけ同梱用に保存する。

ネット接続に依存せず背景を表示できるよう、
地図の部品（ベクタータイル・アイコン・欧文フォント・スタイル）をページと一緒に置く。
日本語の文字は端末のフォントで描くので、フォントは欧文・記号の範囲だけでよい。

使い方: python3 data/build_basemap.py 南 西 北 東
例:     python3 data/build_basemap.py 35.665 139.700 35.710 139.775
出力:   vendor/basemap/（style.json・tiles/・sprite/・fonts/）
出典:   OpenFreeMap（https://openfreemap.org）© OpenMapTiles © OpenStreetMap contributors
"""
import base64, json, math, sys, urllib.parse, urllib.request
# タイルとフォントは同梱形式に合わせてBase64のテキスト（.pbf.txt）で保存し、
# app.js の b64:// 読み込み（maplibregl.addProtocol）で元のバイナリに戻す。
b64 = lambda data: base64.b64encode(data).decode()
from pathlib import Path

s, w, n, e = map(float, sys.argv[1:5])
OUT = Path(__file__).resolve().parent.parent / 'vendor' / 'basemap'
UA = {'User-Agent': 'walk-burden-map/1.0'}
get = lambda url: urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()

style = json.loads(get('https://tiles.openfreemap.org/styles/liberty'))
tilejson = json.loads(get(style['sources']['openmaptiles']['url']))
template = tilejson['tiles'][0]

def tile(lat, lon, z):
    x = int((lon + 180) / 360 * 2 ** z)
    y = int((1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * 2 ** z)
    return x, y
count = 0
for z in range(13, 15):  # 地図は拡大表示のみ（Leafletのズーム14〜19＝この地図データのズーム13〜18）。14より上は14を拡大
    x0, y0 = tile(n, w, z); x1, y1 = tile(s, e, z)
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            f = OUT / 'tiles' / str(z) / str(x) / f'{y}.pbf.txt'
            if not f.exists():
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(b64(get(template.format(z=z, x=x, y=y))))
            count += 1

sprite = style['sprite']
(OUT / 'sprite').mkdir(parents=True, exist_ok=True)
for suffix in ['.json', '.png', '@2x.json', '@2x.png']:
    (OUT / 'sprite' / f'ofm{suffix}').write_bytes(get(sprite + suffix))

# フォント名の空白をファイル名から外す（公開時のパスを単純にするため）
stacks = {}
for layer in style['layers']:
    tf = layer.get('layout', {}).get('text-font')
    if tf:
        key = tf[0].replace(' ', '')
        stacks[key] = tf[0]
        layer['layout']['text-font'] = [key]
    if layer.get('layout', {}).get('text-field') and 'name' in json.dumps(layer['layout']['text-field']):
        layer['layout']['text-field'] = ['coalesce', ['get', 'name:ja'], ['get', 'name']]  # 日本語表記を優先
ranges = ['0-255', '256-511', '8192-8447', '8448-8703', '8704-8959', '9472-9727', '12288-12543', '65024-65279', '65280-65535']
for key, name in stacks.items():
    d = OUT / 'fonts' / key; d.mkdir(parents=True, exist_ok=True)
    for r in ranges:
        try:
            (d / f'{r}.pbf.txt').write_text(b64(get(f"https://tiles.openfreemap.org/fonts/{urllib.parse.quote(name)}/{r}.pbf")))
        except Exception:
            (d / f'{r}.pbf.txt').write_text('')  # 無い範囲は空ファイル（その文字だけ描かれない）

# 外部の陰影画像（低ズーム用）は使わないので外す。URLは app.js が読み込み時に絶対パスへ直す
style['layers'] = [l for l in style['layers'] if l.get('source') != 'ne2_shaded']
style['sources'] = {'openmaptiles': {'type': 'vector', 'tiles': ['b64://vendor/basemap/tiles/{z}/{x}/{y}.pbf.txt'], 'minzoom': 13, 'maxzoom': 14,
                                     'bounds': [w, s, e, n], 'attribution': tilejson.get('attribution', '')}}
style['sprite'] = 'vendor/basemap/sprite/ofm'
style['glyphs'] = 'b64://vendor/basemap/fonts/{fontstack}/{range}.pbf.txt'
(OUT / 'style.json').write_text(json.dumps(style, ensure_ascii=False, separators=(',', ':')))
(OUT / 'SOURCE.txt').write_text(f'OpenFreeMap liberty style / tiles {template}\n範囲 {s},{w},{n},{e} / ズーム13〜14\n© OpenFreeMap © OpenMapTiles © OpenStreetMap contributors (ODbL)\n')
print('tiles', count, 'fonts', list(stacks))
