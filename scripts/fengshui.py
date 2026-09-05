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
#  渲染
# ═══════════════════════════════════════════════════════════════

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
                         "特殊": flags, "notes": charts["notes"], "城门": cm}
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
    L.append("")
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
