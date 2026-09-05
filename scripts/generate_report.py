#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
风水分析 HTML 报告生成器（yangzhai-fengshui skill）

用法：
  python generate_report.py --input data.json --output 风水报告.html --validate

输入 data.json 结构：
{
  "meta":    {"title": "报告标题（可选）"},
  "result":  { ...fengshui.py analyze_house 的 JSON（`all --json` 输出），必填... },
  "conclusion": {
      "verdict": "适合 | 有条件适合 | 须谨慎",
      "summary": "综合结论段落（必填，≥30字）",
      "suggestions": ["建议1", "建议2", ...],
      "room_notes": [{"name": "房间名", "verdict": "✅|⚠|❌", "text": "说明"}, ...]
  },
  "sections": [ {"title": "流年分析", "html": "<p>...</p>"}, ... ]   // 可选
}

--validate：校验 schema 与内容占位符，全部通过退出码 0。
"""
import sys
import json
import argparse
import html

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

STAR_NUM_NAME = {1: "一白", 2: "二黑", 3: "三碧", 4: "四绿", 5: "五黄",
                 6: "六白", 7: "七赤", 8: "八白", 9: "九紫"}
GUA_DIR = {"乾": "西北", "坎": "北", "艮": "东北", "震": "东",
           "巽": "东南", "离": "南", "坤": "西南", "兑": "西"}
GRID_LAYOUT = [["巽", "离", "坤"], ["震", "中", "兑"], ["艮", "坎", "乾"]]
VERDICTS = ("适合", "有条件适合", "须谨慎")
PLACEHOLDERS = ("TODO", "占位", "待补充", "xxx", "XXX", "…略", "略。")


def validate(data):
    """返回 (errs, warns)：errs 阻断，warns 仅提示。"""
    errs = []
    warns = []
    res = data.get("result")
    if not isinstance(res, dict):
        return ["缺少 result（fengshui.py 的 JSON 输出）"], warns
    if res.get("error"):
        errs.append(f"result.error 存在（排盘失败：{res['error']}），请先解决排盘错误再生成报告")
    for key in ("yun", "sitting", "feixing", "zhai", "persons", "rooms", "annual"):
        if key not in res:
            errs.append(f"result 缺少字段: {key}")
    con = data.get("conclusion")
    if not isinstance(con, dict):
        errs.append("缺少 conclusion")
        con = {}
    summary = (con.get("summary") or "").strip()
    if len(summary) < 30:
        errs.append(f"conclusion.summary 至少 30 字（现 {len(summary)} 字）")
    if con.get("verdict") not in VERDICTS:
        errs.append(f"conclusion.verdict 必须是 {'/'.join(VERDICTS)}")
    for ph in PLACEHOLDERS:
        if ph in summary:
            errs.append(f"conclusion.summary 含占位文本: {ph}")
    for i, s in enumerate(data.get("sections") or []):
        if not s.get("title"):
            errs.append(f"sections[{i}] 缺 title")
        htm = (s.get("html") or "").strip()
        if len(htm) < 20:
            errs.append(f"sections[{i}] 内容过短")
        low = htm.lower()
        if "<script" in low or "onerror" in low or "javascript:" in low:
            warns.append(f"sections[{i}] 含脚本/事件代码，将原样嵌入 HTML，请确认内容可信")
    if res.get("annual", {}).get("error") if isinstance(res.get("annual"), dict) else False:
        warns.append(f"流年数据异常：{res['annual']['error']}")
    for p in res.get("persons") or []:
        if isinstance(p, dict) and p.get("warning"):
            warns.append(f"命主 {p.get('name','')}: {p['warning']}")
    if res.get("persons") is not None and not res["persons"]:
        errs.append("persons 为空：至少需要一位命主")
    return errs, warns


def esc(s):
    return html.escape(str(s))


def chart_html(charts, zuo_palace, xiang_palace):
    rows = []
    for row in GRID_LAYOUT:
        cells = []
        for p in row:
            if p == "中":
                cells.append('<div class="cell center-cell"><div class="star">中五</div>'
                             '<div class="pname">中宫</div></div>')
                continue
            mark = ""
            if p == zuo_palace:
                mark = '<span class="mark mark-zuo">坐</span>'
            elif p == xiang_palace:
                mark = '<span class="mark mark-xiang">向</span>'
            s, x, y = charts["shan"][p], charts["xiang"][p], charts["yun"][p]
            star_names = f'{s} {x} <span class="yunstar">/ {y}</span>'
            tip = f'{STAR_NUM_NAME[s]}·{STAR_NUM_NAME[x]}·{STAR_NUM_NAME[y]}'
            cells.append(
                f'<div class="cell"><div class="star">{star_names}</div>'
                f'<div class="pname">{p}·{GUA_DIR[p]} {mark}<br><span class="tip">{tip}</span></div></div>')
        rows.append('<div class="grid-row">' + "".join(cells) + "</div>")
    return '<div class="grid">' + "".join(rows) + "</div>"


def dayou_table(layout):
    trs = []
    for star, info in layout.items():
        cls = "ji" if "吉" in info["吉凶"] else "xiong"
        trs.append(f'<tr class="{cls}"><td>{esc(star)}</td><td>{esc(info["星"])}</td>'
                   f'<td>{esc(info["卦"])}宫</td><td>{esc(info["方位"])}</td>'
                   f'<td>{esc(info["吉凶"])}</td></tr>')
    return ('<table class="tbl"><tr><th>八星</th><th>北斗</th><th>卦宫</th>'
            '<th>方位</th><th>吉凶</th></tr>' + "".join(trs) + "</table>")


def rooms_table(rooms):
    trs = []
    for r in rooms:
        if not isinstance(r, dict):
            trs.append(f'<tr><td>{esc(str(r)[:24])}</td><td colspan="4">⚠ 条目格式错误</td></tr>')
            continue
        rname = esc(r.get("name", "?"))
        if "error" in r:
            trs.append(f'<tr><td>{rname}</td><td colspan="4">⚠ {esc(r["error"])}</td></tr>')
            continue
        if r.get("宫") == "中":
            trs.append(f'<tr><td>{rname}</td><td colspan="4">中宫（火烧心/中央受污高危位）</td></tr>')
            continue
        if not r.get("宫"):
            trs.append(f'<tr><td>{rname}</td><td colspan="4">⚠ 宫位数据缺失</td></tr>')
            continue
        bazhai = esc(r.get("八宅星(宅卦)") or "—")
        per = "；".join(f"{esc(k)}命:{esc(v)}" for k, v in (r.get("八宅星(各命主)") or {}).items())
        xk = r.get("玄空") or {}
        trs.append(f'<tr><td>{rname}</td><td>{esc(r["宫"])}宫（{esc(r.get("方位",""))}）</td>'
                   f'<td>{bazhai}<br><span class="tip">{per}</span></td>'
                   f'<td>山{xk.get("山星","—")} 向{xk.get("向星","—")} 运{xk.get("运星","—")}</td>'
                   f'<td>{STAR_NUM_NAME.get(xk.get("山星"), "")}·{STAR_NUM_NAME.get(xk.get("向星"), "")}</td></tr>')
    return ('<table class="tbl"><tr><th>房间</th><th>宫位</th><th>八宅星</th>'
            '<th>玄空星</th><th>组合</th></tr>' + "".join(trs) + "</table>")


def render(data):
    res = data["result"]
    con = data.get("conclusion", {})
    title = (data.get("meta") or {}).get("title") or "阳宅风水分析报告"
    yun = res["yun"]
    st = res["sitting"]
    fx = res["feixing"]
    zhai = res["zhai"]
    an = res["annual"]
    charts = fx["charts"]

    per_html = ""
    for p in res["persons"]:
        if not isinstance(p, dict):
            per_html += f'<div class="card">⚠ 命主条目格式错误：{esc(str(p)[:40])}</div>'
            continue
        if "error" in p:
            per_html += (f'<div class="card">⚠ 命主 {esc(p.get("name",""))} 资料有误：'
                         f'{esc(p["error"])}（请补充完整的出生日期与性别）</div>')
            continue
        warn_p = f'<p class="tip" style="color:#c0392b">⚠ {esc(p["warning"])}</p>' if p.get("warning") else ""
        match = "相配" if (p["class"] == "东四命") == (zhai["东西四宅"] == "东四宅") else "不相配"
        icon = "✅" if match == "相配" else "⚠️"
        per_html += f'''
        <div class="card">
          <h3>{esc(p.get("name","命主"))}：{esc(p["ming_gua"])}命（{esc(p["class"])}）</h3>
          <p class="tip">{esc(p["birth"])} {esc(p["gender"])}性 · {esc(p.get("boundary_note",""))}
          {' · ' + esc(p["special"]) if p.get("special") else ''}</p>
          {warn_p}
          <p>宅命相配：{icon} {esc(p["class"])} 住 {esc(zhai["东西四宅"])} → <b>{esc(match)}</b></p>
          {dayou_table(p["dayou"])}
        </div>'''

    flags = "".join(f'<li>{esc(f)}</li>' for f in fx.get("特殊") or []) or "<li>无特殊格局</li>"
    cm = fx.get("城门") or []
    cm_text = "；".join(f'{esc(c["宫"])}宫（运{c["运星"]} 山{c["山星"]} 向{c["向星"]}）' for c in cm)

    # 预计算所有复杂表达式（避免 f-string 嵌套问题）
    if st.get("度数偏差") is not None:
        deg_note = f'，实测偏差 {st["度数偏差"]:+.1f}°，{esc(st["排盘方式"])}'
    else:
        deg_note = ""
    sxtwl_note = 'sxtwl 历法引擎' if res.get("meta", {}).get("sxtwl") else '纯 Python 近似历法'
    ws_pals = "、".join(fx["格局细节"]["旺山星所在"]) or "—"
    wx_pals = "、".join(fx["格局细节"]["旺向星所在"]) or "—"
    notes_list = "".join(f"<li>{esc(n)}</li>" for n in fx.get("notes") or [])
    wuhuang_pals = "、".join(an["五黄到"]) or "中宫"
    erhei_pals = "、".join(an["二黑到"]) or "中宫"
    taishui = an["太岁"]
    suipo = an["岁破"]
    warn_cards = "".join(f'<div class="card">⚠ {esc(w)}</div>' for w in st.get("warnings") or [])
    ss = fx.get("收山出煞")
    ss_line = ""
    if ss:
        ss_line = (f'<p><b>收山出煞</b>（中州派）：向首{esc(ss["向首"]["山"])}属{esc(ss["向首"]["诀"])}——'
                   f'{esc(ss["向首"]["宜"])}；坐山{esc(ss["坐山"]["山"])}属{esc(ss["坐山"]["诀"])}</p>')
    pl = res.get("pailong")
    pl_section = ""
    if isinstance(pl, dict) and "error" in pl:
        pl_section = f'<div class="card">⚠ 排龙：{esc(pl["error"])}</div>'
    elif isinstance(pl, dict):
        stars_text = "　".join(f'{esc(g)}宫{esc(s)}' for g, s in pl["十二宫"].items())
        pl_section = f'''<h2>排龙诀（中州派）</h2>
<div class="card">
<p>水口方{esc(pl["水口方山"])} → 来龙{esc(pl["来龙"])}（{esc(pl["行向"])}）；
宅向首{esc(pl["向首宫"])}宫得<b>{esc(pl["龙星"])}龙</b>（{esc(pl["吉凶"])}，五行{esc(pl["龙五行"])}）</p>
<p>{esc(pl["说明"])}</p>
<p class="tip">{stars_text}</p>
<p class="tip">五吉龙：贪狼/巨门/武曲/左辅/右弼，七凶龙：破军/廉贞/文曲/禄存；吉龙宫内二山可作向首选向，仍须配后天星盘与形峦；排龙出卦（如丙巳兼线）此宅不可用。</p>
</div>'''

    room_notes = con.get("room_notes") or []
    rn_html = ""
    if room_notes:
        rows = "".join(
            f'<tr><td>{esc(n["name"])}</td><td>{esc(n.get("verdict",""))}</td><td>{esc(n.get("text",""))}</td></tr>'
            for n in room_notes)
        rn_html = ('<h2>房间逐评</h2><table class="tbl">'
                   '<tr><th>房间</th><th>判定</th><th>说明</th></tr>' + rows + "</table>")

    sugg = con.get("suggestions") or []
    sugg_html = ""
    if sugg:
        sugg_html = "<h2>调整建议（按成本从低到高）</h2><ol>" + "".join(
            f"<li>{esc(s)}</li>" for s in sugg) + "</ol>"

    # 外部环境回显 + 流年段（可能异常）
    ext = res.get("external") or []
    ext_html = ""
    if ext:
        ext_html = ('<h3>外部环境（供形煞评估）</h3><ul>'
                    + "".join(f'<li>{esc(e)}</li>' for e in ext) + '</ul>')
    if isinstance(an, dict) and "error" in an:
        annual_section = f'<div class="card">⚠ 流年数据异常：{esc(an["error"])}</div>'
    else:
        annual_section = f'''<h2>流年飞星（{esc(str(an["year"]))} {esc(an["gz"])}年）</h2>
<div class="card">
<p><b>{esc(STAR_NUM_NAME[an["star"]])}入中</b> · 太岁{esc(taishui["支"])}（{esc(taishui["方位"])}）·
   岁破{esc(suipo["支"])}（{esc(suipo["方位"])}）·
   三煞在{esc(an["三煞"]["方位"])}（{'、'.join(an["三煞"]["宫"])}）</p>
<p><b>五黄到</b>：{wuhuang_pals}　<b>二黑到</b>：{erhei_pals}（宜静不宜动）</p>
</div>'''

    secs_html = ""
    for s in data.get("sections") or []:
        secs_html += f'<h2>{esc(s["title"])}</h2>' + s["html"]

    return f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>{esc(title)}</title>
<style>
 body{{font-family:"Microsoft YaHei","PingFang SC",sans-serif;max-width:960px;margin:24px auto;padding:0 16px;color:#2b2b2b;line-height:1.7;background:#faf8f4}}
 h1{{border-bottom:3px solid #8b5a2b;padding-bottom:8px}} h2{{color:#6b3f14;border-left:5px solid #8b5a2b;padding-left:10px;margin-top:36px}}
 .card{{background:#fff;border:1px solid #e2d8c8;border-radius:10px;padding:16px 20px;margin:14px 0;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
 .grid{{display:table;table-layout:fixed;width:100%;max-width:560px;border:2px solid #8b5a2b;background:#fff}}
 .grid-row{{display:table-row}} .cell{{display:table-cell;border:1px solid #d9c8ae;text-align:center;padding:8px 4px;vertical-align:middle}}
 .center-cell{{background:#f3ece0}}
 .star{{font-size:1.5rem;font-weight:700}} .yunstar{{font-size:.85rem;color:#777;font-weight:400}}
 .pname{{font-size:.9rem;color:#6b3f14}} .tip{{font-size:.8rem;color:#888}}
 .mark{{font-size:.75rem;padding:1px 5px;border-radius:4px;color:#fff;margin-left:3px}}
 .mark-zuo{{background:#3a7bd5}} .mark-xiang{{background:#c0392b}}
 table.tbl{{border-collapse:collapse;width:100%;background:#fff;font-size:.92rem}}
 .tbl th{{background:#8b5a2b;color:#fff;padding:6px}} .tbl td{{border:1px solid #e2d8c8;padding:6px 8px;text-align:center}}
 .tbl tr.ji td{{background:#f2f8ee}} .tbl tr.xiong td{{background:#fdeeee}}
 .verdict{{font-size:1.3rem;font-weight:700;color:#8b5a2b}}
 .disclaimer{{margin-top:40px;font-size:.85rem;color:#999;border-top:1px dashed #ccc;padding-top:12px}}
 .kv{{background:#fff;border:1px solid #e2d8c8;border-radius:10px;padding:12px 20px}}
 .kv b{{color:#6b3f14}}
</style></head><body>
<h1>{esc(title)}</h1>
<div class="kv">
 <b>宅运</b>：{esc(str(yun.get("name") or f"{yun.get('period')}运"))}（建成 {esc(str(yun.get("built_year")))}）&nbsp;&nbsp;
 <b>坐向</b>：坐{esc(st["坐山"])}（{esc(st["坐山三元龙"])}·{esc(st["坐山阴阳"])}）朝{esc(st["向山"])}{deg_note}<br>
 <b>宅卦</b>：{esc(zhai["宅卦"])}宅（{esc(zhai["东西四宅"])}）&nbsp;&nbsp;
 <b>格局</b>：<span class="verdict">{esc(fx["格局"])}</span>
</div>
{warn_cards}

<h2>玄空飞星盘（上南下北）</h2>
<div class="card">
{chart_html(charts, st["坐山宫"], st["向首宫"])}
<p class="tip">每宫上方：左为山星（管人丁健康），右为向星（管财禄）；下方小字为运星。每宫下行为宫位方位。</p>
<p><b>旺山星({esc(str(yun["period"]))}白)在</b>：{ws_pals}；
   <b>旺向星在</b>：{wx_pals}</p>
<p><b>排盘说明</b>：</p><ul>{notes_list}</ul>
<p><b>特殊格局</b>：{flags}</p>
{ss_line}
<p><b>城门宫</b>：{esc(cm_text) or '—'}</p>
</div>

<h2>命卦与宅命相配</h2>
{per_html}

<h2>房间布局核查</h2>
<div class="card">
<h3>宅卦 {esc(zhai["宅卦"])}（{esc(zhai["东西四宅"])}）大游年</h3>
{dayou_table(zhai["宅卦大游年"])}
<h3>逐房间落宫</h3>
{rooms_table(res["rooms"])}
{ext_html}
</div>
{rn_html}

{pl_section}

{annual_section}

{secs_html}
{sugg_html}

<h2>综合结论：<span class="verdict">{esc(con.get("verdict",""))}</span></h2>
<div class="card">{esc(con.get("summary",""))}</div>

<div class="disclaimer">
本报告由 yangzhai-fengshui 排盘引擎生成（{esc(sxtwl_note)}）。
风水学属中国传统民俗文化，流派众多、结论各异，本报告仅供参考娱乐与文化研究，
不构成任何置业、装修、医疗或其他人生决策依据。
</div>
</body></html>'''


def main():
    ap = argparse.ArgumentParser(description="风水分析 HTML 报告生成器")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", default="风水报告.html")
    ap.add_argument("--validate", action="store_true", help="仅校验输入")
    args = ap.parse_args()

    try:
        with open(args.input, encoding="utf-8-sig") as f:
            data = json.load(f)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        print(f"❌ 无法读取输入文件：{e}")
        sys.exit(1)

    try:
        errs, warns = validate(data)
    except Exception as e:
        print(f"❌ 输入结构异常，无法校验：{type(e).__name__}: {e}")
        sys.exit(1)
    if args.validate:
        if errs:
            print("❌ 校验失败：")
            for e in errs:
                print(f"  - {e}")
            sys.exit(1)
        for w in warns:
            print(f"  ⚠ {w}")
        print("✅ 输入校验通过")
        return
    if errs:
        print("❌ 校验有误，拒绝生成（请先修正后再运行）：")
        for e in errs:
            print(f"  - {e}")
        sys.exit(1)
    for w in warns:
        print(f"  ⚠ {w}")

    try:
        html_text = render(data)
    except Exception as e:
        print(f"❌ 报告渲染失败：{type(e).__name__}: {e}")
        print("  请检查 data.json 的 result 结构是否完整（可先跑 --validate）")
        sys.exit(1)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html_text)
    print(f"✅ 报告已生成：{args.output}")


if __name__ == "__main__":
    main()
