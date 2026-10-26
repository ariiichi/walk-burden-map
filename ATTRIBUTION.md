# データと同梱ソフトウェアの出典

独自のコードにはルートの [LICENSE](LICENSE)（MIT）が適用されます。以下のデータ・第三者ソフトウェアをMITで再許諾するものではありません。

| 対象 | 出典・利用条件 |
| --- | --- |
| 出口の地表標高、道路勾配の計算値 | 国土地理院の標高タイル（DEM1A・DEM5A）を加工して作成。[国土地理院コンテンツ利用規約](https://www.gsi.go.jp/kikakuchousei/kikakuchousei40182.html)・[標高タイル仕様](https://maps.gsi.go.jp/development/demtile.html) |
| `data/osm/subway.json`、`data/areas/`、`data/stations/`、`data/station-list.json`、`data/processed/` | © OpenStreetMap contributors。[Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/)（ODbL）で提供。抽出・加工済みの公開データを同梱。[著作権表示](https://www.openstreetmap.org/copyright) |
| `data.js` | 上記の標高・OSM由来データをまとめたもの。元データの条件を引き継ぎます |
| `vendor/basemap/` | [OpenFreeMap](https://openfreemap.org/)のLibertyスタイルとタイル等を同梱・加工。© OpenMapTiles / © OpenStreetMap contributors（地図データはODbL）。取得元と範囲は [SOURCE.txt](vendor/basemap/SOURCE.txt)。[スタイルの原リポジトリ](https://github.com/hyperknot/openfreemap-styles)も参照 |
| 国土地理院のオンライン標準・淡色地図 | 国土地理院 [地理院タイル一覧](https://maps.gsi.go.jp/development/ichiran.html)。画面に出典表示 |
| Leaflet | BSD-2-Clause。[同梱ライセンス](vendor/LICENSE) |
| MapLibre GL JS | BSD-3-Clause。[同梱ライセンス・第三者通知](vendor/maplibre/LICENSE.txt) |
| MapLibreのLeaflet連携 | [maplibre-gl-leaflet](https://github.com/maplibre/maplibre-gl-leaflet)。ISC。[ライセンス原文](https://github.com/maplibre/maplibre-gl-leaflet/blob/main/LICENSE) |

データの数値・地物は取得時点の記録です。現在の通行条件、営業状況、標高精度を保証するものではありません。

## 駅構内レイヤー

駅別JSONの形状・階・設備区分は © OpenStreetMap contributors / [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/)（[OSM著作権表示](https://www.openstreetmap.org/copyright)）で提供します。加工データベースもODbLで公開し、各地物に元のOSM要素IDとタグを保持しています。出口には国土地理院DEMによる地表標高を付与しています。駅別・区画別に分けた加工データにも元データの条件が適用されます。

公式構内図・えきペディア等の図版をコピー・トレース・座標化したデータは含みません。採用する情報源と利用条件は [README](README.md#出典・ライセンス) を参照してください。

同梱背景のスタイルは配信パス・日本語ラベル設定等を変更しています。[OpenFreeMap Stylesのライセンス一覧](https://github.com/hyperknot/openfreemap-styles/blob/main/LICENSE.md)に従い、Liberty（OSM Bright / Mapbox Open Styles由来）のコードはBSD-3-Clause、デザインはCC BY 4.0、OpenFreeMap側のコードはMITとして扱います。欧文グリフはNoto Sans（SIL Open Font License 1.1）、アイコンはMaki（CC0）等に由来します。背景の帰属・利用条件はこの一覧と [OSM Libertyの原ライセンス](https://github.com/maputnik/osm-liberty/blob/gh-pages/LICENSE.md)を参照してください。

## 駅別・区画別データ

`data/raw/expansion/*.json.gz` はOverpass APIの原JSONを圧縮したものです。© OpenStreetMap contributors / [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/)。各取得の接続先・日時・クエリ・OSM基準時刻・SHA-256を同じフォルダに保存しています。

`data/stations/`、`data/area-index.json`、`data/station-index.json`、`data/areas/`、`data/processed/` は、上記と既存OSM入力を加工したデータベースです。OSM由来部分はODbLを引き継ぎます。駅所属に450m以内の最近接による推定を含み、元の形状・levelタグ・OSM IDを保持しています。詳しい加工内容は [追加手順](docs/EXPANSION_ARCHITECTURE.md) を参照してください。

駅の列挙はOSMの路線・停止点・駅ノードだけを使用しています。別名の乗換駅の統合は一覧上の編集規則であり、構内接続や歩行可能な乗換経路は未検証です。公式・民間の構内図のトレース・座標化は行っていません。

`data/raw/expansion/dem/` の原PNG、出口標高、坂の計算値は国土地理院のDEM1A・DEM5Aを利用・加工しています。各タイルの取得URL・日時・SHA-256も保存しています。地下の床の高さを表すものではありません。[標高タイル仕様](https://maps.gsi.go.jp/development/demtile.html)・[国土地理院コンテンツ利用規約](https://www.gsi.go.jp/kikakuchousei/kikakuchousei40182.html)に従い、画面でも出典を表示します。

同梱範囲外のオンライン背景は [OpenFreeMap](https://openfreemap.org/) / © OpenMapTiles / © OpenStreetMap contributors。APIキーは使用しません。背景タイルの同梱範囲は `vendor/basemap/SOURCE.txt` に記載しています。

JR駅・路線・地上/高架の判定にもOSMの駅カタログ・路線relation・停止点・近傍線路だけを使用しています。元のlevel値は保持し、模式階は推定根拠とともに区別して表示します。原クエリ・取得日時・SHA-256は `data/raw/expansion/jr-*.overpass`・`.metadata.json` に保存しています。処理方法は [追加手順](docs/EXPANSION_ARCHITECTURE.md) を参照してください。

都営4線もOSMの路線relation・停止点・駅カタログと国土地理院DEMだけを使用しています。取得した原レスポンス・クエリ・日時・SHA-256を `data/raw/expansion/` に保存し、保存済みの成功入力も再利用します。別名駅の統合は一覧の編集規則です。構内接続・通行可否の確認や公式図版のトレースは行っていません。[全駅の収録状況](docs/STATIONS_COVERAGE.md)を参照してください。
