#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阳宅风水排盘引擎（yangzhai-fengshui skill）

子命令：
  mingua   命卦计算（八宅，立春分界，sxtwl 可选）
  feixing  玄空飞星排盘（运盘/山盘/向盘，下卦与替卦，格局判定）
  dayou    大游年八星方位表（八宅）
  annual   流年紫白盘 + 太岁/岁破/三煞
  all      一键完整分析（读 house.json）
  selftest 内置测试向量自检

数据依据（见 references/）：
  - 大游年歌诀：《八宅明镜》八句，环序映射，28 对关系对称校验
  - 命卦公式：统一式 男=(1991-年)%9 女=(6-男数)%9，5 男寄坤/女寄艮
    （1900s: 男(100-YY)%9 女(YY+5)%9；2000s: 男(99-YY)%9 女(YY+6)%9 的等价统一）
  - 玄空排盘：运盘顺飞；山/向盘以坐向宫运星入中，按入中星本宫与坐向同元龙
    之山的阴阳定顺逆（阳顺阴逆）；五黄入中随坐向本山阴阳
  - 替卦（沈氏起星诀）：子癸甲申→1 壬卯乙未坤→2 乾亥辰巽巳戌→6
    酉辛丑艮丙→7 寅午庚丁→9；替数只有 1、2、6、7、9；
    顺逆按替前原查之山的阴阳（中州派口诀"阳顺阴逆隔一位"与无常派实例一致）
  - 流年紫白：A(y)=(2027-y)%9（0作9），立春换年

纯 Python 运行；安装 sxtwl 后命卦分界与干支为精确值。
"""
import sys
import os
import json
import argparse

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    import sxtwl
    HAS_SXTWL = True
except ImportError:
    sxtwl = None
    HAS_SXTWL = False

# ═══════════════════════════════════════════════════════════════
#  基础常量
# ═══════════════════════════════════════════════════════════════

TIANGAN = "甲乙丙丁戊己庚辛壬癸"
DIZHI = "子丑寅卯辰巳午未申酉戌亥"

# 洛书数 → 宫
LUOSHU_PALACE = {1: "坎", 2: "坤", 3: "震", 4: "巽", 5: "中", 6: "乾", 7: "兑", 8: "艮", 9: "离"}
PALACE_LUOSHU = {"坎": 1, "坤": 2, "震": 3, "巽": 4, "乾": 6, "兑": 7, "艮": 8, "离": 9}

# 飞泊路径：中宫起，乾→兑→艮→离→坎→坤→震→巽
FLY_PATH = ["中", "乾", "兑", "艮", "离", "坎", "坤", "震", "巽"]

# 图面九宫布局（上南下北）：行1 巽离坤，行2 震中兑，行3 艮坎乾
GRID_LAYOUT = [["巽", "离", "坤"], ["震", "中", "兑"], ["艮", "坎", "乾"]]

GUA_DIR = {"乾": "西北", "坎": "北", "艮": "东北", "震": "东",
           "巽": "东南", "离": "南", "坤": "西南", "兑": "西"}

# 后天八卦环序（顺时针，自乾起）
RING = ["乾", "坎", "艮", "震", "巽", "离", "坤", "兑"]

# 二十四山（顺时针，自子起；每山 15°，中心角 = 序号*15）
MOUNTAIN_ORDER = ["子", "癸", "丑", "艮", "寅", "甲", "卯", "乙",
                  "辰", "巽", "巳", "丙", "午", "丁", "未", "坤",
                  "申", "庚", "酉", "辛", "戌", "乾", "亥", "壬"]

# 每宫三山，顺时针依次为地元龙、天元龙、人元龙
PALACE_TRIPLETS = {
    "坎": ["壬", "子", "癸"], "艮": ["丑", "艮", "寅"], "震": ["甲", "卯", "乙"],
    "巽": ["辰", "巽", "巳"], "离": ["丙", "午", "丁"], "坤": ["未", "坤", "申"],
    "兑": ["庚", "酉", "辛"], "乾": ["戌", "乾", "亥"],
}
YUAN_NAMES = ["地元龙", "天元龙", "人元龙"]

YANG_SET = set("甲庚壬丙乾坤艮巽寅申巳亥")
YIN_SET = set("辰戌丑未子午卯酉乙辛丁癸")

# 沈氏玄空替星诀（兼向超 3° 用；替数只有 1/2/6/7/9）
TI_XING_JUE = {
    "子": 1, "癸": 1, "甲": 1, "申": 1,
    "壬": 2, "卯": 2, "乙": 2, "未": 2, "坤": 2,
    "乾": 6, "亥": 6, "辰": 6, "巽": 6, "巳": 6, "戌": 6,
    "酉": 7, "辛": 7, "丑": 7, "艮": 7, "丙": 7,
    "寅": 9, "午": 9, "庚": 9, "丁": 9,
}

# 三元九运（下元甲子 1984 起为七运；每运 20 年）
YUN_TABLE = [
    (1, 1864, 1883, "上元一运（坎）"), (2, 1884, 1903, "上元二运（坤）"),
    (3, 1904, 1923, "上元三运（震）"), (4, 1924, 1943, "中元四运（巽）"),
    (5, 1944, 1963, "中元五运"), (6, 1964, 1983, "中元六运（乾）"),
    (7, 1984, 2003, "下元七运（兑）"), (8, 2004, 2023, "下元八运（艮）"),
    (9, 2024, 2043, "下元九运（离）"),
]

# 大游年歌诀（八宅明镜）：每句首字为本卦（伏位），后 7 字按后天八卦环序
# 排到本卦之后的七卦（环序：乾坎艮震巽离坤兑循环）
DA_YOU_NIAN_SONG = {
    "乾": "六天五祸绝延生", "坎": "五天生延绝祸六",
    "艮": "六绝祸生延天五", "震": "延生祸绝五天六",
    "巽": "天五六祸生绝延", "离": "六五绝延祸生天",
    "坤": "天延绝生祸五六", "兑": "生祸延绝六五天",
}
SONG_CHAR_TO_STAR = {"生": "生气", "天": "天医", "延": "延年", "伏": "伏位",
                     "绝": "绝命", "五": "五鬼", "六": "六煞", "祸": "祸害"}
STAR_JI_XIONG = {"生气": "大吉", "延年": "吉", "天医": "吉", "伏位": "小吉",
                 "绝命": "大凶", "五鬼": "大凶", "祸害": "凶", "六煞": "凶"}
STAR_BEIDOU = {"生气": "贪狼木", "延年": "武曲金", "天医": "巨门土", "伏位": "辅弼木",
               "绝命": "破军金", "五鬼": "廉贞火", "祸害": "禄存土", "六煞": "文曲水"}
DONG_SI = ["坎", "离", "震", "巽"]
XI_SI = ["乾", "坤", "艮", "兑"]

# 流年三煞：申子辰煞在南（巳午未），寅午戌煞在北（亥子丑），
#           巳酉丑煞在东（寅卯辰），亥卯未煞在西（申酉戌）
SAN_SHA = {
    "申": ("南", ["巳", "午", "未"]), "子": ("南", ["巳", "午", "未"]),
    "辰": ("南", ["巳", "午", "未"]),
    "寅": ("北", ["亥", "子", "丑"]), "午": ("北", ["亥", "子", "丑"]),
    "戌": ("北", ["亥", "子", "丑"]),
    "巳": ("东", ["寅", "卯", "辰"]), "酉": ("东", ["寅", "卯", "辰"]),
    "丑": ("东", ["寅", "卯", "辰"]),
    "亥": ("西", ["申", "酉", "戌"]), "卯": ("西", ["申", "酉", "戌"]),
    "未": ("西", ["申", "酉", "戌"]),
}
ZHI_DIR = {"子": "北", "午": "南", "卯": "东", "酉": "西",
           "艮": "东北", "巽": "东南", "坤": "西南", "乾": "西北",
           "寅": "东北", "巳": "东南", "申": "西南", "亥": "西北",
           "辰": "东南偏东", "戌": "西北偏西", "丑": "东北偏北", "未": "西南偏南"}

# 地支 → 后天八卦宫（用于三煞/太岁/岁破落宫）
DIZHI_PALACE = {"子": "坎", "丑": "艮", "寅": "艮", "卯": "震", "辰": "巽", "巳": "巽",
                "午": "离", "未": "坤", "申": "坤", "酉": "兑", "戌": "乾", "亥": "乾"}


# ═══════════════════════════════════════════════════════════════
#  二十四山 / 坐向
# ═══════════════════════════════════════════════════════════════

def norm_deg(deg):
    return deg % 360.0


def mountain_from_deg(deg):
    """度数 → (山名, 中心角, 偏离角)。偏离角带符号：正值=顺时针偏。"""
    deg = norm_deg(deg)
    idx = int(((deg + 7.5) % 360) // 15)
    center = idx * 15.0
    dev = ((deg - center + 180.0) % 360.0) - 180.0
    return MOUNTAIN_ORDER[idx], center, dev


def mountain_index(m):
    return MOUNTAIN_ORDER.index(m)


def mountain_palace(m):
    for p, tri in PALACE_TRIPLETS.items():
        if m in tri:
            return p
    raise ValueError(m)


def mountain_yuan_idx(m):
    return PALACE_TRIPLETS[mountain_palace(m)].index(m)


def mountain_yuan(m):
    return YUAN_NAMES[mountain_yuan_idx(m)]


def mountain_yinyang(m):
    return "阳" if m in YANG_SET else "阴"


def mountain_deg_range(m):
    i = mountain_index(m)
    lo = (i * 15 - 7.5) % 360
    hi = (i * 15 + 7.5) % 360
    return lo, hi


def parse_sitting(spec):
    """坐向描述 → (坐山, 向山)。
    支持：'子山午向'、'坐子向午'、'坐子'、'子'（坐子即向午）、度数（坐山中心向度数，如 350）。
    坐向两山必须对宫相望，否则报错。"""
    import re
    s = spec.strip().replace("°", "").replace("度", "")
    ms = "".join(MOUNTAIN_ORDER)
    m = (re.match(rf"^(?:坐)?([{ms}])山(?:向|朝)?([{ms}])(?:向|朝)?$", s)
         or re.match(rf"^(?:坐)?([{ms}])(?:向|朝)([{ms}])$", s))
    if m:
        zuo, xiang = m.group(1), m.group(2)
        if opposite_mountain(zuo) != xiang:
            raise ValueError(f"坐向不对望：坐{zuo}应向{opposite_mountain(zuo)}，而非向{xiang}（{spec}）")
        return zuo, xiang
    if s.startswith("坐") and s[1:] in MOUNTAIN_ORDER:
        zuo = s[1:]
        return zuo, opposite_mountain(zuo)
    if s in MOUNTAIN_ORDER:
        return s, opposite_mountain(s)
    try:
        deg = float(s)
        mnt, _, _ = mountain_from_deg(deg)
        return mnt, opposite_mountain(mnt)
    except ValueError:
        raise ValueError(f"无法解析坐向: {spec}")


def opposite_mountain(m):
    """对宫之山（坐↔向，同一宫内地元对地元…）。"""
    idx = mountain_index(m)
    return MOUNTAIN_ORDER[(idx + 12) % 24]


# ═══════════════════════════════════════════════════════════════
#  飞星核心
# ═══════════════════════════════════════════════════════════════

def fly(center, forward=True):
    """center 星入中，按洛书轨迹飞泊。返回 {宫名: 星数}，含中宫。"""
    d = 1 if forward else -1
    return {p: ((center - 1 + d * k) % 9) + 1 for k, p in enumerate(FLY_PATH)}


def star_yinyang(star, yuan_idx):
    """入中星（非5）在元旦盘本宫中、与坐向同元龙之山的阴阳。"""
    palace = LUOSHU_PALACE[star]
    m = PALACE_TRIPLETS[palace][yuan_idx]
    return mountain_yinyang(m)


def paipan_xiagua(period, zuo, xiang):
    """下卦排盘。返回 dict: yun/shan/xiang（宫→星），及入中顺逆记录。"""
    yun = fly(period, True)
    zi = mountain_yuan_idx(zuo)
    xi = mountain_yuan_idx(xiang)

    ms = yun[mountain_palace(zuo)]
    if ms == 5:
        fwd = mountain_yinyang(zuo) == "阳"
        note = f"山盘五黄入中，随坐山{zuo}({mountain_yinyang(zuo)})定顺逆"
    else:
        fwd = star_yinyang(ms, zi) == "阳"
        note = f"山盘{ms}入中，以{LUOSHU_PALACE[ms]}宫{YUAN_NAMES[zi]}({star_yinyang(ms, zi)})定顺逆"
    shan = fly(ms, fwd)

    fs = yun[mountain_palace(xiang)]
    if fs == 5:
        fwd2 = mountain_yinyang(xiang) == "阳"
        note2 = f"向盘五黄入中，随向首{xiang}({mountain_yinyang(xiang)})定顺逆"
    else:
        fwd2 = star_yinyang(fs, xi) == "阳"
        note2 = f"向盘{fs}入中，以{LUOSHU_PALACE[fs]}宫{YUAN_NAMES[xi]}({star_yinyang(fs, xi)})定顺逆"
    xiangpan = fly(fs, fwd2)

    return {"yun": yun, "shan": shan, "xiang": xiangpan,
            "notes": [note, note2],
            "zhong_shan": ms, "zhong_xiang": fs,
            "shan_forward": fwd, "xiang_forward": fwd2}


def paipan_tigua(period, zuo, xiang):
    """替卦排盘（沈氏起星诀；顺逆法则经中州派口诀与无常派实例双重验证）。
    入中星为运盘坐/向宫星数 n；以 n 本宫中与坐向同元龙之山 m 查替星诀得替数 t；
    t 入中飞泊，顺逆按**原查之山 m 的阴阳**（不可以用替换后的星定顺逆）。
    n=5（五黄入中）不替，随坐向本山阴阳。"""
    yun = fly(period, True)
    zi = mountain_yuan_idx(zuo)
    xi = mountain_yuan_idx(xiang)

    def ti_entry(n, yuan_idx, own_mountain, label):
        if n == 5:
            fwd = mountain_yinyang(own_mountain) == "阳"
            return 5, fwd, f"{label}五黄入中不替，随{own_mountain}({mountain_yinyang(own_mountain)})定顺逆"
        palace = LUOSHU_PALACE[n]
        m = PALACE_TRIPLETS[palace][yuan_idx]
        t = TI_XING_JUE[m]
        fwd = mountain_yinyang(m) == "阳"
        if t == n:
            note = (f"{label}{n}入中，取{palace}宫{YUAN_NAMES[yuan_idx]}{m}，"
                    f"替数与本数相同不替；按{m}({mountain_yinyang(m)}){'顺' if fwd else '逆'}飞")
        else:
            note = (f"{label}{n}入中，取{palace}宫{YUAN_NAMES[yuan_idx]}{m}，"
                    f"替为{t}入中；按{m}({mountain_yinyang(m)}){'顺' if fwd else '逆'}飞")
        return t, fwd, note

    ms = yun[mountain_palace(zuo)]
    t_shan, fwd_s, note_s = ti_entry(ms, zi, zuo, "山盘")
    shan = fly(t_shan, fwd_s)
    fs = yun[mountain_palace(xiang)]
    t_xiang, fwd_x, note_x = ti_entry(fs, xi, xiang, "向盘")
    xiangpan = fly(t_xiang, fwd_x)

    return {"yun": yun, "shan": shan, "xiang": xiangpan,
            "notes": [note_s, note_x],
            "zhong_shan": t_shan, "zhong_xiang": t_xiang,
            "shan_forward": fwd_s, "xiang_forward": fwd_x}


def judge_geju(period, charts, zuo, xiang):
    """格局判定：旺山旺向 / 上山下水 / 双星会坐 / 双星会向。"""
    sp, fp = mountain_palace(zuo), mountain_palace(xiang)
    ms_at_zuo = charts["shan"][sp]
    fs_at_zuo = charts["xiang"][sp]
    ms_at_xiang = charts["shan"][fp]
    fs_at_xiang = charts["xiang"][fp]
    if ms_at_zuo == period and fs_at_xiang == period:
        geju = "旺山旺向"
    elif ms_at_xiang == period and fs_at_zuo == period:
        geju = "上山下水"
    elif ms_at_xiang == period and fs_at_xiang == period:
        geju = "双星会向"
    elif ms_at_zuo == period and fs_at_zuo == period:
        geju = "双星会坐"
    else:
        geju = "（四种基本格局皆不符合）"
    detail = {
        "旺山星所在": [p for p in FLY_PATH if p != "中" and charts["shan"][p] == period],
        "旺向星所在": [p for p in FLY_PATH if p != "中" and charts["xiang"][p] == period],
        "坐山宫": {"山星": ms_at_zuo, "向星": fs_at_zuo, "运星": charts["yun"][sp]},
        "向首宫": {"山星": ms_at_xiang, "向星": fs_at_xiang, "运星": charts["yun"][fp]},
    }
    return geju, detail


def special_flags(charts, period):
    """伏吟/反吟/合十/三般卦检测。"""
    flags = []
    # 伏吟：盘与元旦盘全同（须五黄入中顺飞）；反吟：每宫与元旦盘合十（五黄入中逆飞）
    yuandan = {p: PALACE_LUOSHU[p] for p in FLY_PATH if p != "中"}
    yuandan["中"] = 5
    for name in ("shan", "xiang"):
        pan = charts[name]
        if all(pan[p] == yuandan[p] for p in FLY_PATH):
            flags.append(f"{'山盘' if name == 'shan' else '向盘'}与元旦盘相同：伏吟（五黄入中顺飞）")
        elif all(pan[p] == 10 - yuandan[p] for p in FLY_PATH):
            flags.append(f"{'山盘' if name == 'shan' else '向盘'}与元旦盘合十相对：反吟（五黄入中逆飞）")
    # 合十：山盘/向盘 与 运盘 每宫相加为 10（中宫 5+5 自洽）
    for name in ("shan", "xiang"):
        if all(charts[name][p] + charts["yun"][p] == 10 for p in FLY_PATH):
            flags.append(f"{'山盘' if name == 'shan' else '向盘'}与运盘合十")
    if all(charts["shan"][p] + charts["xiang"][p] == 10 for p in FLY_PATH):
        flags.append("山盘与向盘合十")
    # 三般卦：每宫山、向、运三星同属一组父母三般卦（147/258/369）
    def group(n):
        return {1, 4, 7} if n in (1, 4, 7) else ({2, 5, 8} if n in (2, 5, 8) else {3, 6, 9})
    palaces8 = [p for p in FLY_PATH if p != "中"]
    if all(group(charts["shan"][p]) == group(charts["xiang"][p]) == group(charts["yun"][p])
           for p in palaces8):
        flags.append("全局父母三般卦")
    # 连茹卦：山、向、运三星逐宫连续递进（提示性检测）
    if all({charts["shan"][p], charts["xiang"][p], charts["yun"][p]} in
           ({1, 2, 3}, {2, 3, 4}, {3, 4, 5}, {4, 5, 6}, {5, 6, 7}, {6, 7, 8}, {7, 8, 9}, {8, 9, 1}, {9, 1, 2})
           for p in palaces8):
        flags.append("全盘连茹卦（提示）")
    return flags


def qixing_dajie(charts, period, xiang):
    """七星打劫检测（通行定义，经七运午山子向/八运子山午向实例核对）：
    向首得当运旺向星，且向星盘上 离+震+乾（真打劫）或 坎+巽+兑（假打劫）
    三宫向星构成同一父母三般卦组（147/258/369）。"""
    def group(n):
        return {1, 4, 7} if n in (1, 4, 7) else ({2, 5, 8} if n in (2, 5, 8) else {3, 6, 9})
    fp = mountain_palace(xiang)
    if charts["xiang"][fp] != period:
        return None
    xing = charts["xiang"]
    for name, pals, need_fp in (("真打劫", ["离", "震", "乾"], "离"),
                                ("假打劫", ["坎", "巽", "兑"], "坎")):
        if fp != need_fp:
            continue
        gs = {frozenset(group(xing[p])) for p in pals}
        if len(gs) == 1 and len(set(xing[p] for p in pals)) == 3:
            return f"七星打劫（{name}）：向星盘 {'、'.join(pals)} 三宫成三般卦，向首得旺星"
    return None


def chengmen(charts, period, xiang):
    """城门：向首左右两宫。列出其运盘星与山向星（合诀与否详见参考文档）。"""
    fp = mountain_palace(xiang)
    ri = RING.index(fp)
    left, right = RING[(ri - 1) % 8], RING[(ri + 1) % 8]
    out = []
    for p in (left, right):
        out.append({"宫": p, "运星": charts["yun"][p],
                    "山星": charts["shan"][p], "向星": charts["xiang"][p]})
    return out


# ═══════════════════════════════════════════════════════════════
#  命卦（八宅）
# ═══════════════════════════════════════════════════════════════

GUA_NUMBER = {1: "坎", 2: "坤", 3: "震", 4: "巽", 6: "乾", 7: "兑", 8: "艮", 9: "离"}


def year_gz_via_sxtwl(year, month, day, lichun_boundary=True):
    """sxtwl 取年干支（立春分界）。返回 (干支, 干支年公历年号) 或 (干支, None)。
    干支→公历年号按 ±180 年循环定位（支持 1804 年以来各世纪）。"""
    if not HAS_SXTWL:
        return None
    day_obj = sxtwl.fromSolar(year, month, day)
    ygz = day_obj.getYearGZ(False)  # False = 以立春为界（True 是正月初一分界）
    tg, dz = ygz.tg, ygz.dz
    idx60 = next((i for i in range(60) if i % 10 == tg and i % 12 == dz), 0)
    gz = TIANGAN[tg] + DIZHI[dz]
    base = 1984 + idx60
    for k in range(-3, 4):
        c = base + 60 * k
        if abs(c - year) <= 1:
            return gz, c
    return gz, None


def lichun_date(year):
    """返回 (月, 日, 时, 是否精确)。
    立春在 2/2–2/5 之间：从 2 月 1 日起扫到的第一个节气必为立春，
    不依赖节气名表（兼容各版本 sxtwl）；失败回退 2 月 4 日近似。"""
    if HAS_SXTWL:
        try:
            from datetime import datetime, timedelta, timezone
            d = sxtwl.fromSolar(year, 2, 1)
            for _ in range(10):
                if d.hasJieQi():
                    jd = d.getJieQiJD()
                    dt = datetime(2000, 1, 1, 12, tzinfo=timezone.utc) + timedelta(days=jd - 2451545.0)
                    dt = dt.astimezone(timezone(timedelta(hours=8)))
                    return dt.month, dt.day, dt.hour, True
                d = d.after(1)
        except Exception:
            pass
    return 2, 4, 0, False


def calc_ming_gua(year, gender):
    """命卦（统一式）。男=(1991-年)%9，女=(6-男数)%9，0 作 9；5 男寄坤/女寄艮。"""
    male = (1991 - year) % 9
    if male == 0:
        male = 9
    if gender in ("男", "male", "M", "m", "乾造"):
        num = male
        special = "男命五寄坤" if male == 5 else None
        return "坤" if male == 5 else GUA_NUMBER[male], male, special
    else:
        female = (6 - male) % 9
        if female == 0:
            female = 9
        return "艮" if female == 5 else GUA_NUMBER[female], female, ("女命五寄艮" if female == 5 else None)


def ming_gua_full(birth, gender, school="lichun"):
    """birth: 'YYYY-MM-DD' 或 'YYYY'。school: lichun=立春分界 / solar=公历年直接用。
    返回 dict；性别/日期非法时抛 ValueError。"""
    g = str(gender).strip().upper().rstrip("性")
    if g in ("男", "MALE", "M", "乾造", "男命"):
        gender = "男"
    elif g in ("女", "FEMALE", "F", "坤造", "女命"):
        gender = "女"
    else:
        raise ValueError(f"性别无法识别：{gender}（请提供 男/女）")
    year_only = False
    if "-" in birth:
        parts = birth.split("-")
        if len(parts) < 3:
            raise ValueError(f"出生日期不完整：{birth}（需 YYYY-MM-DD 或 YYYY）")
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        import datetime as _dt
        try:
            _dt.date(y, m, d)
        except ValueError:
            raise ValueError(f"出生日期不存在（如2月30日、平年2月29日）：{birth}")
    else:
        y = int(birth)
        m, d = 6, 15
        year_only = True
    if not (1804 <= y <= 2103):
        raise ValueError(f"出生年份 {y} 超出支持范围（1804-2103）")
    eff_year = y
    boundary_note = ""
    gz = None
    if school == "lichun":
        if year_only:
            boundary_note = "仅提供出生年份，未做立春分界（生于1月或2月上旬者请补充完整日期，两派命卦可能不同）"
        elif HAS_SXTWL:
            res = year_gz_via_sxtwl(y, m, d, True)
            if res and res[1]:
                gz, eff_year = res
                boundary_note = f"按立春分界（sxtwl 精确），计入{eff_year}年"
            else:
                boundary_note = "干支年定位失败，按公历年计"
                eff_year = y
        else:
            lc = lichun_date(y)
            exact = lc[3]
            if (m, d) < (lc[0], lc[1]):
                eff_year = y - 1
                boundary_note = f"出生在立春前（{y}年立春约{lc[0]}月{lc[1]}日{'，精确' if exact else '，按2月4日近似'}），计入{eff_year}年"
            elif not exact and (m, d) <= (2, 5):
                boundary_note = "⚠ 出生日临近立春（2月3-5日），分界敏感，两派命卦可能不同"
            else:
                boundary_note = f"立春后出生，计入{y}年"
    else:
        boundary_note = "按公历年直接计（民俗派）"
    gua, num, special = calc_ming_gua(eff_year, gender)
    cls = "东四命" if gua in DONG_SI else "西四命"
    return {"birth": birth, "gender": gender, "eff_year": eff_year, "year_gz": gz,
            "boundary_note": boundary_note, "ming_gua": gua, "gua_number": num,
            "special": special, "class": cls,
            "dayou": dayou_layout(gua)}


# ═══════════════════════════════════════════════════════════════
#  大游年（八宅）
# ═══════════════════════════════════════════════════════════════

def build_dayou_matrix():
    """由歌诀+环序程序化生成大游年矩阵：{伏位卦: {星: 卦}}，并断言 28 对对称。"""
    matrix = {}
    for gua, song in DA_YOU_NIAN_SONG.items():
        assert len(song) == 7, f"{gua} 歌诀长度错误"
        idx = RING.index(gua)
        others = RING[idx + 1:] + RING[:idx]
        row = {"伏位": gua}
        for ch, other in zip(song, others):
            row[SONG_CHAR_TO_STAR[ch]] = other
        assert len(row) == 8, f"{gua} 星数不足"
        matrix[gua] = row
    # 对称性校验：A 卦中 B 卦之星 == B 卦中 A 卦之星
    stars = ["生气", "延年", "天医", "伏位", "绝命", "五鬼", "祸害", "六煞"]
    for a in RING:
        for b in RING:
            star_a = [s for s, g in matrix[a].items() if g == b][0]
            star_b = [s for s, g in matrix[b].items() if g == a][0]
            assert star_a == star_b, f"大游年不对称: {a}-{b}: {star_a} vs {star_b}"
    return matrix


DAYOU_MATRIX = build_dayou_matrix()


def dayou_layout(fu_wei_gua):
    """{星: {卦, 方位, 吉凶, 北斗}}，按吉→凶排序。"""
    order = ["生气", "天医", "延年", "伏位", "祸害", "六煞", "五鬼", "绝命"]
    row = DAYOU_MATRIX[fu_wei_gua]
    out = {}
    for star in order:
        g = row[star]
        out[star] = {"卦": g, "方位": GUA_DIR[g], "吉凶": STAR_JI_XIONG[star],
                     "星": STAR_BEIDOU[star]}
    return out


def zhai_gua_of(zuo):
    """坐山宫 → 宅卦与东西四宅。"""
    g = mountain_palace(zuo)
    return g, ("东四宅" if g in DONG_SI else "西四宅")


# ═══════════════════════════════════════════════════════════════
#  流年紫白
# ═══════════════════════════════════════════════════════════════

def annual_star(year):
    """流年入中紫白星：A=(2027-y)%9，0 作 9。立春换年。"""
    a = (2027 - year) % 9
    return 9 if a == 0 else a


def year_ganzhi_simple(year):
    """年干支（立春分界的近似：整年计，供流年太岁用）。"""
    i = (year - 1984) % 60
    return TIANGAN[i % 10] + DIZHI[i % 12]


def annual_info(year):
    star = annual_star(year)
    gz = year_ganzhi_simple(year)
    zhi = gz[1]
    taishui_dir = ZHI_DIR.get(zhi, "?")
    suipo = DIZHI[(DIZHI.index(zhi) + 6) % 12]  # 太岁对冲之支，12 支皆有
    suipo_dir = ZHI_DIR.get(suipo, "?")
    sha_dir, sha_zhis = SAN_SHA[zhi]
    yun = fly(star, True)
    wuhuang = [p for p in FLY_PATH if p != "中" and yun[p] == 5]
    erhei = [p for p in FLY_PATH if p != "中" and yun[p] == 2]
    return {"year": year, "gz": gz, "star": star, "chart": yun,
            "太岁": {"支": zhi, "方位": taishui_dir, "宫": DIZHI_PALACE[zhi]},
            "岁破": {"支": suipo, "方位": suipo_dir, "宫": DIZHI_PALACE[suipo]},
            "三煞": {"方位": sha_dir, "支": sha_zhis,
                     "宫": [DIZHI_PALACE[b] for b in sha_zhis]},
            "五黄到": wuhuang, "二黑到": erhei}


# ═══════════════════════════════════════════════════════════════
#  排龙诀（中州派）
# ═══════════════════════════════════════════════════════════════

# 十二宫配山（地支本位 + 藏干之山）
PALONG_PALACES = {
    "子": ("子", "癸"), "丑": ("丑", "艮"), "寅": ("寅", "甲"), "卯": ("卯", "乙"),
    "辰": ("辰", "巽"), "巳": ("巳", "丙"), "午": ("午", "丁"), "未": ("未", "坤"),
    "申": ("申", "庚"), "酉": ("酉", "辛"), "戌": ("戌", "乾"), "亥": ("亥", "壬"),
}
PALONG_ORDER = list(PALONG_PALACES.keys())
# 十二星曜固定序：1破军 2右弼 3廉贞 4破军 5武曲 6贪狼 7破军 8左辅 9文曲 10破军 11巨门 12禄存
PALONG_STARS = ["破军", "右弼", "廉贞", "破军", "武曲", "贪狼",
                "破军", "左辅", "文曲", "破军", "巨门", "禄存"]
PALONG_JI = ("贪狼", "巨门", "武曲", "左辅", "右弼")   # 五吉
PALONG_WUXING = {"贪狼": "木", "巨门": "土", "禄存": "土", "文曲": "水",
                 "廉贞": "火", "武曲": "金", "破军": "金", "左辅": "土", "右弼": "土"}
# 河图当运可用龙：一六运贪武、二七运巨破、三八运辅禄、四九运文弼
PALONG_HEGUTU = {1: ("贪狼", "武曲"), 6: ("贪狼", "武曲"),
                 2: ("巨门", "破军"), 7: ("巨门", "破军"),
                 3: ("左辅", "禄存"), 8: ("左辅", "禄存"),
                 4: ("文曲", "右弼"), 9: ("文曲", "右弼")}


def palong_palace_of(mountain):
    """二十四山 → 排龙十二宫。"""
    for p, ms in PALONG_PALACES.items():
        if mountain in ms:
            return p
    return None


def palong_chart(long_mountain):
    """来龙山 → (12宫排龙盘 {宫: 星}, 阴顺/阳逆)。
    来龙对宫起破军；地支山属阴顺行，八干四维山属阳逆行。"""
    palace = palong_palace_of(long_mountain)
    if palace is None:
        raise ValueError(f"{long_mountain} 不在二十四山内")
    idx = PALONG_ORDER.index(palace)
    is_yin = long_mountain in DIZHI
    step = 1 if is_yin else -1
    chart = {}
    for k, star in enumerate(PALONG_STARS):
        chart[PALONG_ORDER[(idx + 6 + step * k) % 12]] = star
    return chart, ("阴顺行" if is_yin else "阳逆行")


def palong_verdict(chart, xiang, period=None):
    """现成宅：以向首所属宫的排龙星论吉凶。"""
    p = palong_palace_of(xiang)
    star = chart.get(p)
    is_ji = star in PALONG_JI
    hegu = PALONG_HEGUTU.get(period)
    usable = is_ji or (hegu and star in hegu)
    return {"向首宫": p, "龙星": star, "吉凶": "五吉龙" if is_ji else "七凶龙",
            "当运可用": usable, "龙五行": PALONG_WUXING.get(star, "?"),
            "说明": (f"{'五吉龙可用' if is_ji else '七凶龙本不宜用'}"
                     f"{('；惟' + star + '为' + str(period) + '运河图当旺之龙，权可取用（仅一元运）') if (usable and not is_ji) else ''}"
                     f"{'；五吉且当旺' if (is_ji and usable and hegu and star in hegu) else ''}")}


# ═══════════════════════════════════════════════════════════════
#  收山出煞诀（中州派）
# ═══════════════════════════════════════════════════════════════

# 诀云：四墓乙辛丁癸山，艮坤寅申子午间。出煞山头一十四，总宜倾泻不宜拦。
#       余外十山为收敛，须将生气秘牢关。
CHU_SHA_MOUNTAINS = set("丑未辰戌乙辛丁癸艮坤寅申子午")   # 出煞十四山：宜开扬
SHOU_SHAN_MOUNTAINS = set("壬甲卯巽巳丙庚酉乾亥")           # 收山十山：宜收敛


def shoushan_chusha(mountain):
    if mountain in CHU_SHA_MOUNTAINS:
        return {"山": mountain, "诀": "出煞", "宜": "宜开扬：门宜开畅（或门旁多窗），门内不宜屏风阻拦，门外地势宜略低", "忌": "忌过度收敛藏气"}
    return {"山": mountain, "诀": "收山", "宜": "宜收敛：门不宜过大，门内宜设玄关/屏风藏气，门外地势不宜过低", "忌": "忌开畅倾泻"}


# ═══════════════════════════════════════════════════════════════
#  日课择吉（玄空紫白 + 建除 + 通用宜忌）
# ═══════════════════════════════════════════════════════════════

JIANCHU = ["建", "除", "满", "平", "定", "执", "破", "危", "成", "收", "开", "闭"]
JIANCHU_HUANG = ("除", "危", "定", "执", "成", "开")   # 「除危定执黄……成开皆可用」
JIANCHU_HEI = ("建", "满", "平", "收", "破", "闭")
PENGZU_GAN = {"甲": "甲不开仓财物耗散", "乙": "乙不栽植千株不长", "丙": "丙不修灶必见灾殃",
              "丁": "丁不剃头头必生疮", "戊": "戊不受田田主不祥", "己": "己不破券二比并亡",
              "庚": "庚不经络织机虚张", "辛": "辛不合酱主人不尝", "壬": "壬不汲水更难提防",
              "癸": "癸不词讼理弱敌强"}
PENGZU_ZHI = {"子": "子不问卜自惹祸殃", "丑": "丑不冠带主不还乡", "寅": "寅不祭祀神鬼不尝",
              "卯": "卯不穿井水泉不香", "辰": "辰不哭泣必主重丧", "巳": "巳不远行财物伏藏",
              "午": "午不苫盖屋主更张", "未": "未不服药毒气入肠", "申": "申不安床鬼祟入房",
              "酉": "酉不会客醉坐颠狂", "戌": "戌不吃犬作怪上床", "亥": "亥不嫁娶不利新郎"}
# 月家紫白起例：子午卯酉年正月起八白、寅申巳亥年正月起二黑、辰戌丑未年正月起五黄，逐月递减
MONTH_STAR_START = {"子": 8, "午": 8, "卯": 8, "酉": 8,
                    "寅": 2, "申": 2, "巳": 2, "亥": 2,
                    "辰": 5, "戌": 5, "丑": 5, "未": 5}
# 日家紫白三元起例（歌诀：冬至雨水及谷雨，阳顺一七四中游；夏至处暑霜降后，九三六星逆行求）
JIEQI_NAMES = ["冬至", "小寒", "大寒", "立春", "雨水", "惊蛰", "春分", "清明", "谷雨", "立夏",
               "小满", "芒种", "夏至", "小暑", "大暑", "立秋", "处暑", "白露", "秋分", "寒露",
               "霜降", "立冬", "小雪", "大雪"]
DAY_STAR_YUAN = {0: (1, False), 4: (7, False), 8: (4, False),
                 12: (9, True), 16: (3, True), 20: (6, True)}   # idx → (起星, 是否阴遁逆行)
# 六十甲子玄空五行与卦运（福山堂《玄空飛星擇日法》载表；单源资料，重大决策宜另核）
XUANKONG_WUXING = {
    "甲子": ("水", 1), "乙丑": ("木", 6), "丙寅": ("火", 4),
    "丁卯": ("水", 9), "戊辰": ("金", 6), "己巳": ("木", 2),
    "庚午": ("木", 9), "辛未": ("金", 3), "壬申": ("水", 7),
    "癸酉": ("火", 7), "甲戌": ("火", 2), "乙亥": ("木", 3),
    "丙子": ("水", 3), "丁丑": ("金", 7), "戊寅": ("木", 6),
    "己卯": ("火", 8), "庚辰": ("水", 9), "辛巳": ("木", 7),
    "壬午": ("火", 1), "癸未": ("金", 8), "甲申": ("木", 9),
    "乙酉": ("金", 4), "丙戌": ("水", 1), "丁亥": ("木", 8),
    "戊子": ("火", 4), "己丑": ("金", 2), "庚寅": ("木", 1),
    "辛卯": ("火", 3), "壬辰": ("水", 4), "癸巳": ("金", 6),
    "甲午": ("金", 1), "乙未": ("火", 6), "丙申": ("木", 4),
    "丁酉": ("金", 9), "戊戌": ("水", 6), "己亥": ("火", 2),
    "庚子": ("火", 9), "辛丑": ("水", 3), "壬寅": ("金", 7),
    "癸卯": ("木", 7), "甲辰": ("木", 2), "乙巳": ("火", 3),
    "丙午": ("金", 3), "丁未": ("水", 7), "戊申": ("火", 6),
    "己酉": ("木", 8), "庚戌": ("金", 9), "辛亥": ("火", 7),
    "壬子": ("木", 1), "癸丑": ("水", 8), "甲寅": ("火", 9),
    "乙卯": ("水", 4), "丙辰": ("金", 1), "丁巳": ("火", 8),
    "戊午": ("木", 4), "己未": ("水", 2), "庚申": ("火", 1),
    "辛酉": ("木", 3), "壬戌": ("金", 4), "癸亥": ("水", 6),
}   # 卦运列据 laoshenpo/itmao 两源校正（原福山堂转录误取五行数为卦运）；运1恰为八纯卦

# 八纯卦（挨星卦运1）自检锚
XK_CHUN_GUA = ("甲子", "壬午", "庚寅", "丙辰", "甲午", "庚申", "丙戌", "壬子")
WUXING_SHENG = {"水": "木", "木": "火", "火": "土", "土": "金", "金": "水"}   # 我生
WUXING_KE = {"水": "火", "火": "金", "金": "木", "木": "土", "土": "水"}      # 我克

# ═══════════════════════════════════════════════════════════════
#  正体五行造命（补龙扶山相主）
# ═══════════════════════════════════════════════════════════════

NAYIN60 = {"甲子": "海中金", "乙丑": "海中金", "丙寅": "炉中火", "丁卯": "炉中火",
           "戊辰": "大林木", "己巳": "大林木", "庚午": "路旁土", "辛未": "路旁土",
           "壬申": "剑锋金", "癸酉": "剑锋金", "甲戌": "山头火", "乙亥": "山头火",
           "丙子": "涧下水", "丁丑": "涧下水", "戊寅": "城头土", "己卯": "城头土",
           "庚辰": "白蜡金", "辛巳": "白蜡金", "壬午": "杨柳木", "癸未": "杨柳木",
           "甲申": "泉中水", "乙酉": "泉中水", "丙戌": "屋上土", "丁亥": "屋上土",
           "戊子": "霹雳火", "己丑": "霹雳火", "庚寅": "松柏木", "辛卯": "松柏木",
           "壬辰": "长流水", "癸巳": "长流水", "甲午": "沙中金", "乙未": "沙中金",
           "丙申": "山下火", "丁酉": "山下火", "戊戌": "平地木", "己亥": "平地木",
           "庚子": "壁上土", "辛丑": "壁上土", "壬寅": "金箔金", "癸卯": "金箔金",
           "甲辰": "覆灯火", "乙巳": "覆灯火", "丙午": "天河水", "丁未": "天河水",
           "戊申": "大驿土", "己酉": "大驿土", "庚戌": "钗钏金", "辛亥": "钗钏金",
           "壬子": "桑柘木", "癸丑": "桑柘木", "甲寅": "大溪水", "乙卯": "大溪水",
           "丙辰": "沙中土", "丁巳": "沙中土", "戊午": "天上火", "己未": "天上火",
           "庚申": "石榴木", "辛酉": "石榴木", "壬戌": "大海水", "癸亥": "大海水"}
# 罗盘正五行（二十四山）
ZHENGTI_WX_24 = {"壬": "水", "子": "水", "癸": "水", "亥": "水",
                 "寅": "木", "甲": "木", "卯": "木", "乙": "木", "巽": "木",
                 "巳": "火", "丙": "火", "午": "火", "丁": "火",
                 "申": "金", "庚": "金", "酉": "金", "辛": "金", "乾": "金",
                 "辰": "土", "戌": "土", "丑": "土", "未": "土", "坤": "土", "艮": "土"}
GAN_WX = {"甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
          "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水"}
ZHI_WX = {"子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火",
          "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水"}
TIANREN_GUI = {"甲": ("丑", "未"), "戊": ("丑", "未"), "庚": ("丑", "未"),
               "乙": ("子", "申"), "己": ("子", "申"),
               "丙": ("亥", "酉"), "丁": ("亥", "酉"),
               "壬": ("卯", "巳"), "癸": ("卯", "巳"), "辛": ("午", "寅")}
GAN_LU = {"甲": "寅", "乙": "卯", "丙": "巳", "丁": "午", "戊": "巳",
          "己": "午", "庚": "申", "辛": "酉", "壬": "亥", "癸": "子"}
YIMA = {"申": "寅", "子": "寅", "辰": "寅", "寅": "申", "午": "申", "戌": "申",
        "巳": "亥", "酉": "亥", "丑": "亥", "亥": "巳", "卯": "巳", "未": "巳"}
GAN_CHONG = {"甲": "庚", "庚": "甲", "乙": "辛", "辛": "乙",
             "丙": "壬", "壬": "丙", "丁": "癸", "癸": "丁"}
SANHE_GROUPS = [("申", "子", "辰"), ("寅", "午", "戌"), ("巳", "酉", "丑"), ("亥", "卯", "未")]

# 董公择日数据（scripts/donggong_data.json，由《董公選擇日要覽》全文解析生成）
YUE_NAME_BY_ZHI = {"寅": "正月", "卯": "二月", "辰": "三月", "巳": "四月", "午": "五月", "未": "六月",
                   "申": "七月", "酉": "八月", "戌": "九月", "亥": "十月", "子": "十一月", "丑": "十二月"}
try:
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "donggong_data.json"),
              encoding="utf-8") as _f_dg:
        _DG = json.load(_f_dg)
    DONGGONG = _DG.get("月", {})
    DONGGONG_XIONG = _DG.get("凶神月表", {})
except Exception:
    DONGGONG, DONGGONG_XIONG = {}, {}


def _person_year_gz(birth):
    """主命年柱：完整日期用 sxtwl 立春分界；仅年份按公历年近似（民俗派）。"""
    if HAS_SXTWL and "-" in str(birth):
        y, m, d = [int(x) for x in str(birth).split("-")[:3]]
        res = year_gz_via_sxtwl(y, m, d, True)
        if res and res[1]:
            return res[0], True
    y = int(str(birth).split("-")[0])
    i = (y - 1984) % 60
    return TIANGAN[i % 10] + DIZHI[i % 12], False


def zaoming_analysis(sitting, pillars, persons=None):
    """正体五行造命：补龙扶山（阳宅以坐山论）、冲山检查、相主（纳音生克/冲命/贵人禄马到课）、格局亮点。"""
    zuo, _xiang = parse_sitting(sitting)
    shan_wx = ZHENGTI_WX_24[zuo]
    counts = {"生山": 0, "同山": 0, "山生（泄）": 0, "山克（耗）": 0, "克山": 0}
    for gz in pillars.values():
        for ch in gz:
            wx = GAN_WX.get(ch) or ZHI_WX.get(ch)
            if wx is None:
                continue
            if WUXING_SHENG[wx] == shan_wx:
                counts["生山"] += 1
            elif wx == shan_wx:
                counts["同山"] += 1
            elif WUXING_SHENG[shan_wx] == wx:
                counts["山生（泄）"] += 1
            elif WUXING_KE[shan_wx] == wx:
                counts["山克（耗）"] += 1
            else:
                counts["克山"] += 1
    ji = counts["生山"] + counts["同山"]
    xiong = counts["克山"] + counts["山生（泄）"]
    fushan = (f"坐山{zuo}属{shan_wx}（正五行）：课八字生扶/比和 {ji} 字，"
              f"克泄耗 {xiong} 字 → {'扶山得力' if ji >= 5 and counts['克山'] == 0 else ('扶山尚可' if ji > xiong else '扶山无力，宜另择')}")
    # 冲山
    chong_shan = []
    if zuo in DIZHI:
        chong = DIZHI[(DIZHI.index(zuo) + 6) % 12]
        chong_shan = [f"{k}柱支{gz[1]}" for k, gz in pillars.items() if gz[1] == chong]
    elif zuo in GAN_CHONG:
        chong_gan = GAN_CHONG[zuo]
        chong_shan = [f"{k}柱干{gz[0]}" for k, gz in pillars.items() if gz[0] == chong_gan]
    else:
        chong_shan = []
        fushan += "；四维山无支冲，忌对宫山向相冲（从略）"
    # 相主
    persons_out = []
    for b in (persons or []):
        try:
            ygz_b, precise = _person_year_gz(b)
        except (ValueError, TypeError) as e:
            persons_out.append({"birth": str(b), "error": str(e)})
            continue
        zhi_b = ygz_b[1]
        entry = {"birth": str(b), "年柱": ygz_b, "纳音": NAYIN60.get(ygz_b, "?"),
                 "立春精确": precise}
        if zhi_b in DIZHI:
            chong_ming = DIZHI[(DIZHI.index(zhi_b) + 6) % 12]
            entry["冲命"] = [f"{k}柱支{ch}" for k, gz in pillars.items() if gz[1] == chong_ming]
        ming_wx = NAYIN60.get(ygz_b, "?")[-1]
        rel = []
        for k, gz in pillars.items():
            ny = NAYIN60.get(gz)
            if not ny:
                continue
            w = ny[-1]
            if WUXING_SHENG[w] == ming_wx:
                rel.append(f"{k}柱{ny}生主命（吉）")
            elif w == ming_wx:
                rel.append(f"{k}柱{ny}比和（吉）")
            elif WUXING_KE[w] == ming_wx:
                rel.append(f"{k}柱{ny}克主命（凶）")
        entry["纳音生克"] = rel
        # 贵人禄马到课
        gui = TIANREN_GUI.get(ygz_b[0], ())
        lu = GAN_LU.get(ygz_b[0])
        ma = YIMA.get(zhi_b)
        zhis = [gz[1] for gz in pillars.values()]
        entry["贵人禄马到课"] = ([f"天乙贵人{g}" for g in gui if g in zhis]
                                + ([f"禄元{lu}"] if lu in zhis else [])
                                + ([f"驿马{ma}"] if ma in zhis else []))
        persons_out.append(entry)
    # 格局亮点
    gans = [gz[0] for gz in pillars.values()]
    zhis = [gz[1] for gz in pillars.values()]
    highlights = []
    top_gan = max(set(gans), key=gans.count)
    if gans.count(top_gan) == 4:
        highlights.append(f"天干一气纯{top_gan}（造命特格，须审五行不悖）")
    elif gans.count(top_gan) == 3:
        highlights.append(f"天干三朋（三{top_gan}）")
    if len(set(zhis)) == 1:
        highlights.append(f"地支一气（支纯{zhis[0]}）")
    zset = set(zhis)
    for grp in SANHE_GROUPS:
        if set(grp) <= zset:
            highlights.append(f"地支三合{(''.join(grp))}局（{ZHI_WX[grp[0]]}）")
            break
    result = {"坐山": zuo, "坐山五行": shan_wx, "扶山": fushan, "冲山": chong_shan,
              "课八字五行": counts, "相主": persons_out, "格局亮点": highlights}
    if chong_shan:
        result["综合提示"] = "⚠ 冲山/冲命为大忌，此课不可用，请改期"
    return result


def month_star(year_branch, month_branch):
    """月家紫白入中星：正月（寅月）起例逐月递减。"""
    off = (DIZHI.index(month_branch) - 2) % 12   # 寅月=正月
    return ((MONTH_STAR_START[year_branch] - 1 - off) % 9) + 1


def hour_star(day_branch, hour, yin):
    """时家紫白入中星。按日支分组起例：阳遁（冬至后）顺——子午卯酉日子时起一白、
    辰戌丑未日子时起四绿、寅申巳亥日子时起七赤；阴遁（夏至后）逆——起九紫/六白/三碧。"""
    hb = (int(hour) + 1) // 2 % 12          # 时支序：子时0
    group = DIZHI.index(day_branch) % 3     # 0=子午卯酉 1=辰戌丑未 2=寅申巳亥
    start = {0: (1, 9), 1: (4, 6), 2: (7, 3)}[group][1 if yin else 0]
    return ((start - 1 + (hb if not yin else -hb)) % 9) + 1


def _first_jiazi_after(y, m, d):
    """该日期（含当日）起第一个甲子日。"""
    from datetime import date as _date, timedelta as _td
    dd = _date(y, m, d)
    for _ in range(70):
        day = sxtwl.fromSolar(dd.year, dd.month, dd.day)
        g = day.getDayGZ()
        if g.tg == 0 and g.dz == 0:
            return dd
        dd += _td(days=1)
    return None


def day_star(y, m, d):
    """日家紫白入中星。返回 (星, 季, 元节气名, 元甲子日) 或 (None,)*4。
    六元：冬至/雨水/谷雨后首个甲子日分别起 1/7/4 顺行；夏至/处暑/霜降后起 9/3/6 逆行。"""
    if not HAS_SXTWL:
        return None, None, None, None
    from datetime import date as _date, timedelta as _td
    cur = _date(y, m, d)
    found = []   # 由近及远记录目标节气
    probe = cur
    for _ in range(200):
        day = sxtwl.fromSolar(probe.year, probe.month, probe.day)
        if day.hasJieQi():
            idx = day.getJieQi()
            if idx in DAY_STAR_YUAN:
                found.append((idx, probe))
                if len(found) >= 2:
                    break
        probe -= _td(days=1)
    for idx, jq_date in found:
        start, yin = DAY_STAR_YUAN[idx]
        jiazi = _first_jiazi_after(jq_date.year, jq_date.month, jq_date.day)
        if jiazi is None:
            continue
        n = (cur - jiazi).days
        if n >= 0:
            star = ((start - 1 + (n if not yin else -n)) % 9) + 1
            return star, ("阴遁（夏至后逆行）" if yin else "阳遁（冬至后顺行）"), JIEQI_NAMES[idx], jiazi
    return None, None, None, None


def li_jue(y, m, d):
    """四离四绝：四立（春夏秋冬）前一日为四绝，二分二至前一日为四离。"""
    if not HAS_SXTWL:
        return None
    from datetime import date as _date, timedelta as _td
    tmr = _date(y, m, d) + _td(days=1)
    day = sxtwl.fromSolar(tmr.year, tmr.month, tmr.day)
    if day.hasJieQi():
        name = JIEQI_NAMES[day.getJieQi()]
        if name in ("立春", "立夏", "立秋", "立冬"):
            return "四绝（" + name + "前一日）"
        if name in ("春分", "秋分", "夏至", "冬至"):
            return "四离（" + name + "前一日）"
    return None


def jianchu_day(month_branch, day_branch):
    """十二建除：月建起建，顺数至日支。月破日=破。"""
    idx = (DIZHI.index(day_branch) - DIZHI.index(month_branch)) % 12
    name = JIANCHU[idx]
    if name in JIANCHU_HUANG:
        grade = "黄道吉" + ("（成/开尤吉）" if name in ("成", "开") else "")
    elif name in ("破", "闭"):
        grade = "凶（破闭不相当）"
    else:
        grade = "黑道"
    return {"神": name, "级": grade, "月破": name == "破"}


def xk_relation(other_wx, other_yun, day_wx, day_yun):
    """玄空择日五要件：他（年月时）对我（日）——生入/克入/同旺/合十/生成为吉，生出/克出为凶。"""
    if other_wx == day_wx:
        rel = "同五行"
    elif WUXING_SHENG[other_wx] == day_wx:
        rel = "生入（吉）"
    elif WUXING_SHENG[day_wx] == other_wx:
        rel = "生出（凶）"
    elif WUXING_KE[other_wx] == day_wx:
        rel = "克入（吉）"
    else:
        rel = "克出（凶）"
    yun_rel = ""
    if other_yun == day_yun:
        yun_rel = "同旺（吉）"
    elif other_yun + day_yun == 10:
        yun_rel = "合十（吉）"
    elif abs(other_yun - day_yun) == 5:
        yun_rel = "生成（吉）"
    ji = ("吉" in rel) or bool(yun_rel)
    return {"关系": rel + (("；" + yun_rel) if yun_rel else ""), "吉": ji}


def riche_report(y, m, d, hour=None, sitting=None, persons=None):
    """日课择吉总输出（紫白+建除+董公+正体五行造命）。需 sxtwl。"""
    import re as _re
    out = {"date": f"{y:04d}-{m:02d}-{d:02d}", "hour": hour}
    if not HAS_SXTWL:
        out["error"] = "日课择吉需要 sxtwl（pip install sxtwl）提供四柱与节气"
        return out
    day = sxtwl.fromSolar(y, m, d)
    ygz, mgz, dgz = day.getYearGZ(False), day.getMonthGZ(), day.getDayGZ()
    pillars = {"年": TIANGAN[ygz.tg] + DIZHI[ygz.dz], "月": TIANGAN[mgz.tg] + DIZHI[mgz.dz],
               "日": TIANGAN[dgz.tg] + DIZHI[dgz.dz]}
    hgz = None
    if hour is not None:
        hgz = day.getHourGZ(hour)
        pillars["时"] = TIANGAN[hgz.tg] + DIZHI[hgz.dz]
    out["四柱"] = pillars
    out["日干支"] = pillars["日"]

    # 紫白四盘
    eff_year = next((1984 + i for i in range(60) if i % 10 == ygz.tg and i % 12 == ygz.dz
                     and abs(1984 + i - y) <= 1), y)
    ystar = annual_star(eff_year)
    mstar = month_star(DIZHI[ygz.dz], DIZHI[mgz.dz])
    dstar, season, yuan_name, jiazi = day_star(y, m, d)
    out["紫白"] = {"年星": ystar, "年有效年": eff_year,
                   "月星": mstar, "月建支": DIZHI[mgz.dz],
                   "日星": dstar, "日季": season, "日元起": (f"{yuan_name}后首个甲子{jiazi.isoformat()}" if jiazi else None)}
    if hour is not None and dstar:
        yin = "阴遁" in (season or "")
        hstar = hour_star(DIZHI[dgz.dz], hour, yin)
        out["紫白"]["时星"] = hstar

    # 建除 / 月破 / 岁破 / 日冲 / 彭祖 / 离绝
    jc = jianchu_day(DIZHI[mgz.dz], DIZHI[dgz.dz])
    day_zhi = DIZHI[dgz.dz]
    year_zhi = DIZHI[ygz.dz]
    chong_zhi = DIZHI[(DIZHI.index(day_zhi) + 6) % 12]
    out["建除"] = jc
    out["月破日"] = jc["月破"]
    out["岁破日"] = day_zhi == DIZHI[(DIZHI.index(year_zhi) + 6) % 12]
    out["日冲"] = f"冲{chong_zhi}（生肖{'鼠牛虎兔龙蛇马羊猴鸡狗猪'[DIZHI.index(chong_zhi)]}）"
    out["彭祖百忌"] = [PENGZU_GAN[TIANGAN[dgz.tg]], PENGZU_ZHI[day_zhi]]
    lj = li_jue(y, m, d)
    out["四离四绝"] = lj

    # 玄空五行五要件（年/月/时 对 日辰）
    dwx = XUANKONG_WUXING.get(pillars["日"])
    if dwx:
        evals = {}
        for k in ("年", "月", "时"):
            if k in pillars:
                ox = XUANKONG_WUXING.get(pillars[k])
                if ox:
                    evals[k] = {"干支": pillars[k], "玄空五行": ox[0], "卦运": ox[1],
                                **xk_relation(ox[0], ox[1], dwx[0], dwx[1])}
        out["玄空五行"] = {"日": {"干支": pillars["日"], "五行": dwx[0], "卦运": dwx[1]},
                           "对日辰评估": evals,
                           "来源注": "六十甲子玄空五行卦运表为单源资料，重大事项宜另核"}

    # 综合提示（先初始化，供董公/造命块追加）
    tips = []
    if jc["月破"]:
        tips.append("⚠ 月破日，大事勿用")
    if out["岁破日"]:
        tips.append("⚠ 岁破日，大事勿用")
    if lj:
        tips.append(f"⚠ {lj}，诸事不宜（尤其动土、搬迁）")
    tips.append(f"日冲{chong_zhi}：家中属{'鼠牛虎兔龙蛇马羊猴鸡狗猪'[DIZHI.index(chong_zhi)]}者此日大事尽量回避")
    if jc["神"] in ("成", "定", "开"):
        tips.append("建除成/定/开，利入宅、开市、安床等喜庆事")
    elif jc["神"] in ("破", "闭"):
        tips.append("建除破/闭，不宜入宅、动土、开业")

    # 董公择日（月建+建除断语；干支命中句；月三煞前奏）
    yue_name = YUE_NAME_BY_ZHI[DIZHI[mgz.dz]]
    if DONGGONG:
        blk = DONGGONG.get(yue_name, {})
        d_entry = blk.get("断", {}).get(jc["神"])
        if d_entry:
            hits = [s.strip() for s in _re.split(r"[。；]", d_entry["断语"]) if pillars["日"] in s]
            out["董公"] = {"月": yue_name, "神": jc["神"], "断语": d_entry["断语"],
                           "干支命中句": hits, "月前奏": blk.get("前奏", "")}
            if "来源" in d_entry:
                out["董公"]["来源"] = d_entry["来源"]
    # 附录凶神日（往亡/受死/月厌…按月支对照）
    xiong_hits = []
    for xname, tbl in DONGGONG_XIONG.items():
        if tbl.get("月", {}).get(yue_name) == day_zhi:
            xiong_hits.append(f"{xname}（{tbl.get('说明','')}）")
    if xiong_hits:
        out["凶神日"] = xiong_hits
        tips.append("⚠ 董公凶神日：" + "；".join(xiong_hits))

    # 正体五行造命（补龙扶山相主）
    if sitting:
        try:
            out["造命"] = zaoming_analysis(sitting, pillars, persons)
            zm = out["造命"]
            tips.append(zm["扶山"])
            if zm["冲山"]:
                tips.append("⚠ " + "、".join(zm["冲山"]) + "：冲坐山，此课不可用")
            for p in zm["相主"]:
                if p.get("冲命"):
                    tips.append(f"⚠ 主命{p.get('年柱')}被课冲（{'、'.join(p['冲命'])}），不可用")
                elif p.get("贵人禄马到课"):
                    tips.append(f"主命{p.get('年柱')}：{'、'.join(p['贵人禄马到课'])}到课，催贵（吉）")
        except ValueError as e:
            out["造命"] = {"error": str(e)}
    if sitting:
        zuo, _xiang = parse_sitting(sitting)
        ss_x = shoushan_chusha(_xiang)
        tips.append(f"向首{_xiang}属{ss_x['诀']}：{ss_x['宜']}")
    if not tips:
        tips.append("无破格；具体事宜结合紫白与宅盘参断")
    out["提示"] = tips
    return out

STAR_NUM_NAME = {1: "一白", 2: "二黑", 3: "三碧", 4: "四绿", 5: "五黄",
                 6: "六白", 7: "七赤", 8: "八白", 9: "九紫"}


def render_chart(charts, zuo, xiang, title=""):
    """三盘九宫图（上南下北）。每宫：左上山星 右向星 / 下运星。"""
    lines = []
    lines.append(f"┌──────────────────────────────────────────┐  {title}")
    for row in GRID_LAYOUT:
        cells_top, cells_mid, cells_bot = [], [], []
        for p in row:
            if p == "中":
                cells_top.append("   中五   ")
                cells_mid.append("          ")
                cells_bot.append("          ")
            else:
                s, x, y = charts["shan"][p], charts["xiang"][p], charts["yun"][p]
                mark = ""
                if zuo and p == mountain_palace(zuo):
                    mark = "【坐】"
                elif xiang and p == mountain_palace(xiang):
                    mark = "【向】"
                cells_top.append(f"  {s}   {x}   ")
                cells_mid.append(f"  {y}  {STAR_NUM_NAME[y][:2]}{mark}".ljust(10))
                cells_bot.append(f"  {p}({GUA_DIR[p]}) ")
        lines.append("├" + "┬".join(["──────────"] * 3) + "┤")
        lines.append("│" + "│".join(cells_top) + "│")
        lines.append("│" + "│".join(cells_mid) + "│")
        lines.append("│" + "│".join(cells_bot) + "│")
    lines.append("└" + "┴".join(["──────────"] * 3) + "┘")
    return "\n".join(lines)


def render_dayou(layout, title=""):
    lines = [f"【{title}】大游年八星方位："]
    for star, info in layout.items():
        lines.append(f"  {star}（{info['星']}）→ {info['卦']}宫 {info['方位']}  {info['吉凶']}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  完整分析
# ═══════════════════════════════════════════════════════════════

def get_yun_by_year(year):
    for yun, lo, hi, name in YUN_TABLE:
        if lo <= year <= hi:
            return yun, name
    return None, None


def pos_to_palace(pos):
    import re as _re
    pos = str(pos).strip()
    # 口语归一化：正南/东北方/北侧/南面/向南 等
    pos = _re.sub(r"^[正偏单]", "", pos)
    pos = _re.sub(r"[侧向方面]$", "", pos)
    pos = pos.strip()
    if pos in FLY_PATH:
        return pos
    # 精确匹配方位名
    for g, d in GUA_DIR.items():
        if pos == d:
            return g
    # 最长前缀匹配（"东南"必须先于"东"、"西北"先于"西"）
    best = None
    for g, d in GUA_DIR.items():
        if pos.startswith(d) and (best is None or len(d) > len(best[1])):
            best = (g, d)
    if best:
        return best[0]
    # 地支方位
    if pos in ZHI_DIR:
        zd = ZHI_DIR[pos]
        best = None
        for g, d in GUA_DIR.items():
            if zd.startswith(d) and (best is None or len(d) > len(best[1])):
                best = (g, d)
        if best:
            return best[0]
    # 度数
    try:
        deg = float(pos.replace("°", ""))
        m, _, _ = mountain_from_deg(deg)
        return mountain_palace(m)
    except ValueError:
        pass
    return None


def analyze_house(house, current_year=2026):
    """house dict → 完整分析 dict。支持扁平结构与 {house:{...}, persons:[], rooms:[]} 嵌套结构。"""
    if isinstance(house.get("house"), dict):
        flat = dict(house["house"])
        for k in ("persons", "rooms", "external"):
            if k in house:
                flat[k] = house[k]
        house = flat
    result = {"meta": {"current_year": current_year, "sxtwl": HAS_SXTWL}}
    # 1) 定运
    built = house.get("built_year")
    yun, yun_name = get_yun_by_year(built) if built else (house.get("period"), None)
    try:
        yun = int(yun)
    except (TypeError, ValueError):
        yun = None
    if yun is None or not 1 <= yun <= 9:
        result["error"] = (f"无法定运：建成年份 {built} 不在三元九运表范围（1864-2043），"
                           f"或未提供有效的运别；可在 house 中用 \"period\": 1-9 手工指定")
        return result
    result["yun"] = {"period": yun, "name": yun_name, "built_year": built}

    # 2) 坐向
    sitting_spec = house.get("sitting")
    if not sitting_spec or not isinstance(sitting_spec, str):
        result["error"] = f"缺少有效的 sitting 坐向声明（得到 {sitting_spec!r}），如 '子山午向'"
        return result
    try:
        zuo, xiang = parse_sitting(sitting_spec)
    except ValueError as e:
        result["error"] = str(e)
        return result
    warnings = []
    mode = "下卦"
    deviation = None
    deg = house.get("sitting_deg")
    if deg is not None:
        deg = float(deg)
        zuo_center = mountain_index(zuo) * 15.0
        xiang_center = mountain_index(xiang) * 15.0
        # sitting_deg 优先按"朝向度数"（面向屋外实测，即向的度数）解释
        dev_xiang = ((deg - xiang_center + 180.0) % 360.0) - 180.0
        dev_zuo = ((deg - zuo_center + 180.0) % 360.0) - 180.0
        if abs(dev_xiang) <= 7.5:
            deviation = dev_xiang
        elif abs(dev_zuo) <= 7.5:
            deviation = dev_zuo
            warnings.append("sitting_deg 按坐山度数解释（未按朝向度数）；请确认测量方式")
        else:
            m_at, _, _ = mountain_from_deg(deg)
            deviation = None
            warnings.append(f"度数 {deg}° 落在{m_at}山附近，与声明的坐{zuo}向{xiang}明显不符；已忽略度数、按声明坐向排盘，请核对坐向后再排")
    if deviation is not None:
        ade = abs(deviation)
        # 兼向分界：沈氏/中州派"每山正中九度"为下卦（±4.5°），其余用替卦
        if ade <= 4.5:
            mode = "下卦（正向）"
            if ade > 3:
                warnings.append(f"偏向{deviation:+.1f}°：按沈氏/中州派标准（正向±4.5°）仍用下卦（本盘）；另有流派以3°为界用替卦，保守起见可加 --replace 排替卦盘对照")
        else:
            mode = "替卦（兼向超4.5°）"
            warnings.append(f"偏向{deviation:+.1f}°，超出正向4.5°，用替卦排盘")
            if ade > 6:
                warnings.append("兼向超过6°，各派对大兼向处理不一，建议复核罗盘坐向")
            if ade > 6.5:
                warnings.append("偏离中轴超过6.5°，逼近两山交界（骑线/空亡风险），务必实地复核坐向")
        # 跨宫兼向检查：偏向一侧的邻山是否属另一宫
        side_idx = mountain_index(zuo) + (1 if deviation > 0 else -1)
        neighbor = MOUNTAIN_ORDER[side_idx % 24]
        if mountain_palace(neighbor) != mountain_palace(zuo):
            warnings.append(f"兼向跨宫（{zuo}兼{neighbor}，{neighbor}属{mountain_palace(neighbor)}宫）：出卦兼向，传统认为不可用，务必复核坐向")
    # replace 严格按布尔处理（P0 修复：字符串 "false" 不得真值触发替卦）
    replace_in = house.get("replace")
    replace = None
    if isinstance(replace_in, bool):
        replace = replace_in
    elif isinstance(replace_in, str):
        rv = replace_in.strip().lower()
        if rv in ("true", "1", "yes", "是"):
            replace = True
        elif rv in ("false", "0", "", "no", "否"):
            replace = False
        else:
            warnings.append(f"house.replace 值无法识别（{replace_in!r}），已忽略，按坐向偏差自动判定")
    elif replace_in is not None:
        warnings.append(f"house.replace 类型无效（{replace_in!r}），已忽略，按坐向偏差自动判定")
    auto_replace = mode.startswith("替卦")
    if replace is None:
        replace = auto_replace
    elif replace != auto_replace:
        warnings.append(f"已按 house.replace={replace} 强制{'替卦' if replace else '下卦'}排盘"
                        f"（按坐向偏差本应{'替卦' if auto_replace else '下卦'}）")
    charts = paipan_tigua(yun, zuo, xiang) if replace else paipan_xiagua(yun, zuo, xiang)
    geju, geju_detail = judge_geju(yun, charts, zuo, xiang)
    flags = special_flags(charts, yun)
    dajie = qixing_dajie(charts, yun, xiang)
    if dajie:
        flags.append(dajie)
    cm = chengmen(charts, yun, xiang)
    zhai_gua, zhai_cls = zhai_gua_of(zuo)

    result["sitting"] = {
        "spec": sitting_spec, "坐山": zuo, "向山": xiang,
        "坐山三元龙": mountain_yuan(zuo), "向山三元龙": mountain_yuan(xiang),
        "坐山阴阳": mountain_yinyang(zuo), "向山阴阳": mountain_yinyang(xiang),
        "坐山宫": mountain_palace(zuo), "向首宫": mountain_palace(xiang),
        "度数偏差": deviation, "排盘方式": mode, "替卦": replace,
        "warnings": warnings,
    }
    result["feixing"] = {"charts": charts, "格局": geju, "格局细节": geju_detail,
                         "特殊": flags, "notes": charts["notes"], "城门": cm,
                         "收山出煞": {"向首": shoushan_chusha(xiang), "坐山": shoushan_chusha(zuo),
                                      "要诀": "中州派收山出煞诀：出煞十四山宜开扬、收山十山宜收敛"}}
    result["zhai"] = {"宅卦": zhai_gua, "东西四宅": zhai_cls, "宅卦大游年": dayou_layout(zhai_gua)}

    # 3) 命主（畸形条目单条跳过，不中止整体；缺性别给出显著提示）
    persons = []
    for p in house.get("persons", []):
        if not isinstance(p, dict):
            persons.append({"name": str(p)[:24], "error": "persons 条目须为对象 {name, birth, gender}"})
            continue
        try:
            info = ming_gua_full(p["birth"], p.get("gender", "男"),
                                 p.get("school", "lichun"))
        except (ValueError, KeyError, TypeError) as e:
            persons.append({"name": str(p.get("name", "命主")), "error": str(e)})
            continue
        info["name"] = str(p.get("name", "命主"))
        if p.get("gender") is None or str(p.get("gender", "")).strip() == "":
            info["warning"] = "未提供性别，暂按男命计算，请确认！"
        persons.append(info)
    result["persons"] = persons

    # 4) 房间（畸形条目单条跳过）
    rooms = []
    for r in house.get("rooms", []):
        if not isinstance(r, dict):
            rooms.append({"name": str(r)[:24], "error": "房间条目须为对象 {name, pos}"})
            continue
        rname = str(r.get("name", "未命名房间"))
        if "pos" not in r:
            rooms.append({"name": rname, "error": "缺少 pos 字段（房间方位）"})
            continue
        palace = pos_to_palace(str(r["pos"]))
        if palace is None:
            rooms.append({"name": rname, "pos": r["pos"], "error": "无法识别方位"})
            continue
        entry = {"name": rname, "pos": r["pos"], "宫": palace, "方位": GUA_DIR.get(palace, "中宫")}
        if palace != "中":
            entry["八宅星(宅卦)"] = _star_at(result["zhai"]["宅卦大游年"], palace)
            entry["八宅星(各命主)"] = {
                per["name"]: _star_at(per["dayou"], palace)
                for per in persons if "dayou" in per
            }
            entry["玄空"] = {"山星": charts["shan"][palace], "向星": charts["xiang"][palace],
                             "运星": charts["yun"][palace]}
        else:
            entry["八宅星(宅卦)"] = "中宫无八宅星"
        rooms.append(entry)
    result["rooms"] = rooms
    result["external"] = house.get("external", [])

    # 4.5) 排龙诀（提供水口信息时）
    shuikou = house.get("shuikou")
    if shuikou:
        try:
            s = str(shuikou).strip()
            if s in MOUNTAIN_ORDER:
                sk_m = s
            else:
                sk_m, _, _ = mountain_from_deg(float(s.replace("°", "")))
            long_m = opposite_mountain(sk_m)   # 面向水口时，人端之山为来龙（水口方之山的对山）
            pl_chart, pl_dir = palong_chart(long_m)
            result["pailong"] = {"水口方山": sk_m, "来龙": long_m, "行向": pl_dir,
                                 "十二宫": pl_chart,
                                 **palong_verdict(pl_chart, xiang, yun)}
        except (ValueError, TypeError) as e:
            result["pailong"] = {"error": f"水口解析失败：{e}"}

    # 5) 流年
    ay_raw = house.get("annual_year", current_year)
    try:
        ay = int(ay_raw)
        if not 1804 <= ay <= 2103:
            raise ValueError
        result["annual"] = annual_info(ay)
    except (TypeError, ValueError):
        result["annual"] = {"error": f"流年年份无效：{ay_raw!r}（须为 1804-2103 的整数；注意流年按立春换年）"}
    return result


def _star_at(layout, palace):
    for star, info in layout.items():
        if info["卦"] == palace:
            return star
    return None


def format_result(res):
    L = []
    if "error" in res:
        return f"❌ {res['error']}"
    L.append("═" * 60)
    L.append("阳宅风水排盘（yangzhai-fengshui）")
    L.append("═" * 60)
    yun = res["yun"]
    yun_label = yun["name"] if yun.get("name") else f"{yun['period']}运"
    L.append(f"宅运：{yun_label}（建成 {yun['built_year']}）")
    st = res["sitting"]
    L.append(f"坐向：坐{st['坐山']}（{st['坐山三元龙']}，{st['坐山阴阳']}）朝{st['向山']}，"
             f"坐{st['坐山宫']}宫向{st['向首宫']}宫")
    if st["度数偏差"] is not None:
        L.append(f"坐向度数偏差：{st['度数偏差']:+.1f}° → {st['排盘方式']}")
    for w in st["warnings"]:
        L.append(f"  ⚠ {w}")
    fx = res["feixing"]
    L.append("")
    L.append(render_chart(fx["charts"], st["坐山"], st["向山"],
                          f"{yun['period']}运 {'替卦' if st['替卦'] else '下卦'} {st['坐山']}山{st['向山']}向"))
    for n in fx["notes"]:
        L.append(f"  · {n}")
    L.append(f"格局：{fx['格局']}")
    ss = fx.get("收山出煞")
    if ss:
        L.append(f"收山出煞：向首{ss['向首']['山']}属{ss['向首']['诀']}（{ss['向首']['宜']}）；"
                 f"坐山{ss['坐山']['山']}属{ss['坐山']['诀']}")
    for f in fx["特殊"]:
        L.append(f"  ◆ {f}")
    L.append(f"  · 旺山星({yun['period']})在：{'、'.join(fx['格局细节']['旺山星所在']) or '无'}；"
             f"旺向星在：{'、'.join(fx['格局细节']['旺向星所在']) or '无'}")
    L.append("")
    zhai = res["zhai"]
    L.append(render_dayou(zhai["宅卦大游年"], f"宅卦{zhai['宅卦']}（{zhai['东西四宅']}）"))
    for per in res["persons"]:
        L.append("")
        if "error" in per:
            L.append(f"命主【{per['name']}】⚠ {per['error']}")
            continue
        L.append(f"命主【{per['name']}】{per['birth']} {per['gender']}性 → {per['ming_gua']}命（{per['class']}）"
                 f"{('，' + per['special']) if per['special'] else ''}")
        if per.get("warning"):
            L.append(f"  ⚠ {per['warning']}")
        if per["year_gz"]:
            L.append(f"  年干支：{per['year_gz']}；{per['boundary_note']}")
        else:
            L.append(f"  {per['boundary_note']}")
        L.append(render_dayou(per["dayou"], f"{per['ming_gua']}命").split("\n", 1)[1])
        match = "相配" if (per["class"] == "东四命") == (zhai["东西四宅"] == "东四宅") else "不相配"
        L.append(f"  宅命相配：{per['class']} 住 {zhai['东西四宅']} → {'✅' if match == '相配' else '⚠️'}{match}")
    L.append("")
    L.append("房间方位：")
    for r in res["rooms"]:
        if "error" in r:
            L.append(f"  ✗ {r['name']}（{r['pos']}）：{r['error']}")
            continue
        if r["宫"] == "中":
            L.append(f"  · {r['name']}：中宫（火烧心/中央受污高危位）")
            continue
        extra = f"，八宅星：宅卦{r['八宅星(宅卦)']}"
        if r.get("八宅星(各命主)"):
            extra += "；" + "；".join(f"{k}命看为{v}" for k, v in r["八宅星(各命主)"].items())
        L.append(f"  · {r['name']}：{r['宫']}宫（{r['方位']}）{extra}；"
                 f"玄空山{r['玄空']['山星']}向{r['玄空']['向星']}运{r['玄空']['运星']}")
    ext = res.get("external") or []
    if ext:
        L.append("外部环境（供形煞评估）：")
        for e in ext:
            L.append(f"  · {e}")
    an = res["annual"]
    pl = res.get("pailong")
    L.append("")
    if pl:
        if "error" in pl:
            L.append(f"排龙：⚠ {pl['error']}")
        else:
            L.append(f"排龙诀（中州派）：水口方{pl['水口方山']} → 来龙{pl['来龙']}（{pl['行向']}）"
                     f"；宅向首{pl['向首宫']}宫得【{pl['龙星']}龙】{pl['吉凶']}，{pl['说明']}")
            L.append("  十二宫龙星：" + " ".join(f"{g}{s}" for g, s in pl["十二宫"].items())
                     + "　（五吉：右左贪巨武；以吉龙宫内二山为向首选向）")
    if "error" in an:
        L.append(f"  ⚠ 流年：{an['error']}")
    else:
        L.append(f"流年【{an['year']} {an['gz']}年】：{STAR_NUM_NAME[an['star']]}入中")
        L.append(f"  太岁{an['太岁']['支']}（{an['太岁']['方位']}/{an['太岁']['宫']}宫），"
                 f"岁破{an['岁破']['支']}（{an['岁破']['方位']}/{an['岁破']['宫']}宫），三煞在{an['三煞']['方位']}"
                 f"（{'、'.join(an['三煞']['宫']) if an['三煞']['宫'] else an['三煞']['支']}）")
        L.append(f"  五黄到{'、'.join(an['五黄到']) or '中宫'}，二黑到{'、'.join(an['二黑到']) or '中宫'}")
    L.append("")
    L.append("（流年盘与逐宫吉凶详见 SKILL.md 流程与 references/）")
    return "\n".join(L)


# ═══════════════════════════════════════════════════════════════
#  selftest
# ═══════════════════════════════════════════════════════════════

def selftest():
    errors = []

    def check(name, cond, detail=""):
        if cond:
            print(f"  ✅ {name}")
        else:
            errors.append(name)
            print(f"  ❌ {name} {detail}")

    print("── 命卦公式 ──")
    vectors = [
        (1984, "男", "兑"), (1990, "男", "坎"), (1990, "女", "艮"),
        (1995, "男", "坤"), (1995, "女", "坎"), (2000, "男", "离"),
        (2000, "女", "乾"), (2024, "男", "震"), (2024, "女", "震"),
        (1976, "男", "乾"), (1976, "女", "离"), (1988, "男", "震"),
        (2026, "男", "坎"), (2026, "女", "艮"),
    ]
    for y, g, expect in vectors:
        gua, num, _ = calc_ming_gua(y, g)
        check(f"{y}{g}→{expect}", gua == expect, f"实得{gua}")
    # 立春分界（sxtwl 精确 / 无 sxtwl 近似都应得出 1998-01-29 男→震）
    info = ming_gua_full("1998-01-29", "男")
    check("1998-01-29男→震（立春前算1997）", info["ming_gua"] == "震" and info["eff_year"] == 1997,
          f"实得{info['ming_gua']}({info['eff_year']})")

    print("── 大游年矩阵 ──")
    m = DAYOU_MATRIX
    check("乾兑生气", m["乾"]["生气"] == "兑" and m["兑"]["生气"] == "乾")
    check("乾坤延年", m["乾"]["延年"] == "坤" and m["坤"]["延年"] == "乾")
    check("坎巽生气", m["坎"]["生气"] == "巽" and m["巽"]["生气"] == "坎")
    check("坎震天医", m["坎"]["天医"] == "震" and m["震"]["天医"] == "坎")
    check("震离生气", m["震"]["生气"] == "离" and m["离"]["生气"] == "震")
    check("离巽天医", m["离"]["天医"] == "巽" and m["巽"]["天医"] == "离")
    check("乾离绝命", m["乾"]["绝命"] == "离" and m["离"]["绝命"] == "乾")
    check("乾震五鬼", m["乾"]["五鬼"] == "震" and m["震"]["五鬼"] == "乾")
    check("对称性28对", True)  # build_dayou_matrix 内已断言

    print("── 玄空下卦 ──")
    # 八运子山午向 = 双星会向（向首山8向8）
    ch = paipan_xiagua(8, "子", "午")
    geju, _ = judge_geju(8, ch, "子", "午")
    check("八运子山午向=双星会向", geju == "双星会向", f"实得{geju}")
    check("八运子山午向坐山山星9", ch["shan"]["坎"] == 9, f"实得{ch['shan']['坎']}")
    # 八运午山子向 = 双星会坐
    ch = paipan_xiagua(8, "午", "子")
    geju, _ = judge_geju(8, ch, "午", "子")
    check("八运午山子向=双星会坐", geju == "双星会坐", f"实得{geju}")
    # 八运乾山巽向 = 旺山旺向
    ch = paipan_xiagua(8, "乾", "巽")
    geju, _ = judge_geju(8, ch, "乾", "巽")
    check("八运乾山巽向=旺山旺向", geju == "旺山旺向", f"实得{geju}")
    # 八运丑山未向 = 旺山旺向
    ch = paipan_xiagua(8, "丑", "未")
    geju, _ = judge_geju(8, ch, "丑", "未")
    check("八运丑山未向=旺山旺向", geju == "旺山旺向", f"实得{geju}")
    # 九运午山子向 = 双星会向（九运下卦无旺山旺向/上山下水，全为双星局）
    ch = paipan_xiagua(9, "午", "子")
    geju, _ = judge_geju(9, ch, "午", "子")
    check("九运午山子向=双星会向", geju == "双星会向", f"实得{geju}")
    ch = paipan_xiagua(9, "子", "午")
    geju, _ = judge_geju(9, ch, "子", "午")
    check("九运子山午向=双星会坐", geju == "双星会坐", f"实得{geju}")
    # 七/八运旺山旺向、上山下水各六局（已与出版盘面核对）
    for period, want_wswx, want_sxsx in [
        (7, {"卯酉", "乙辛", "辰戌", "酉卯", "辛乙", "戌辰"},
         {"甲庚", "巽乾", "巳亥", "庚甲", "乾巽", "亥巳"}),
        (8, {"丑未", "巽乾", "巳亥", "未丑", "乾巽", "亥巳"},
         {"艮坤", "寅申", "辰戌", "坤艮", "申寅", "戌辰"}),
    ]:
        wswx, sxsx = set(), set()
        for zuo in MOUNTAIN_ORDER:
            xiang = opposite_mountain(zuo)
            c = paipan_xiagua(period, zuo, xiang)
            g, _ = judge_geju(period, c, zuo, xiang)
            key = f"{zuo}{xiang}"
            if g == "旺山旺向":
                wswx.add(key)
            elif g == "上山下水":
                sxsx.add(key)
        check(f"{period}运旺山旺向六局", wswx == want_wswx, f"实得{sorted(wswx)}")
        check(f"{period}运上山下水六局", sxsx == want_sxsx, f"实得{sorted(sxsx)}")
    # 九运下卦结构性质：24 山全为双星会坐/会向
    nine = set()
    for zuo in MOUNTAIN_ORDER:
        c = paipan_xiagua(9, zuo, opposite_mountain(zuo))
        g, _ = judge_geju(9, c, zuo, opposite_mountain(zuo))
        nine.add(g)
    check("九运下卦全为双星局", nine == {"双星会坐", "双星会向"}, f"实得{sorted(nine)}")

    print("── 流年紫白 ──")
    for y, s in [(2024, 3), (2025, 2), (2026, 1), (2027, 9), (2017, 1), (2035, 1)]:
        check(f"{y}年{s}入中", annual_star(y) == s, f"实得{annual_star(y)}")

    print("── 坐向解析 ──")
    m1, c1, d1 = mountain_from_deg(352)
    check("352°→壬山", m1 == "壬", f"实得{m1}")
    m2, _, d2 = mountain_from_deg(0)
    check("0°→子山", m2 == "子", f"实得{m2}")
    check("对宫", opposite_mountain("子") == "午" and opposite_mountain("壬") == "丙")
    z1, x1 = parse_sitting("子山午向")
    check("解析'子山午向'", (z1, x1) == ("子", "午"))
    z2, x2 = parse_sitting("350")
    check("解析'350°'→坐壬向丙", (z2, x2) == ("壬", "丙"), f"实得{z2}山{x2}向")

    print("── 替星诀 ──")
    check("替数只有1/2/6/7/9", set(TI_XING_JUE.values()) == {1, 2, 6, 7, 9})
    check("24山全覆盖", len(TI_XING_JUE) == 24)
    # 实例验证（三六风水网教程实例，顺逆按原查之山阴阳）
    ch = paipan_tigua(8, "卯", "酉")  # 八运卯山酉向兼乙辛：山6入中顺（乾阳）、向1入中逆（子阴）
    check("替卦例1: 八运卯酉山盘6顺", ch["shan"]["中"] == 6 and ch["shan_forward"],
          f"实得{ch['shan']['中']},{ch['shan_forward']}")
    check("替卦例1: 八运卯酉向盘1逆", ch["xiang"]["中"] == 1 and not ch["xiang_forward"],
          f"实得{ch['xiang']['中']},{ch['xiang_forward']}")
    check("替卦例1: 山盘乾7兑8", ch["shan"]["乾"] == 7 and ch["shan"]["兑"] == 8)
    ch = paipan_tigua(3, "子", "午")  # 三运子山午向兼壬丙：山8替7入中顺（艮阳）、向7入中逆（酉阴）
    check("替卦例2: 三运子午山星8替7顺", ch["shan"]["中"] == 7 and ch["shan_forward"],
          f"实得{ch['shan']['中']},{ch['shan_forward']}")
    check("替卦例2: 三运子午向盘7逆", ch["xiang"]["中"] == 7 and not ch["xiang_forward"],
          f"实得{ch['xiang']['中']},{ch['xiang_forward']}")
    # 七星打劫：八运子山午向=真打劫（离震乾），七运午山子向=假打劫（坎巽兑）
    ch = paipan_xiagua(8, "子", "午")
    check("八运子山午向=真打劫", qixing_dajie(ch, 8, "午") is not None and "真" in qixing_dajie(ch, 8, "午"))
    ch = paipan_xiagua(7, "午", "子")
    check("七运午山子向=假打劫", qixing_dajie(ch, 7, "子") is not None and "假" in qixing_dajie(ch, 7, "子"))

    print("── 审查修复回归 ──")
    info = annual_info(2025)
    check("2025(乙巳)岁破=亥", info["岁破"]["支"] == "亥", f"实得{info['岁破']['支']}")
    check("2025三煞三宫=艮震巽", info["三煞"]["宫"] == ["艮", "震", "巽"], f"实得{info['三煞']['宫']}")
    check("2026岁破=子且太岁在离宫",
          annual_info(2026)["岁破"]["支"] == "子" and annual_info(2026)["太岁"]["宫"] == "离")
    info = ming_gua_full("1920-06-05", "男")
    check("1920-06-05男→艮(民国生人)", info["ming_gua"] == "艮" and info["eff_year"] == 1920,
          f"实得{info['ming_gua']}({info['eff_year']})")
    info = ming_gua_full("1990", "男")
    check("仅年份1990男→坎", info["ming_gua"] == "坎" and "未做立春分界" in info["boundary_note"],
          f"实得{info['ming_gua']}")
    try:
        ming_gua_full("1990-05-21", "x")
        check("非法性别报错", False)
    except ValueError:
        check("非法性别报错", True)
    try:
        ming_gua_full("1990-13-45", "男")
        check("非法日期报错", False)
    except ValueError:
        check("非法日期报错", True)
    check("pos口语归一化", pos_to_palace("正南") == "离" and pos_to_palace("东北方") == "艮"
          and pos_to_palace("北侧") == "坎" and pos_to_palace("南面") == "离",
          f"{pos_to_palace('正南')}/{pos_to_palace('东北方')}/{pos_to_palace('北侧')}")
    hb = {"built_year": 2012, "sitting": "子山午向", "persons": [], "rooms": []}
    r1 = analyze_house(dict(hb, sitting_deg=178))
    r2 = analyze_house(dict(hb, sitting_deg=183))
    r3 = analyze_house(dict(hb, sitting_deg=185))
    r4 = analyze_house(dict(hb, sitting_deg=352.5))
    r5 = analyze_house(dict(hb, sitting_deg=95))
    check("偏差-2°→下卦", r1["sitting"]["排盘方式"].startswith("下卦"), r1["sitting"]["排盘方式"])
    check("偏差+3°→下卦(沈氏4.5°界)", r2["sitting"]["排盘方式"].startswith("下卦"), r2["sitting"]["排盘方式"])
    check("偏差+5°→替卦", r3["sitting"]["排盘方式"].startswith("替卦"), r3["sitting"]["排盘方式"])
    check("偏差-7.5°→骑线警示", any("骑线" in w for w in r4["sitting"]["warnings"]),
          str(r4["sitting"]["warnings"]))
    check("度数与坐向矛盾→忽略度数", r5["sitting"]["度数偏差"] is None
          and any("不符" in w for w in r5["sitting"]["warnings"]))
    # 第二轮审查回归（健壮性）
    r6 = analyze_house(dict(hb, replace="false"))
    check("replace='false'→按false处理", r6["sitting"]["替卦"] is False,
          f"实得{r6['sitting']['替卦']!r}")
    r7 = analyze_house(dict(hb, replace="true"))
    check("replace='true'→强制替卦并提示", r7["sitting"]["替卦"] is True
          and any("强制" in w for w in r7["sitting"]["warnings"]))
    r8 = analyze_house({"built_year": 2012, "sitting": "子山午向",
                        "persons": [{"name": "甲", "birth": "1990-05-21"}], "rooms": []})
    check("缺gender→按男并显著提示", r8["persons"][0].get("warning") == "未提供性别，暂按男命计算，请确认！"
          and r8["persons"][0]["ming_gua"] == "坎")
    r9 = analyze_house({"built_year": 2012, "sitting": "子山午向",
                        "persons": ["垃圾"], "rooms": [{"name": "x"}]})
    check("畸形persons/rooms单条跳过不中止", "error" in r9["persons"][0] and "error" in r9["rooms"][0])
    try:
        ming_gua_full("2023-02-29", "男")
        check("非法日期(2023-02-29)报错", False)
    except ValueError:
        check("非法日期(2023-02-29)报错", True)
    r10 = analyze_house(dict(hb, annual_year="abc"))
    check("annual_year非法→annual.error", "error" in r10["annual"])
    r11 = analyze_house({"period": 8, "sitting": "子山午向", "persons": [], "rooms": []})
    check("手工period渲染不崩且标注8运", "8运" in format_result(r11))

    print("── 排龙诀 ──")
    ch, _ = palong_chart("子")   # 福山堂实例一：子山来龙，午起破军顺行
    check("子山来龙：午破军未右弼申廉贞", ch["午"] == "破军" and ch["未"] == "右弼" and ch["申"] == "廉贞")
    check("子山来龙：亥贪狼子破军辰巨门", ch["亥"] == "贪狼" and ch["子"] == "破军" and ch["辰"] == "巨门")
    ch, _ = palong_chart("壬")   # 实例二：壬山来龙（阳），巳起破军逆行
    check("壬山来龙：巳破军辰右弼卯廉贞", ch["巳"] == "破军" and ch["辰"] == "右弼" and ch["卯"] == "廉贞")
    check("壬山来龙：午禄存丑武曲子贪狼", ch["午"] == "禄存" and ch["丑"] == "武曲" and ch["子"] == "贪狼")
    ch, _ = palong_chart("癸")   # 实例三：七运癸山来龙，午破军/巳右弼/辰廉贞
    check("癸山来龙：午破军巳右弼辰廉贞", ch["午"] == "破军" and ch["巳"] == "右弼" and ch["辰"] == "廉贞")
    allstars = [palong_chart(m)[0][palong_palace_of(m)] for m in ("子", "癸", "壬", "亥", "午", "丁")]
    check("来龙宫必为第7位破军", all(s == "破军" for s in allstars))
    cnt = list(palong_chart("子")[0].values()).count("破军")
    check("破军出现4次", cnt == 4)
    v = palong_verdict(palong_chart("子")[0], "癸")
    check("子龙宅向癸→七凶破军", v["龙星"] == "破军" and v["吉凶"] == "七凶龙")

    print("── 收山出煞诀 ──")
    check("出煞14山/收山10山/不交且并集24",
          len(CHU_SHA_MOUNTAINS) == 14 and len(SHOU_SHAN_MOUNTAINS) == 10
          and not (CHU_SHA_MOUNTAINS & SHOU_SHAN_MOUNTAINS)
          and CHU_SHA_MOUNTAINS | SHOU_SHAN_MOUNTAINS == set("".join(MOUNTAIN_ORDER)))
    check("子午出煞/壬癸? 子出壬收巳收",
          shoushan_chusha("子")["诀"] == "出煞" and shoushan_chusha("壬")["诀"] == "收山"
          and shoushan_chusha("巳")["诀"] == "收山" and shoushan_chusha("丑")["诀"] == "出煞")

    print("── 日课择吉 ──")
    ms = month_star("午", "寅")
    check("午年寅月起八白", ms == 8, f"实得{ms}")
    check("午年申月二黑(逐月递减)", month_star("午", "申") == 2, f"实得{month_star('午', '申')}")
    check("子年寅月八白/寅年寅月二黑/辰年寅月五黄",
          month_star("子", "寅") == 8 and month_star("寅", "寅") == 2 and month_star("辰", "寅") == 5)
    check("时白阳遁：子午卯酉日子1丑2/辰戌丑未日子4卯7/寅申巳亥日子7卯1",
          hour_star("子", 0, False) == 1 and hour_star("子", 2, False) == 2
          and hour_star("辰", 0, False) == 4 and hour_star("辰", 6, False) == 7
          and hour_star("寅", 0, False) == 7 and hour_star("寅", 6, False) == 1,
          f"{hour_star('子',0,False)}/{hour_star('辰',0,False)}/{hour_star('寅',0,False)}")
    check("时白阴遁：子午卯酉日子9寅7/辰戌丑未日子6寅4/寅申巳亥日子3寅1",
          hour_star("子", 0, True) == 9 and hour_star("子", 4, True) == 7
          and hour_star("辰", 0, True) == 6 and hour_star("辰", 4, True) == 4
          and hour_star("寅", 0, True) == 3 and hour_star("寅", 4, True) == 1)
    if HAS_SXTWL:
        s1 = day_star(2024, 12, 26)   # 冬至2024-12-21后首个甲子
        check("日白：2024-12-26一白(冬至后首甲子)", s1[0] == 1 and s1[2] == "冬至", f"实得{s1[0]},{s1[2]}")
        s2 = day_star(2024, 12, 27)
        check("日白：次日二白顺行", s2[0] == 2, f"实得{s2[0]}")
        s3 = day_star(2025, 2, 24)    # 雨水2025-02-18后首个甲子
        check("日白：2025-02-24七赤(雨水后首甲子)", s3[0] == 7 and s3[2] == "雨水", f"实得{s3[0]},{s3[2]}")
        s4 = day_star(2025, 2, 25)
        check("日白：次日八白顺行", s4[0] == 8, f"实得{s4[0]}")
        s5 = day_star(2024, 12, 24)   # 甲子前数日→沿用霜降元
        check("日白：元前空档沿用前元(霜降逆行)", s5[0] is not None and s5[2] == "霜降", f"实得{s5[0]},{s5[2]}")
        r = riche_report(2026, 9, 6, 8)
        check("riche四柱2026-09-06癸未日", r["四柱"]["日"] == "癸未", f"实得{r['四柱']}")
        check("riche建除申月未日=闭", r["建除"]["神"] == "闭", f"实得{r['建除']['神']}")
    check("玄空五行表抽查", XUANKONG_WUXING["甲子"] == ("水", 1) and XUANKONG_WUXING["壬午"] == ("火", 1)
          and XUANKONG_WUXING["癸亥"] == ("水", 6) and XUANKONG_WUXING["乙酉"] == ("金", 4))
    yun1 = sorted(k for k, (w, y) in XUANKONG_WUXING.items() if y == 1)
    check("卦运1恰为八纯卦", yun1 == sorted(XK_CHUN_GUA), str(yun1))
    mirror = all(XUANKONG_WUXING["甲子" + "乙丑丙寅丁卯戊辰己巳庚午辛未壬申癸酉"[i*2:i*2+2]][1]
                 == XUANKONG_WUXING["甲子" + "乙丑丙寅丁卯戊辰己巳庚午辛未壬申癸酉"[i*2:i*2+2]][1] for i in range(0))
    pairs = [("甲子", "甲午"), ("乙丑", "乙未"), ("丙寅", "丙申"), ("丁卯", "丁酉"),
             ("戊辰", "戊戌"), ("己巳", "己亥"), ("庚午", "庚子"), ("辛未", "辛丑"),
             ("壬申", "壬寅"), ("癸酉", "癸卯")]
    check("玄空数理六旬镜像对称", all(XUANKONG_WUXING[a][1] == XUANKONG_WUXING[b][1] for a, b in pairs))
    check("建除月破=破神", jianchu_day("申", "寅")["月破"] is True)
    check("六十甲子表全覆盖", len(XUANKONG_WUXING) == 60)

    print("── 正体五行造命/董公 ──")
    check("纳音60抽查", NAYIN60["甲子"] == "海中金" and NAYIN60["戊午"] == "天上火"
          and NAYIN60["壬戌"] == "大海水" and len(NAYIN60) == 60)
    check("24山正五行抽查", ZHENGTI_WX_24["壬"] == "水" and ZHENGTI_WX_24["乾"] == "金"
          and ZHENGTI_WX_24["巽"] == "木" and ZHENGTI_WX_24["坤"] == "土" and len(ZHENGTI_WX_24) == 24)
    check("天乙贵人表", TIANREN_GUI["甲"] == ("丑", "未") and TIANREN_GUI["辛"] == ("午", "寅"))
    zm = zaoming_analysis("子山午向", {"年": "甲子", "月": "丙子", "日": "庚午", "时": "壬寅"}, [])
    check("造命冲山（子山课见午）", any("午" in c for c in zm["冲山"]), str(zm["冲山"]))
    check("造命扶山统计(生1同3泄2耗2克0)", zm["课八字五行"]["生山"] == 1 and zm["课八字五行"]["同山"] == 3
          and zm["课八字五行"]["克山"] == 0, str(zm["课八字五行"]))
    zm2 = zaoming_analysis("子山午向", {"年": "庚子", "月": "戊子", "日": "甲申", "时": "壬申"}, ["1986"])
    p0 = zm2["相主"][0]
    check("主命1986丙寅+驿马申到课", p0["年柱"] == "丙寅" and p0["纳音"] == "炉中火"
          and "驿马申" in p0["贵人禄马到课"], str(p0)[:140])
    if DONGGONG:
        check("董公12月×12神完整", len(DONGGONG) == 12 and all(len(b["断"]) == 12 for b in DONGGONG.values()))
        check("董公十月建亥断语", "不利起造" in DONGGONG["十月"]["断"]["建"]["断语"])
        check("往亡表正月在寅", DONGGONG_XIONG["往亡日"]["月"].get("正月") == "寅")
        r = riche_report(2026, 9, 10, 9, "子山午向", ["1986"])
        check("riche输出含董公与造命", "董公" in r and "造命" in r)

    print("")
    if errors:
        print(f"❌ {len(errors)} 项失败：{errors}")
        return 1
    print("✅ 全部自检通过")
    return 0


# ═══════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="阳宅风水排盘引擎")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("mingua", help="命卦计算")
    p.add_argument("birth", help="出生日期 YYYY-MM-DD 或 YYYY")
    p.add_argument("gender", help="男/女")
    p.add_argument("--school", default="lichun", choices=["lichun", "solar"])

    p = sub.add_parser("feixing", help="玄空飞星排盘")
    p.add_argument("--period", type=int, required=True, choices=[1, 2, 3, 4, 5, 6, 7, 8, 9])
    p.add_argument("--sitting", required=True, help="坐向，如 '子山午向' / '子'；传纯度数时按坐山度数解释")
    p.add_argument("--facing", type=float, default=None,
                   help="面向屋外实测的朝向度数（=向的度数）。给出时自动判正向/替卦，优先于 --sitting 中的度数")
    p.add_argument("--replace", action="store_true", help="强制替卦")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("dayou", help="大游年八星表")
    p.add_argument("gua", help="命卦或宅卦，如 坎")

    p = sub.add_parser("annual", help="流年紫白盘")
    p.add_argument("year", type=int)

    p = sub.add_parser("pailong", help="排龙诀（中州派）")
    p.add_argument("--long", dest="long_m", help="来龙山（宅中心面向水口时，人端罗盘所压之山）")
    p.add_argument("--shuikou", help="水口方的山（自动取其对山为来龙）")
    p.add_argument("--facing", help="现成宅的向山，用于吉凶判定")
    p.add_argument("--period", type=int, choices=[1, 2, 3, 4, 6, 7, 8, 9], help="当运，用于河图当旺龙判断")

    p = sub.add_parser("riche", help="日课择吉（紫白+建除+董公+正体五行造命，需 sxtwl）")
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    p.add_argument("--hour", type=int, help="24小时制，可选（给出生时柱与时星）")
    p.add_argument("--sitting", help="坐向，可选（收山出煞+正体五行造命扶山/冲山）")
    p.add_argument("--person", action="append", help="主命出生年或 YYYY-MM-DD（可多次），相主+贵人禄马到课")

    p = sub.add_parser("all", help="完整分析")
    p.add_argument("--house", required=True, help="house.json 路径")
    p.add_argument("--json", help="输出 JSON 到文件")

    p = sub.add_parser("selftest", help="自检")
    args = ap.parse_args()

    if args.cmd == "selftest" or args.cmd is None:
        sys.exit(selftest())

    if args.cmd == "mingua":
        info = ming_gua_full(args.birth, args.gender, args.school)
        print(f"出生 {info['birth']} {info['gender']}性")
        print(info["boundary_note"])
        print(f"命卦：{info['ming_gua']}命（{info['class']}）"
              f"{('，' + info['special']) if info['special'] else ''}")
        print(render_dayou(info["dayou"], f"{info['ming_gua']}命大游年"))
        return

    if args.cmd == "feixing":
        zuo, xiang = parse_sitting(args.sitting)
        replace = args.replace
        facing_note = None
        facing_dev = None
        if args.facing is not None:
            xiang_center = mountain_index(xiang) * 15.0
            facing_dev = ((args.facing - xiang_center + 180.0) % 360.0) - 180.0
            if facing_dev != facing_dev or abs(facing_dev) > 7.5:  # 含 NaN 检查
                print(f"❌ 朝向度数 {args.facing} 与向首{xiang}相差超过7.5°（或非法），请核对坐向")
                sys.exit(1)
            if not replace:
                replace = abs(facing_dev) > 4.5
            facing_note = (f"朝向 {args.facing}°（偏离向首{xiang}中心 {facing_dev:+.1f}°，"
                           f"{'正向±4.5°内' if abs(facing_dev) <= 4.5 else '超出4.5°用替卦'}）")
        charts = paipan_tigua(args.period, zuo, xiang) if replace else paipan_xiagua(args.period, zuo, xiang)
        geju, detail = judge_geju(args.period, charts, zuo, xiang)
        flags = special_flags(charts, args.period)
        dajie = qixing_dajie(charts, args.period, xiang)
        if dajie:
            flags.append(dajie)
        out = {"period": args.period, "坐山": zuo, "向山": xiang,
               "替卦": replace, "facing": args.facing, "facing_dev": facing_dev,
               "charts": charts, "格局": geju,
               "格局细节": detail, "特殊": flags, "notes": charts["notes"],
               "城门": chengmen(charts, args.period, xiang),
               "宅卦": zhai_gua_of(zuo)}
        if args.json:
            print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        else:
            if facing_note:
                print(f"  {facing_note}")
            print(render_chart(charts, zuo, xiang,
                               f"{args.period}运 {'替卦' if replace else '下卦'} {zuo}山{xiang}向"))
            for n in charts["notes"]:
                print(f"  · {n}")
            print(f"格局：{geju}")
            for f in flags:
                print(f"  ◆ {f}")
            print(f"旺山星({args.period})在：{'、'.join(detail['旺山星所在']) or '无'}；"
                  f"旺向星在：{'、'.join(detail['旺向星所在']) or '无'}")
            print(f"城门宫：{out['城门']}")
        return

    if args.cmd == "dayou":
        g = args.gua
        if g not in RING:
            print(f"无效卦名: {g}，可选 {'、'.join(RING)}")
            sys.exit(1)
        print(render_dayou(dayou_layout(g), f"{g}卦大游年"))
        return

    if args.cmd == "annual":
        if not 1804 <= args.year <= 2103:
            print("❌ 年份须在 1804-2103 范围内（流年紫白按立春换年）")
            sys.exit(1)
        info = annual_info(args.year)
        ch = {"yun": info["chart"], "shan": info["chart"], "xiang": info["chart"]}
        print(render_chart(ch, "", "", f"{info['year']} {info['gz']}年 流年盘（{STAR_NUM_NAME[info['star']]}入中）"))
        print(f"太岁{info['太岁']['支']}（{info['太岁']['方位']}/{info['太岁']['宫']}宫），"
              f"岁破{info['岁破']['支'] or '—'}（{info['岁破']['方位']}），"
              f"三煞在{info['三煞']['方位']}")
        print(f"五黄到{'、'.join(info['五黄到']) or '中宫'}，二黑到{'、'.join(info['二黑到']) or '中宫'}（宜静不宜动）")
        return

    if args.cmd == "pailong":
        if args.shuikou:
            if args.shuikou not in MOUNTAIN_ORDER:
                print(f"❌ 水口方须为二十四山之一（{args.shuikou} 无效）")
                sys.exit(1)
            long_m = opposite_mountain(args.shuikou)
        elif args.long_m:
            long_m = args.long_m
        else:
            print("❌ 需提供 --long 来龙山 或 --shuikou 水口方的山")
            sys.exit(1)
        chart, direction = palong_chart(long_m)
        print(f"排龙诀（中州派）：来龙{long_m}，{direction}，来龙对宫起破军")
        print("  十二宫龙星（五吉：贪巨武左右辅；七凶：破廉文禄）：")
        for g in PALONG_ORDER:
            star = chart[g]
            tag = "★" if star in PALONG_JI else "✕"
            ms = "/".join(PALONG_PALACES[g])
            print(f"    {g}宫（{ms}）→ {star} {tag}")
        if args.facing:
            if args.facing not in MOUNTAIN_ORDER:
                print(f"❌ 向山无效：{args.facing}")
                sys.exit(1)
            v = palong_verdict(chart, args.facing, args.period)
            print(f"  宅向首{v['向首宫']}宫 → 【{v['龙星']}龙】{v['吉凶']}（五行{v['龙五行']}）")
            print(f"  判定：{v['说明']}")
            print("  提示：吉龙宫内二山可作向首选向，还须配后天星盘与形峦；排龙出卦（如丙巳兼线）此宅不可用")
        return

    if args.cmd == "riche":
        try:
            from datetime import date as _d
            yy, mm, dd = [int(x) for x in args.date.split("-")]
            _d(yy, mm, dd)
        except ValueError as e:
            print(f"❌ 日期无效：{e}")
            sys.exit(1)
        res2 = riche_report(yy, mm, dd, args.hour, args.sitting, args.person)
        if "error" in res2:
            print(f"❌ {res2['error']}")
            sys.exit(1)
        p4 = res2["四柱"]
        print(f"日课：{res2['date']}" + (f" {args.hour}:00" if args.hour is not None else ""))
        print(f"四柱：{p4['年']}年 {p4['月']}月 {p4['日']}日" + (f" {p4['时']}时" if "时" in p4 else ""))
        zb = res2["紫白"]
        print(f"紫白入中：年{zb['年星']}白（{zb['年有效年']}）· 月{zb['月星']}白（{zb['月建支']}月）· "
              f"日{zb['日星']}白（{zb['日季']}）" + (f"· 时{zb['时星']}白" if "时星" in zb else ""))
        jc = res2["建除"]
        print(f"建除：{jc['神']}（{jc['级']}）" + ("　⚠月破日" if res2["月破日"] else ""))
        print(f"{'⚠ 岁破日　' if res2['岁破日'] else ''}{res2['日冲']}　{'⚠ ' + res2['四离四绝'] if res2['四离四绝'] else ''}")
        print(f"彭祖百忌：{'；'.join(res2['彭祖百忌'])}")
        if "董公" in res2:
            dge = res2["董公"]
            print(f"董公择日（{dge['月']}月{dge['神']}日）：{dge['断语']}")
            if dge.get("干支命中句"):
                for h in dge["干支命中句"]:
                    print(f"    → 本日干支命中：{h}")
            if dge.get("月前奏"):
                print(f"    （月令：{dge['月前奏']}）")
        for x in res2.get("凶神日", []):
            print(f"    ⚠ {x}")
        xk = res2.get("玄空五行")
        if xk:
            print(f"玄空五行：日{xk['日']['干支']}属{xk['日']['五行']}（卦运{xk['日']['卦运']}）")
            for k, v in xk["对日辰评估"].items():
                print(f"  {k}柱{v['干支']}（{v['玄空五行']}，运{v['卦运']}）→ {v['关系']}")
        if "造命" in res2:
            zm = res2["造命"]
            if "error" in zm:
                print(f"造命：⚠ {zm['error']}")
            else:
                print(f"正体五行造命：{zm['扶山']}")
                if zm["冲山"]:
                    print(f"  ⚠ 冲山：{'、'.join(zm['冲山'])}")
                for p in zm["相主"]:
                    if "error" in p:
                        print(f"  主命 {p['birth']}：⚠ {p['error']}")
                        continue
                    print(f"  主命{p['birth']} → 年柱{p['年柱']}（{p['纳音']}）"
                          + ("　⚠冲命" if p.get("冲命") else "")
                          + ("；" + "；".join(p["贵人禄马到课"]) if p.get("贵人禄马到课") else "；贵人禄马未到课")
                          + ("；" + "；".join(p["纳音生克"]) if p.get("纳音生克") else ""))
                if zm["格局亮点"]:
                    print("  格局亮点：" + "；".join(zm["格局亮点"]))
        for t in res2["提示"]:
            print(f"  · {t}")
        return

    if args.cmd == "all":
        with open(args.house, encoding="utf-8") as f:
            house = json.load(f)
        res = analyze_house(house)
        if args.json:
            with open(args.json, "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=2, default=str)
            print(f"JSON 已写入 {args.json}")
        print(format_result(res))
        return


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except (ValueError, KeyError, TypeError, AttributeError, FileNotFoundError, OSError) as e:
        print(f"❌ 错误：{e}", file=sys.stderr)
        sys.exit(1)
