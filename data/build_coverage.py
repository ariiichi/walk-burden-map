"""現行駅索引から全駅群の収録状況表を生成。通信はしない。"""
import json
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def main():
    c=json.loads((ROOT/'data/station-list.json').read_text())
    stations=json.loads((ROOT/'data/station-index.json').read_text())['stations']
    assert {s['id'] for s in stations}=={s['id'] for s in c['stations']}, '未生成駅あり'
    text=['# 全駅の収録状況','',
          '2026-10-26 JST。現在の駅リスト `data/station-list.json` と現行の駅別JSONから生成。',
          f'対象{len(stations)}駅群。東京メトロ9路線、JR山手線30駅と内側7駅、都営4路線の山手線上・内側を収録する。',
          f'都営の対象は{len(c["toei_stations"])}駅名。別名統合後は{sum(bool(s.get("toei_names")) for s in stations)}駅群を収録する。',
          '対象範囲はOSM山手線の停止点を結ぶ多角形と境界駅名で判定する。線路の曲線・駅敷地そのものの境界ではない。',
          '', '## 路線別の対象', '', '| 路線 | 一覧の駅群数 |', '| --- | ---: |']
    for line in sorted({line for s in stations for line in s['lines']}):
        text.append(f'| {line} | {sum(line in s["lines"] for s in stations)} |')
    text+=['','路線間で重複する駅群を含む。都営の元駅名・停止点・対象外駅・統合規則は累計正本に保持する。',
           '', '## 全駅群', '',
           '数値はOSM地物の件数で、設備総数・ホーム番線数ではない。0は未収録を示す。近接による駅所属の推定を含む。',
           '統合駅では各路線・別名駅を合算するため、ホーム等があっても全所属路線の収録を保証しない。駅別JSONには確認できた路線所属を保存する。',
           '階は「階情報あり / 構内地物数」。出口を除く。階のない地物は補わず、画面で未収録と表示する。JRの地上・高架にはOSM線路からの模式階を含む。',
           '坂は周囲約800mの矩形内の道路をDEMで計算し、4%以上の区間を表示する。0区間でも平坦とは限らない。標高欠測道路は計算しない。',
           '', '| 駅群（駅別JSON） | 路線 | ホーム | 通路 | 階段 | EV | ES | 出口 | 出口標高あり | 階情報 | 坂区間 | 標高欠測道路 |',
           '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |']
    for s in sorted(stations,key=lambda s:s['name']):
        d=json.loads((ROOT/s['url']).read_text());fs=d['features'];n=s['counts'];t=s['terrain']
        interiors=[f for f in fs if f['properties']['kind']!='exit']
        known=sum(bool(f['properties']['levels']) for f in interiors)
        text.append(f'| [{s["name"]}](../{s["url"]}) | {"・".join(s["lines"])} | '+
                    ' | '.join(str(n[k]) for k in ['platform','corridor','stairs','elevator','escalator','exit','exit_elevation'])+
                    f' | {known}/{len(interiors)} | {t["slope_segments"]} | {t["missing_roads"]} |')
    total=Counter()
    for s in stations:total.update(s['counts'])
    text+=['',f'累計：ホーム{total["platform"]}、通路{total["corridor"]}、階段{total["stairs"]}、EV{total["elevator"]}、ES{total["escalator"]}、出口{total["exit"]}（標高あり{total["exit_elevation"]}）。',
           f'改札{total["gate"]}・コンコース面{total["concourse"]}件。0件は設備がないという意味ではない。',
           '', '## 一覧統合', '',
           '同名駅は既存IDへ統合。別名は以下の既存駅群にまとめ、元の停止点・駅名・座標を保持した。構内接続・改札内外・通行可否・歩行可能な乗換経路は未検証。',
           '', '| 都営の元駅名 | 統合先の駅群 |', '| --- | --- |']
    for name,target in c['toei_merge_aliases'].items():
        row=next((s for s in stations if name in s.get('toei_names',[])),None)
        if row:text.append(f'| {name} | {row["name"]} |')
    text+=['','泉岳寺と高輪ゲートウェイは別駅群として保持する。近いという理由だけで全ての別名駅を統合しない。',
           '', '## 都営の対象外駅', '',
           '4線の原routeに含まれる範囲外駅も判定記録を残す。都庁前・汐留などは今回の多角形の外側。設備の取得失敗・未収録とは異なる。',
           '', '| 駅名 | 路線 | 判定 |', '| --- | --- | --- |']
    for s in sorted(c['toei_excluded'],key=lambda s:s['name']):
        text.append(f'| {s["name"]} | {"・".join(s["lines"])} | 範囲外 |')
    text+=['','## 来歴と再生成','',
           'データ源はOpenStreetMap（Overpass、ODbL）と国土地理院DEM1A/DEM5A。原レスポンス、クエリ、日時、SHA-256は `data/raw/expansion/` に保存。公式・民間の構内図はトレースしていない。',
           '', '```sh','python3 data/build_coverage.py','```', '',
           '取得・再生成の手順と処理上の制約は [エリア・駅を追加する手順](EXPANSION_ARCHITECTURE.md) を参照。','']
    (ROOT/'docs/STATIONS_COVERAGE.md').write_text('\n'.join(text))


if __name__=='__main__':main()
