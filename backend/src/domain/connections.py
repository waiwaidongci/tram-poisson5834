"""路口阻断对接驳乘客的影响：按班次跨系统对账，双队列试算接驳余座。"""

from collections import defaultdict, deque

_MAX_ROWS = 5000
_RECORDS = ("班次到发", "接驳余座", "晚到更正")
_BUCKETS = {"班次到发": "trips", "接驳余座": "departures", "晚到更正": "corrections"}


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}不能为空")
    return value.strip()


def _clock(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label}须为 HH:MM 时刻")
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"{label}须为 HH:MM 时刻")
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        raise ValueError(f"{label}须为 HH:MM 时刻") from None
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"{label}须在 00:00 至 23:59 之间")
    return f"{hour:02d}:{minute:02d}"


def _amount(value, label, upper, optional=False):
    if value is None:
        if optional:
            return None
        raise ValueError(f"{label}不能为空")
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= upper:
        raise ValueError(f"{label}须为 0 至 {upper} 之间的整数")
    return value


def validate_rows(rows):
    if not isinstance(rows, (list, tuple)) or not 1 <= len(rows) <= _MAX_ROWS:
        raise ValueError(f"接驳对账台账须包含 1 至 {_MAX_ROWS} 行")
    records = []
    for index, row in enumerate(rows, start=1):
        try:
            if not isinstance(row, dict):
                raise ValueError("须为一条对账记录")
            kind = row.get("record")
            if kind not in _RECORDS:
                raise ValueError(f"记录类型须为{'、'.join(_RECORDS)}之一")
            item = {"record": kind, "date": _text(row.get("date"), "日期"),
                    "point": _text(row.get("point"), "接驳点")}
            if kind == "班次到发":
                item.update(trip=_text(row.get("trip"), "电车班次"),
                            arrival=_clock(row.get("arrival"), "实到时刻"),
                            delay_min=_amount(row.get("delay_min"), "确认阻断延误", 240, optional=True),
                            waiting=_amount(row.get("waiting"), "待换乘人数", 5000, optional=True))
            elif kind == "接驳余座":
                item.update(departure=_clock(row.get("departure"), "接驳发车时刻"),
                            seats=_amount(row.get("seats"), "接驳余座", 5000))
            else:
                item.update(trip=_text(row.get("trip"), "电车班次"),
                            arrival=_clock(row.get("arrival"), "更正后实到时刻"))
            records.append(item)
        except ValueError as error:
            raise ValueError(f"第 {index} 条记录 · {error}") from None
    return records


def _minutes(stamp):
    hour, minute = stamp.split(":")
    return int(hour) * 60 + int(minute)


def _stamp(minutes):
    day, clock = divmod(minutes, 1440)
    text = f"{clock // 60:02d}:{clock % 60:02d}"
    return f"前一日 {text}" if day < 0 else text


def _simulate(groups, departures):
    """同一组接驳余座上的先到先上排队：坐不下等下一班，末班走后记为没搭上。"""
    ordered = sorted(groups, key=lambda group: (group["arrival"], group["order"]))
    boardings = {group["trip"]: [] for group in ordered}
    stranded = {group["trip"]: 0 for group in ordered}
    loads = {}
    queue = deque()
    index = 0
    for departure, seats in departures:
        while index < len(ordered) and ordered[index]["arrival"] <= departure:
            if ordered[index]["waiting"]:
                queue.append([ordered[index]["trip"], ordered[index]["waiting"]])
            index += 1
        remaining = seats
        while remaining and queue:
            head = queue[0]
            take = min(remaining, head[1])
            boardings[head[0]].append((departure, take))
            loads[departure] = loads.get(departure, 0) + take
            head[1] -= take
            remaining -= take
            if not head[1]:
                queue.popleft()
    for trip, waiting in queue:
        stranded[trip] += waiting
    for group in ordered[index:]:
        stranded[group["trip"]] += group["waiting"]
    return boardings, stranded, loads


def _allocations(boardings):
    allocation = defaultdict(dict)
    for trip, legs in boardings.items():
        for departure, count in legs:
            allocation[departure][trip] = count
    return allocation


def _sequence(boardings, stranded, trip):
    return [departure for departure, count in boardings[trip] for _ in range(count)] + [None] * stranded[trip]


def _legs(legs, stranded):
    parts = [f"{_stamp(departure)}×{count}" for departure, count in legs]
    if stranded:
        parts.append(f"未搭上×{stranded}")
    return "、".join(parts) or "—"


def _reconcile(day, point, bucket, gaps_out):
    """跨系统对账：来源对不齐的接驳点只报缺口，返回 None 表示不参与试算。"""
    gaps = []
    names = [record["trip"] for record in bucket["trips"]]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        gaps.append({"gap": f"同一班次有多条到发记录：{'、'.join(duplicates)}", "records": len(duplicates),
                     "waiting": None})
    times = [record["departure"] for record in bucket["departures"]]
    duplicates = sorted({time for time in times if times.count(time) > 1})
    if duplicates:
        gaps.append({"gap": f"同一发车时刻有多条接驳余座：{'、'.join(duplicates)}", "records": len(duplicates),
                     "waiting": None})
    fixed = [record["trip"] for record in bucket["corrections"]]
    duplicates = sorted({name for name in fixed if fixed.count(name) > 1})
    if duplicates:
        gaps.append({"gap": f"同一班次有多条晚到更正：{'、'.join(duplicates)}", "records": len(duplicates),
                     "waiting": None})
    trips = {record["trip"]: record for record in bucket["trips"]}
    unknown = sorted({name for name in fixed if name not in trips})
    if unknown:
        gaps.append({"gap": f"晚到更正找不到对应班次：{'、'.join(unknown)}", "records": len(unknown),
                     "waiting": None})
    incomplete = sorted(record["trip"] for record in bucket["trips"]
                        if record["delay_min"] is None or record["waiting"] is None)
    if incomplete:
        gaps.append({"gap": f"班次缺少确认阻断延误或待换乘人数：{'、'.join(incomplete)}",
                     "records": len(incomplete), "waiting": None})
    if bucket["trips"] and not bucket["departures"]:
        waiting = sum(record["waiting"] or 0 for record in bucket["trips"])
        gaps.append({"gap": "有班次到发但缺少接驳余座记录", "records": len(bucket["trips"]),
                     "waiting": waiting or None})
    if bucket["departures"] and not bucket["trips"]:
        gaps.append({"gap": "接驳余座没有对应班次到发记录", "records": len(bucket["departures"]),
                     "waiting": None})
    if gaps:
        gaps_out.extend({"date": day, "point": point, **gap} for gap in gaps)
        return None
    return trips


def _point_impact(day, point, trips, bucket, details, corrections_out):
    corrections = {record["trip"]: record["arrival"] for record in bucket["corrections"]}
    departures = sorted((_minutes(record["departure"]), record["seats"]) for record in bucket["departures"])
    base, actual, counter = [], [], []
    for order, record in enumerate(sorted(trips.values(), key=lambda item: item["trip"])):
        group = {"trip": record["trip"], "waiting": record["waiting"], "order": order}
        arrival = _minutes(corrections.get(record["trip"], record["arrival"]))
        base.append({**group, "arrival": _minutes(record["arrival"])})
        actual.append({**group, "arrival": arrival})
        counter.append({**group, "arrival": arrival - record["delay_min"]})
    actual_board, actual_stranded, _ = _simulate(actual, departures)
    counter_board, counter_stranded, _ = _simulate(counter, departures)
    changed = []
    if corrections:
        base_board, _, _ = _simulate(base, departures)
        before, after = _allocations(base_board), _allocations(actual_board)
        changed = sorted(departure for departure in set(before) | set(after)
                         if before.get(departure) != after.get(departure))
        for trip, corrected in sorted(corrections.items()):
            corrections_out.append({
                "date": day, "point": point, "trip": trip, "original": trips[trip]["arrival"],
                "corrected": corrected, "recomputed": len(changed),
                "departures": "、".join(_stamp(departure) for departure in changed) or "未引起接驳分配变化",
            })
    summary = {"date": day, "point": point, "trips": len(actual), "waiting": 0,
               "delayed": 0, "missed": 0, "departures": len(departures),
               "seats": sum(seats for _, seats in departures),
               "span": f"{_stamp(departures[0][0])}–{_stamp(departures[-1][0])}"}
    for group in actual:
        trip = group["trip"]
        summary["waiting"] += group["waiting"]
        delayed = missed = 0
        for have, want in zip(_sequence(actual_board, actual_stranded, trip),
                              _sequence(counter_board, counter_stranded, trip)):
            if want is None:
                continue
            if have is None:
                missed += 1
            elif have > want:
                delayed += 1
        if delayed or missed:
            record = trips[trip]
            details.append({
                "date": day, "point": point, "trip": trip, "arrival": _stamp(group["arrival"]),
                "delay": record["delay_min"], "counterfactual": _stamp(group["arrival"] - record["delay_min"]),
                "waiting": group["waiting"],
                "actual_board": _legs(actual_board[trip], actual_stranded[trip]),
                "counter_board": _legs(counter_board[trip], counter_stranded[trip]),
                "delayed": delayed, "missed": missed,
            })
        summary["delayed"] += delayed
        summary["missed"] += missed
    summary["affected"] = summary["delayed"] + summary["missed"]
    summary["basis"] = f"{summary['departures']} 班 · 余座 {summary['seats']} · {summary['span']}"
    return summary


def _table(title, columns, rows):
    return {"title": title, "columns": [{"key": key, "label": label} for key, label in columns], "rows": rows}


def analyze(rows, normalized_params):
    if normalized_params:
        raise ValueError("存在未知运行参数")
    records = validate_rows(rows)
    grouped = defaultdict(lambda: {"trips": [], "departures": [], "corrections": []})
    for record in records:
        grouped[(record["date"], record["point"])][_BUCKETS[record["record"]]].append(record)
    summaries, details, corrections_out, gaps_out = [], [], [], []
    for (day, point), bucket in sorted(grouped.items()):
        trips = _reconcile(day, point, bucket, gaps_out)
        if trips is not None:
            summaries.append(_point_impact(day, point, trips, bucket, details, corrections_out))
    delayed = sum(summary["delayed"] for summary in summaries)
    missed = sum(summary["missed"] for summary in summaries)
    affected = delayed + missed
    gap_points = len({(gap["date"], gap["point"]) for gap in gaps_out})
    recomputed = sum(item["recomputed"] for item in corrections_out)
    if affected:
        headline = f"{affected} 名接驳乘客因路口阻断晚搭上或没搭上（晚搭上 {delayed} · 没搭上 {missed}）。"
    else:
        headline = "本批接驳乘客没有因路口阻断晚搭上或没搭上。"
    if gap_points:
        headline += f"{gap_points} 个接驳点来源对不齐，只报缺口。"
    note = (f"对账 {len(grouped)} 个接驳点服务日：{len(summaries)} 个完成双队列试算，{gap_points} 个只报缺口。"
            f"晚到更正 {len(corrections_out)} 条，重算后续接驳班次 {recomputed} 班。")
    tables = [
        _table("接驳点影响汇总", (("date", "日期"), ("point", "接驳点"), ("trips", "电车班次"),
               ("waiting", "待换乘人数"), ("affected", "受影响人数"), ("delayed", "其中晚搭上"),
               ("missed", "其中没搭上"), ("basis", "接驳依据")), summaries),
        _table("班次影响明细", (("date", "日期"), ("point", "接驳点"), ("trip", "电车班次"),
               ("arrival", "实到时刻"), ("delay", "确认延误（分钟）"), ("counterfactual", "无阻断时刻"),
               ("waiting", "待换乘人数"), ("actual_board", "实际搭上"), ("counter_board", "无阻断搭上"),
               ("delayed", "晚搭上"), ("missed", "没搭上")), details),
    ]
    if corrections_out:
        tables.append(_table("晚到更正重算", (("date", "日期"), ("point", "接驳点"), ("trip", "电车班次"),
                             ("original", "原实到时刻"), ("corrected", "更正后实到"),
                             ("recomputed", "重算班次数"), ("departures", "被重算的接驳班次")), corrections_out))
    if gaps_out:
        tables.append(_table("来源缺口（只报缺口）", (("date", "日期"), ("point", "接驳点"), ("gap", "缺口说明"),
                             ("records", "涉及记录"), ("waiting", "涉及待换乘人数")), gaps_out))
    return {
        "state": "warning" if gaps_out else "ok",
        "headline": headline,
        "note": note,
        "metrics": [
            {"label": "受影响乘客", "value": affected, "detail": f"晚搭上 {delayed} · 没搭上 {missed}"},
            {"label": "涉及班次", "value": len(details),
             "detail": f"共试算 {sum(summary['trips'] for summary in summaries)} 班电车"},
            {"label": "试算接驳点", "value": len(summaries),
             "detail": f"接驳 {sum(summary['departures'] for summary in summaries)} 班 · "
                       f"余座 {sum(summary['seats'] for summary in summaries)}"},
            {"label": "晚到更正", "value": len(corrections_out), "detail": f"重算后续接驳班次 {recomputed} 班"},
            {"label": "对不齐接驳点", "value": gap_points, "detail": "来源对不齐，只报缺口，未纳入试算"},
        ],
        "charts": [
            {"title": "各接驳点受影响人数", "kind": "bar", "series": [
                {"label": f"{summary['date']} {summary['point']}", "value": summary["affected"]}
                for summary in summaries]},
            {"title": "影响构成", "kind": "bar", "series": [
                {"label": "晚搭上", "value": delayed}, {"label": "没搭上", "value": missed}]},
        ],
        "tables": tables,
        "sections": [
            {"title": "对账口径", "text": "按电车班次核对实到时刻、沿途确认的阻断延误和待换乘人数。"
             "班次或发车时刻重复、更正找不到班次、缺确认延误或待换乘人数、缺接驳余座的接驳点，"
             "来源对不齐，只报缺口，不参与试算。"},
            {"title": "排队口径", "text": "同一接驳点同一日期共用一组接驳余座，按到达时刻先到先上，"
             "坐不下的乘客等下一班，末班走后仍未上车的记为没搭上。实际队列用更正后的实到时刻，"
             "无阻断队列用实到扣除确认阻断延误后的时刻，两边用同一组接驳余座各排一次。"},
            {"title": "影响口径", "text": "只算实际队列比无阻断队列晚搭上或没搭上的乘客，"
             "无阻断时同样没搭上的不计入。晚到更正先更新实到时刻，再重算被挤占座位的后续接驳班次，"
             "更正对照表列出分配发生变化的班次。"},
        ],
    }
