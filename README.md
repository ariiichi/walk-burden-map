Walk Burden Map shows the uphill effort hidden behind “minutes from a station.”  
It combines GSI elevation data with OpenStreetMap roads to show road gradients and station exit elevations.  
The map covers 96 stations in central Tokyo, with station names, slopes, and station interiors.

# 毎日の登りマップ

「駅徒歩7分」でも、帰り道が平坦か、坂を登るかで毎日の負担は変わります。この地図は、駅周辺の坂と出口の地表標高を表示する試作です。対象は、東京メトロ9路線、山手線30駅と内側のJR7駅、都営4路線の山手線上・内側を統合した96駅群です。都営は41駅名を収録し、乗換駅を統合しています。取得済みのOSM駅構内を重ねます。乗換駅は一覧で1つにまとめています。地図に駅名を表示し、出口の地表標高や周辺の坂を確認できます。ハッカソン応募用の制作物として、公開地理データで動くデモをまとめました。Claude Codeで作りました。

## 使い方

このフォルダをHTTPサーバーで配信して開きます。Python 3で起動する例：

```sh
python3 -m http.server 8103 --bind 127.0.0.1
```

ブラウザで `http://localhost:8103/` を開きます。坂・出口・構内は静的なJSONを必要な範囲だけ読むため、ファイルの直接表示（`file://`）には対応しません。

1. 地図上の駅名を目印に周辺の坂を確認します。駅名は「表示するもの」で切り替えられます。
2. 地図を移動すると、見ている区画の道路・坂・出口標高を読み込みます。「未収録」の表示は、その範囲に坂や駅がないという意味ではありません。
3. 駅構内は「路線→駅」で選びます。ホーム・通路・出口・階の収録状況を表示します。「選んだ駅を拡大」で構内を重ね、階と地表出口の表示を切り替えられます。
4. 「立体表示」で、選択駅の収録済み設備を斜めから見られます。「高さの誇張」で倍率を変え、「平面に戻る」で戻ります。WebGL対応ブラウザが必要です。

背景は都心の一部のOpenFreeMapタイルを同梱しています。その範囲をはみ出すと、キー不要のオンラインOpenFreeMapへ切り替えます。オンライン背景を読めない場合は同梱範囲だけを表示します。同梱範囲外でも、取得済みの道路・坂・構内JSONは表示できます。

駅構内はOSM収録分のみです。駅所属には周辺の駅代表点から450m以内の最近接による推定を含みます。駅全体の網羅、改札内外、設備の接続、通行可否は保証しません。路線色は元タグまたはOSM路線メンバーで確認できたものだけに使い、未確認は灰色にします。公式・民間の構内図は転載許可がないため使わず、構内の形状・設備はOSMのデータだけを使っています。

元のlevel値は保持します。JRホームには近傍OSM線路から推定した地上0・高架1の模式階を含み、詳細に原levelと推定根拠を表示します。立体表示は地上・高架も地面の上に描き、level 0は見やすさのため4m浮かせます。階間は約5m、初期3倍の模式表現で、実測床高や切通しと道路の高低差は再現しません。出口の接続階は最寄り設備からの推定を含みます。出口標高は地表の値で、地下の深さには換算しません。平面ではズーム16以上でホーム・出口、17以上で通路・階段、18以上で出口番号と標高を表示します。

駅ごとの収録・未収録は [全駅の収録状況](docs/STATIONS_COVERAGE.md) を参照してください。

駅名は96駅群の代表点付近に表示します。広域では主要駅を優先して間引き、拡大すると全駅を対象に重なりを避けて配置します。カラー背景の対応駅名は独自ラベルにまとめ、国土地理院の背景ではズーム15以上で背景側の駅名を使います。

## 計算しているもの

| 表示 | 計算・データ |
| --- | --- |
| 道路の勾配 | DEM1A（1m）、不足分はDEM5A。道路に沿って約5mごとに読み、5点移動平均後、約20m区間の勾配を計算。4%以上を表示 |
| 地点の標高 | DEM1A・不足分DEM5Aの地表標高。未取得は数値を補わない |

同じ駅でも出入口によって地表の標高が違います。六本木一丁目駅の収録データでは、3番出口が12.99m、2番出口が25.07mで、12.08mの差があります（国土地理院DEM1Aによる地表標高）。駅名と徒歩分数だけでは、この違いは読み取れません。

## 計算上の注意

- 坂道表示では橋・地下等の構造物と誤差の大きい通路を除き、幹線道路の12%超・その他の25%超を表示しません。地表の標高は橋・擁壁・段差などで歩行面と一致しないことがあります。
- 地下鉄の階はOSMタグです。ホームまでの表示距離は直線距離で、実際の歩行距離や時間ではありません。

## データの再生成

表示だけならビルドは不要です。保存済みの駅別計算キャッシュから、道路・坂・出口の約1km区画と起動用の `data.js` を生成できます。

```sh
python3 data/build_bundle.py
```

駅を追加する入口は `data/build_area.py` です。駅リストから道路網・構内・標高・勾配・出口標高を取得・計算し、区画と駅別JSONを出力します。取得にはnumpy・Pillowとネット接続が必要です。

```sh
python3 data/build_area.py --stations-file data/station-list.json
```

入力の形式、生データの保存先、再開・再生成方法は [エリア・駅を追加する手順](docs/EXPANSION_ARCHITECTURE.md) にまとめています。新規のOverpass原JSONは `data/raw/expansion/` にgzipで保存し、取得日時・クエリ・SHA-256を記録します。国土地理院の原DEMタイルも保存します。取得した原入力は公開ファイルには同梱していません。

確認コマンド：

```sh
node --check app.js
node --check area-loader.js
node --check station-interiors.js
node --check station-labels.js
node --check walk3d.js
node tests/station-interiors.test.cjs
node tests/station-labels.test.cjs
node tests/area-loader.test.cjs
node tests/walk3d.test.cjs
python3 tests/check_station_data.py
python3 tests/check_expansion.py
.venv/bin/python tests/check_area_build.py  # numpy/Pillow環境
.venv/bin/python tests/check_metro.py      # 7路線の全停止点・別名統合
.venv/bin/python tests/check_jr.py      # JR37駅・模式階・原入力照合
.venv/bin/python tests/check_toei.py      # 都営4線・全停止点・収録表
```

| スクリプト | 用途 |
| --- | --- |
| `data/build_area.py` | 駅リストから取得・標高・勾配・駅別出力・区画更新までを実行 |
| `data/discover_toei.py` | 都営4線の原路線・停止点から対象駅を判定し、既存駅へ統合 |
| `data/build_coverage.py` | 現行駅JSONから全駅の収録状況表を生成 |
| `data/discover_metro.py` / `data/discover_jr.py` | 東京メトロ・JRの駅を路線原入力から列挙し、ローカルの中間リストへ保存 |
| `data/split_bundle.py` / `data/build_bundle.py` | 駅別計算キャッシュを区画化し、起動用データを生成 |
| `data/station_geometry.py` | 階タグと座標距離の共通処理 |
| `data/build_subway.py` | OSM原JSONから地下鉄概観を抽出 |
| `data/build_basemap.py` | 背景地図の同梱処理。同梱範囲のタイルを取得 |

駅の列挙をやり直す場合は、路線群の入力を次の順に統合します。中間リストは非公開の `data/raw/expansion/` に保存し、最後に `data/station-list.json` を出力します。保存済み原入力のない問い合わせには通信が必要です。

```sh
python3 data/discover_metro.py
python3 data/discover_jr.py
python3 data/discover_toei.py
```

## 出典・ライセンス

コードはMIT Licenseです。地理データと第三者ライブラリには各出典の利用条件が適用されます。

- 出口標高・勾配：国土地理院の標高タイルを加工。[標高タイル仕様](https://maps.gsi.go.jp/development/demtile.html)・[国土地理院コンテンツ利用規約](https://www.gsi.go.jp/kikakuchousei/kikakuchousei40182.html)
- 道路・駅出入口・地物・地下鉄：© OpenStreetMap contributors / [ODbL](https://www.openstreetmap.org/copyright)
- 駅構内レイヤー：© OpenStreetMap contributors / [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/)。OSMの位置・形状・階タグを保持して駅別GeoJSONへ加工。国土地理院の地表標高を出口へ付与。公式・民間構内図の図版は収録・トレースしていません。
- 同梱カラー背景： [OpenFreeMap](https://openfreemap.org/) / © OpenMapTiles / © OpenStreetMap contributors
- 描画：Leaflet・[MapLibre GL JS](https://maplibre.org/)

詳細と同梱ライセンスの場所は [ATTRIBUTION.md](ATTRIBUTION.md) を参照してください。

## JRの収録範囲

対象は山手線30駅と、内側の千駄ケ谷・信濃町・四ツ谷・市ケ谷・飯田橋・水道橋・御茶ノ水の7駅。JR山手線、JR中央・総武線、JR中央線快速から駅を選べます。他のJR系統が乗り入れる駅も駅として含みますが、その全系統の路線別一覧は対象外です。同名の地下鉄駅を一覧で統合し、原宿は明治神宮前、御徒町は上野広小路・仲御徒町と1項目にまとめています。接続・乗換経路は未検証です。

OSMの複数輪郭から成るホームは、原wayの端点が一致し、閉じた面を作れる場合だけ結合します。穴も残し、欠けた輪郭は補いません。地上の入口もOSMの収録分だけで、出口が0件の駅は未収録と表示します。現在の駅リストは `data/station-list.json`。取得原データ・クエリ・日時・SHA-256は `data/raw/expansion/` に保存しています。

信濃町はホーム形状を収録していますが、ホームのlevelは未記載で、近傍の同路線線路にtunnel=yesがあるため、地上階を補わず「階未収録」と表示します。階の分からないホームは立体表示に描きません。

## 都営地下鉄の収録範囲

浅草線6駅、三田線15駅、新宿線7駅、大江戸線17駅が対象です（路線間の重複を除くと41駅名）。東京メトロ・JRと合わせて96駅群を選べます。新宿と新宿西口を1項目にまとめるため、大江戸線の一覧は16駅群です。対象判定は、OSM山手線の停止点を結ぶ多角形と境界駅名で行います。線路の曲線や駅敷地の境界とは異なり、都庁前・汐留・東銀座・岩本町などは今回の範囲外です。対象外も [全駅の収録状況](docs/STATIONS_COVERAGE.md) に記載しています。

同名駅は既存IDに統合し、別名の新線新宿・新宿西口、春日、小川町、上野御徒町、三田、大門、国立競技場も対応する駅群にまとめています。泉岳寺と高輪ゲートウェイは別駅です。元の停止点・駅名・座標は駅リストに残しています。一覧の統合は、構内の接続や歩行可能な乗換経路を確認したものではありません。

ホーム・通路・階段・EV・出口・階はOSMにある分だけ表示します。統合駅の件数は複数路線の合計で、各路線の構内全体がそろったことを示す数値ではありません。周辺の坂は国土地理院DEMから計算し、出口には地表標高を付けています。設備や階の欠測、駅所属の推定は画面と収録表で確認できます。

```sh
python3 data/build_area.py --rebuild --stations-file data/station-list.json
python3 data/build_coverage.py
```

原レスポンス・取得日・クエリは `data/raw/expansion/` に保存し、成功済み入力を再利用します。全駅の件数・欠測は [STATIONS_COVERAGE.md](docs/STATIONS_COVERAGE.md)、処理方法と制約は [追加手順](docs/EXPANSION_ARCHITECTURE.md) を参照してください。
