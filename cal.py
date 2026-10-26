# -*- coding: utf-8 -*-
"""캠페인 일정 — 방문·체험 예약일, 글 마감일, 공구 시작일을 달력 파일(.ics)로.

앱은 창을 닫으면 꺼지니 알림은 폰·PC 달력에 맡긴다 — .ics 를 받아 달력에 넣으면 알림(VALARM)까지 같이 들어간다.
UID 는 캠페인 id + 종류로 고정이라, 다시 받아 넣으면 달력 앱이 같은 일정으로 알아본다(앱마다 다르다).
"""
from datetime import datetime, timedelta

KINDS = {"visit": "방문·체험", "deadline": "글 마감", "start": "공구 시작"}


def events(camps):
    """진행 중인 캠페인 → [{camp, kind, date, time, title}] (날짜 순)."""
    out = []
    for c in camps or ():
        if c.get("status") == "done":
            continue
        name = c.get("brand", "") + (" · " + c["title"] if c.get("title") else "")
        for kind, key in (("visit", "visit"), ("deadline", "deadline"), ("start", "start")):
            v = (c.get(key) or "").strip()
            if not v or (kind == "start" and c.get("kind") != "groupbuy"):
                continue
            date, _, time = v.partition("T")
            time = "" if time[:5] == "00:00" else time[:5]          # 0시 = 시간 모름 → 하루 종일
            out.append({"camp": c.get("id", ""), "kind": kind, "date": date, "time": time,
                        "title": "%s — %s" % (KINDS[kind], name)})
    return sorted(out, key=lambda e: (e["date"], e["time"] or "99"))


def _esc(s):
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _alarm(trigger, text):
    return ["BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:" + _esc(text), "TRIGGER:" + trigger, "END:VALARM"]


def ics(evs, now=None):
    """일정 → .ics 글자(CRLF). 시간 있는 방문은 하루 전·2시간 전, 하루 종일 일정은 전날·당일 아침 9시에 알림."""
    stamp = (now or datetime.now()).strftime("%Y%m%dT%H%M%S")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//PostKit//KO", "CALSCALE:GREGORIAN", "X-WR-CALNAME:체험단·협찬 일정"]
    for e in evs:
        try:
            d = datetime.strptime(e["date"], "%Y-%m-%d")
        except ValueError:
            continue
        lines += ["BEGIN:VEVENT", "UID:%s-%s@postkit" % (e["camp"], e["kind"]), "DTSTAMP:" + stamp, "SUMMARY:" + _esc(e["title"])]
        if e["time"]:
            t = datetime.strptime(e["date"] + " " + e["time"], "%Y-%m-%d %H:%M")
            lines += ["DTSTART:" + t.strftime("%Y%m%dT%H%M00"), "DTEND:" + (t + timedelta(hours=1)).strftime("%Y%m%dT%H%M00")]
            lines += _alarm("-P1D", "내일 " + e["title"]) + _alarm("-PT2H", "2시간 뒤 " + e["title"])
        else:
            lines += ["DTSTART;VALUE=DATE:" + d.strftime("%Y%m%d"), "DTEND;VALUE=DATE:" + (d + timedelta(days=1)).strftime("%Y%m%d")]
            lines += _alarm("-PT15H", "내일 " + e["title"]) + _alarm("PT9H", "오늘 " + e["title"])
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
