"""駅設備の階タグと座標距離の共通処理。"""
import math
import re


def levels(value):
    """明記された値のみ。範囲・不明な表記を展開しない。"""
    parts = str(value or '').split(';')
    if not all(re.fullmatch(r'-?\d+(?:\.\d+)?', p.strip()) for p in parts):
        return []
    return sorted(set(float(p) for p in parts), reverse=True)


def distance(a, b):
    return math.hypot((a[0] - b[0]) * 111000,
                      (a[1] - b[1]) * 111000 * math.cos(math.radians(a[0])))
