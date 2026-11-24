"""澄浦 2 号线的可复现观测台账。"""

from datetime import date, timedelta
from math import exp
from random import Random


_INTERSECTIONS = (
    ("港湾路", "货栈街口", "混行"),
    ("港湾路", "渡口街口", "混行"),
    ("科创大道", "智造街口", "独立通行"),
    ("科创大道", "东环街口", "独立通行"),
)


def _poisson(rng, mean):
    limit = exp(-mean)
    product = rng.random()
    count = 0
    while product > limit:
        product *= rng.random()
        count += 1
    return count


def demo_rows():
    rng = Random(261160)
    rows = []
    for day in range(14):
        stamp = (date(2026, 11, 7) + timedelta(days=day)).isoformat()
        for road, intersection, track in _INTERSECTIONS:
            for shift in ("平峰", "高峰"):
                peak = shift == "高峰"
                exposure = (38 if peak else 20) + rng.randrange(13)
                rate = 0.035 * exp(0.9 * peak + 1.05 * (track == "混行"))
                rows.append({
                    "date": stamp, "road": road, "intersection": intersection,
                    "shift": shift, "track": track, "exposure": exposure,
                    "count": _poisson(rng, exposure * rate),
                })
    return rows


def _record(kind, day, point, **values):
    row = {"record": kind, "date": day, "point": point, "trip": None, "arrival": None,
           "delay_min": None, "waiting": None, "departure": None, "seats": None}
    row.update(values)
    return row


def demo_connection_rows():
    """澄浦 2 号线 11 月 20 日高峰的接驳对账台账，含一条晚到更正和一处对不齐的接驳点。"""
    day = "2026-11-20"
    rows = []
    # 港湾路站：早高峰接驳余座紧张，确认延误让换乘乘客错过原班次。
    for departure in ("08:00", "08:15", "08:30", "08:45"):
        rows.append(_record("接驳余座", day, "港湾路站", departure=departure, seats=40))
    rows.append(_record("班次到发", day, "港湾路站", trip="G201", arrival="07:50", delay_min=0, waiting=30))
    rows.append(_record("班次到发", day, "港湾路站", trip="G203", arrival="08:05", delay_min=12, waiting=35))
    rows.append(_record("班次到发", day, "港湾路站", trip="G205", arrival="08:12", delay_min=18, waiting=45))
    rows.append(_record("班次到发", day, "港湾路站", trip="G207", arrival="08:32", delay_min=0, waiting=20))
    rows.append(_record("班次到发", day, "港湾路站", trip="G209", arrival="08:50", delay_min=25, waiting=12))
    rows.append(_record("晚到更正", day, "港湾路站", trip="G205", arrival="08:26"))
    # 科创大道站：接驳余座充足，阻断延误没有影响换乘。
    rows.append(_record("接驳余座", day, "科创大道站", departure="09:00", seats=60))
    rows.append(_record("接驳余座", day, "科创大道站", departure="09:20", seats=60))
    rows.append(_record("班次到发", day, "科创大道站", trip="G301", arrival="08:50", delay_min=5, waiting=40))
    rows.append(_record("班次到发", day, "科创大道站", trip="G303", arrival="09:05", delay_min=0, waiting=30))
    # 东环街口站：缺少接驳余座来源，且有一条找不到班次的更正，只报缺口。
    rows.append(_record("班次到发", day, "东环街口站", trip="G401", arrival="10:05", delay_min=6, waiting=25))
    rows.append(_record("班次到发", day, "东环街口站", trip="G403", arrival="10:20", delay_min=0, waiting=18))
    rows.append(_record("晚到更正", day, "东环街口站", trip="G499", arrival="10:31"))
    return rows
