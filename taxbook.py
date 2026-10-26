# -*- coding: utf-8 -*-
"""장부 → 종합소득세 신고 준비용 엑셀(요약·내역·월별·업체별).

세금 계산은 하지 않는다 — 소득 구분(사업·기타소득)·경비는 사람마다 달라서 홈택스·세무사 몫으로 남기고,
여기선 "1년 동안 무엇을 얼마 받았고 얼마 떼였나"를 신고 자료와 맞춰 보기 좋게 모은다.
"""
import xlsx

NOTES = [
    "• 협찬 물품·식사권도 소득으로 볼 수 있어요. 「물품 가액」은 내가 적은 시가예요.",
    "• 원고료에서 3.3%가 떼였다면 업체가 신고(지급명세서)를 했다는 뜻이에요. 홈택스 종합소득세 신고 도움 자료와 「업체별」 시트를 맞춰 보세요.",
    "• 종합소득세 신고는 매년 5월(홈택스·손택스)이에요. 소득 구분과 경비 처리는 홈택스나 세무사에게 확인하세요 — 이 파일은 기록 정리용이에요.",
]


def _n(v):
    try:
        return int(round(float(str(v or 0).replace(",", ""))))
    except ValueError:
        return 0


def _sum(vals, rng):
    return {"v": sum(vals), "f": "SUM(%s)" % rng, "s": "bnum"}


def build(rows, year, plat_names=None):
    """장부 행들(그해 것만 골라서) → xlsx 바이트."""
    plat_names = plat_names or {}
    rows = sorted([r for r in rows if str(r.get("date", "")).startswith(str(year))], key=lambda r: r.get("date", ""))
    cash = [_n(r.get("amount")) for r in rows]
    goods = [_n(r.get("value")) for r in rows]
    tax = [_n(r.get("tax")) for r in rows]
    n = len(rows)
    last = n + 1                                             # 내역 시트 마지막 데이터 행

    # 내역
    detail = [[{"v": h, "s": "head"} for h in ("날짜", "종류", "플랫폼", "업체·내용", "받은 돈", "물품 가액", "합계", "떼인 세금", "실제 받은 돈", "글 주소", "메모")]]
    for i, r in enumerate(rows, 2):
        detail.append([r.get("date", ""), r.get("kind", ""), plat_names.get(r.get("platform"), r.get("platform", "")), r.get("what", ""),
                       cash[i - 2], goods[i - 2], {"v": cash[i - 2] + goods[i - 2], "f": "E%d+F%d" % (i, i)},
                       tax[i - 2], {"v": cash[i - 2] - tax[i - 2], "f": "E%d-H%d" % (i, i)}, r.get("url", ""), r.get("memo", "")])
    if n:
        detail.append([{"v": "합계", "s": "bold"}, "", "", {"v": "%d건" % n, "s": "bold"},
                       _sum(cash, "E2:E%d" % last), _sum(goods, "F2:F%d" % last), _sum([a + b for a, b in zip(cash, goods)], "G2:G%d" % last),
                       _sum(tax, "H2:H%d" % last), _sum([a - b for a, b in zip(cash, tax)], "I2:I%d" % last)])

    # 요약
    ref = lambda c: "'내역'!%s2:%s%d" % (c, c, last)        # noqa: E731
    summary = [[{"v": "항목", "s": "head"}, {"v": "금액(원)", "s": "head"}],
               ["연도", str(year)],
               ["받은 돈 합계", {"v": sum(cash), "f": "SUM(%s)" % ref("E"), "s": "bnum"}],
               ["물품 가액 합계", {"v": sum(goods), "f": "SUM(%s)" % ref("F"), "s": "bnum"}],
               [{"v": "총수입 (받은 돈 + 물품)", "s": "bold"}, {"v": sum(cash) + sum(goods), "f": "B3+B4", "s": "bnum"}],
               ["떼인 세금 합계 (원천징수)", {"v": sum(tax), "f": "SUM(%s)" % ref("H"), "s": "bnum"}],
               ["건수", n],
               [],
               [{"v": "종류별", "s": "head"}, {"v": "합계(원)", "s": "head"}]]
    for k in sorted({r.get("kind", "") for r in rows}):
        v = sum(c + g for r, c, g in zip(rows, cash, goods) if r.get("kind", "") == k)
        summary.append([k or "(없음)", {"v": v, "f": "SUMIF(%s,A%d,%s)" % (ref("B"), len(summary) + 1, ref("G")), "s": "num"}])
    summary.append([])
    summary += [[{"v": t, "s": "note"}] for t in NOTES]

    # 월별
    month = [[{"v": h, "s": "head"} for h in ("월", "건수", "받은 돈", "물품 가액", "합계", "떼인 세금")]]
    for m in range(1, 13):
        idx = [i for i, r in enumerate(rows) if str(r.get("date", ""))[5:7] == "%02d" % m]
        c, g, t = sum(cash[i] for i in idx), sum(goods[i] for i in idx), sum(tax[i] for i in idx)
        k = len(month) + 1
        month.append(["%d월" % m, len(idx), c, g, {"v": c + g, "f": "C%d+D%d" % (k, k)}, t])
    month.append([{"v": "합계", "s": "bold"}, {"v": n, "f": "SUM(B2:B13)", "s": "bnum"}, _sum(cash, "C2:C13"), _sum(goods, "D2:D13"),
                  _sum(cash + goods, "E2:E13"), _sum(tax, "F2:F13")])

    # 업체별 — 지급명세서와 맞춰 보기
    by = {}
    for r, c, g, t in zip(rows, cash, goods, tax):
        w = (r.get("what") or "(없음)").strip()
        a = by.setdefault(w, [0, 0, 0, 0])
        a[0] += 1; a[1] += c; a[2] += g; a[3] += t                 # noqa: E702
    payer = [[{"v": h, "s": "head"} for h in ("업체·내용", "건수", "받은 돈", "물품 가액", "합계", "떼인 세금")]]
    for w, (k, c, g, t) in sorted(by.items(), key=lambda x: -(x[1][1] + x[1][2])):
        payer.append([w, k, c, g, c + g, t])

    return xlsx.build([("요약", summary, [30, 16]),
                       ("내역", detail, [11, 11, 12, 28, 12, 12, 12, 11, 13, 36, 24]),
                       ("월별", month, [8, 8, 13, 13, 13, 12]),
                       ("업체별", payer, [30, 8, 13, 13, 13, 12])])
