---
name: yangzhai-fengshui
description: 专业阳宅风水分析：房屋是否适合命主、户型布局是否合理。涵盖三元九运定宅运、二十四山定坐向、玄空飞星三盘（运/山/向）、替卦排盘、八宅大游年命卦与东西四宅、门主灶核查、流年飞星叠加、外部形煞评估，并生成图文 HTML 报告。当用户提到风水、看房、买房选房、房屋坐向朝向、八宅、命卦、东四命西四命、九宫飞星、玄空飞星、宅运盘、三元九运、户型风水、房子是否适合我、搬家看宅，或给出户型图/坐向度数/出生年份性别要求分析住宅时使用——即使用户没有明确说"风水"二字。
---

# 阳宅风水分析（yangzhai-fengshui）

## 〇、铁律（先读）

1. **一切排盘必须调用 `scripts/fengshui.py`**（相对本 skill 目录）。禁止手推飞星盘、禁止凭记忆报命卦/星盘数字。脚本内置 selftest 与已验证算法，手推出错概率极高。
2. 每完成一步，先向用户回读关键盘面（坐向、运、格局、命卦），确认无误再进入下一步。
3. 涉及流派差异（立春/公历分界、门向/阳向、兼向分界等）时**两说并存**，标注差异，不强行统一。
4. 所有吉凶结论必须给出依据（星、方位、规则条款）；化解建议注明"民俗传统做法，供参考"。
5. 结束时附一句免责声明：本分析属传统民俗文化研究，仅供参考娱乐，不构成任何人生、医疗、投资决策依据。
6. 排盘命令的运行方式：`python <本skill目录>/scripts/fengshui.py <子命令>`（Windows 下若 `python` 不可用改用 `py`）。

## 一、输出分流（先分流，再动手）

| 模式 | 触发 | 输出 |
|---|---|---|
| **完整分析** | 给出/可补全房屋+命主信息，要求整体分析 | 第 2–7 步全流程 + 综合报告（可选 HTML） |
| **单点问答** | 只问一件事（如"我是东四命吗""2026 年五黄在哪"） | 直接调脚本算该项 → 结论+依据，三五行 |
| **排盘确认** | 只要求排盘（飞星盘/命卦/流年盘） | 盘面+格局标注，问是否继续深入 |
| **信息不足** | 关键信息缺失 | 贴问诊单（可裁剪）或按第二节清单提出**最少必要**的问题（一次问全，≤6 问） |

## 二、信息采集：问诊单模式（AI 无眼睛，靠结构化输入弥补）

口语描述结构化程度低（一句"朝南"至少有三种坐向解释），AI 从中提取还会叠加理解偏差且无法自证。
因此完整分析的采集一律走**问诊单**（`templates/intake-form.md`），它是逆向设计的：
从报告所需的**每个结论**反推**必填字段**（每字段标注"→ 决定报告里的什么"），并给每项"不知道怎么办"的降级路径。

| 用户给到的素材 | 你的动作 |
|---|---|
| 零散描述 / 户型图 / 房屋信息基本空白 | 把问诊单（按需裁剪：单点问答只贴相关条）贴给用户；**已从描述中提取的项先预填好**，回显请用户确认+补空 |
| 用户自己已写好 house.json | 直接跑 `validate-input` 校验后进入分析 |
| 用户只问单点问题 | 不发问诊单，按输出分流直接答 |

拿到回传后的固定流程：
1. 将填写内容解析为 `house.json`（schema 见 `templates/house-input.json` 与第五节）。
2. `python scripts/fengshui.py validate-input house.json` —— ❌ 硬伤**逐条定向追问**（输出已映射问诊单条目号①–⑧），补齐后重跑；⚠ 降级项向用户口头声明即可继续。
3. 校验通过（exit 0）→ 写入文件后用 `all --house house.json` 进入第 3 步起的流程。

铁律：
- **AI 预填进问诊单的内容必须回显请用户确认**（弥补无眼睛的补偿机制：人是校验者，AI 是填写者）。
- 用户"不知道"的项走问诊单里的降级路径并在报告中声明 ⚠，**不得静默猜测**——猜错一个度数比缺一个度数糟。
- 信息不全但能先排的（如只有年份性别 → 先出命卦表），照常先给，同时用问诊单追问其余。

## 三、完整分析流程（七步）

### 第 1 步 · 定运
读 `references/sanyuan-jiuyun.md`。由建成年份定 7/8/9 运；建成与入住跨运、改建等情况按该文档规则处理并在报告中说明。

### 第 2 步 · 定坐向
读 `references/zuoxiang-24shan.md`。度数 → 24 山（注意磁偏角与"坐"与"向"的方向差）；判断正向/兼向/替卦/空亡。脚本会自动判定并给出替卦盘。

### 第 3 步 · 玄空飞星排盘与格局
```bash
python scripts/fengshui.py feixing --period <运> --sitting "<坐山>山<向山>向"
```
⚠ 度数口径：`--sitting` 传纯度数时按**坐山度数**解释；若手头是"面向屋外实测的朝向度数"（更常见），请用 `--facing <度数>`，脚本会自动判正向/替卦。也可加 `--replace` 强制替卦、`--json` 输出结构化结果。
读 `references/xuankong-feixing.md` 解读：格局（旺山旺向/上山下水/双星会坐/会向）→ 旺衰 → 逐宫山向星组合 → 特殊格局（伏吟/反吟/合十/三般卦/打劫/城门）。脚本同时输出**收山出煞**判定（向首/坐山宜开扬或收敛，见 references/pailong-shoushan.md），纳入大门与门厅设计建议。九运房注意：下卦无旺山旺向与上山下水，全为双星局，属正常而非排盘错误。

### 第 4 步 · 八宅命卦与宅命相配
```bash
python scripts/fengshui.py mingua <YYYY-MM-DD> <男/女>
python scripts/fengshui.py dayou <卦名>        # 直接查某卦（宅卦或命卦）的八星方位表
```
读 `references/bazhai-dayou.md`。每位命主：命卦、东西四命、八星方位表；与宅卦相配与否；门主灶初步吉凶。

### 第 5 步 · 户型布局核查
读 `references/layout-checklist.md`。把各房间归宫后：结构硬伤（缺角/中宫厨厕/穿堂/门冲/横梁…）→ 八宅门主灶 → 玄空逐宫取用。一键命令（先按第二节解析 house.json 并校验）：
```bash
python scripts/fengshui.py validate-input house.json   # ❌ 须补齐 / ⚠ 降级声明
python scripts/fengshui.py all --house house.json [--json out.json]
```

### 第 6 步 · 流年叠加
```bash
python scripts/fengshui.py annual <年份>
```
读 `references/liunian-feixing.md`。列当年五黄/二黑/三煞/岁破/文昌/财气方，映射到用户家中具体房间，并说明与宅盘的引动关系。

### 第 7 步 · 外部形煞与排龙（有描述/水口信息才做）
读 `references/waixing-shasha.md`。按强度分级评估形煞，落宫引动，给出"挡避优先"的建议。
若用户提供**水口**信息（最近的十字/丁字路口方位），加排排龙诀（中州派，读 `references/pailong-shoushan.md`）：
```bash
python scripts/fengshui.py pailong --shuikou <水口方的山> --facing <向山> --period <运>
```
水口方的山（如南面路口取"午"），脚本自动取对山为来龙、排十二宫龙星、按宅向首判五吉/七凶（含当运河图权用）。`all` 命令亦接受 house.json 的 `"shuikou": "午"` 字段自动排龙。现代高楼难定真水口时，如实告知勿强断。

### 第 8 步 · 日课择吉（用户需要选日子时做）
读 `references/rique-zhai.md`。用于入宅搬家、动土装修、开业安床等：
```bash
python scripts/fengshui.py riche --date 2026-10-01 --hour 9 --sitting "子山午向" --person 1990-05-21 --person 1988
```
输出四柱、年月日时紫白四盘、十二建除黄黑道、月破/岁破/日冲生肖、彭祖百忌、四离四绝、玄空五行五要件、**董公择日断语（含月三煞方位与凶神日比对）**、**正体五行造命（扶山/冲山/相主纳音/贵人禄马到课）**（需 sxtwl）。硬规则：避月破、岁破、四离四绝、冲宅主年支、**冲坐山**、董公断语凶；入宅喜成/定/开日。多个候选日时逐日跑 `riche` 对比后给推荐排序。

### 综合报告（完整分析模式的收尾）

结构：
1. **宅运概况**：运、坐向（含偏差/替卦声明）、宅卦。
2. **玄空盘**：贴脚本九宫图 + 格局结论 + 旺衰要点。
3. **命卦与宅配**：每位命主命卦表 + 宅命相配结论。
4. **门主灶与房间逐评**：房间 × 判定（✅合理 / ⚠可优化 / ❌硬伤）+ 依据。
5. **流年提醒**：当年凶方吉方落到具体房间。
6. **形煞评估**（如有）。
7. **综合结论**：房子是否适合命主，用三档（适合 / 有条件适合（列条件与调整项） / 须谨慎（列硬伤））+ 可执行调整清单（按成本排序：摆放 ≤ 家具移位 ≤ 装修改造）。
8. 免责声明。

需要交付文件时，生成 HTML 报告（见第四节）。

## 四、HTML 报告

```bash
python scripts/generate_report.py --input data.json --output 风水报告.html --validate
```
- `data.json`：第 3–6 步的脚本 JSON 输出（`fengshui.py all --json` 或各子命令 `--json`）合并进一个对象（schema 见 scripts/generate_report.py 头注释与 --validate 提示）。
- 结论文字由你写好放进 `data.json` 的 `sections` 字段，脚本负责渲染九宫图、表格与样式；`result.external` 会自动渲染为"外部环境"清单。
- 生成前脚本会**自动校验**：`result.error` 存在（排盘失败）、缺字段、verdict 非法、summary 不足 30 字、persons 为空等会**直接拒绝生成**；sections 含脚本标签、命主缺性别、流年数据异常等会给出 ⚠ 警告。`--validate` 可单独跑校验。
- 生成的 HTML 请快速抽查：九宫图数字与脚本输出一致、房间表完整、无占位文本，再交付给用户。

## 五、house.json 示例（`all` 命令输入；空模板见 templates/house-input.json）

```json
{
  "house": {
    "built_year": 2012,
    "sitting": "子山午向",
    "sitting_deg": 178,
    "annual_year": 2026,
    "replace": false,
    "shuikou": "午"
  },
  "persons": [
    {"name": "命主", "birth": "1990-05-21", "gender": "女", "school": "lichun"}
  ],
  "rooms": [
    {"name": "大门", "pos": "南"},
    {"name": "主卧", "pos": "西北"},
    {"name": "厨房", "pos": "东"},
    {"name": "卫生间", "pos": "西"},
    {"name": "阳台", "pos": "南"}
  ],
  "external": ["北侧有道路直冲"]
}
```
- `sitting`：坐向描述或坐山名；`sitting_deg` 为**面向屋外实测的度数**（默认按朝向/向的度数解释，若更接近坐山则自动按坐山解释并提示；与声明坐向明显不符时忽略度数并警示），给出时自动判兼向/替卦（沈氏标准：正向 ±4.5°）。
- `replace`：`true` 强制按替卦排盘（默认按偏差自动判定）。
- `shuikou`：水口方的山（如南面路口取"午"），提供时自动排中州派排龙诀并按宅向首判吉凶。
- `pos`：方位名（南/东南/正南/东北方…）、宫名（离/巽…）或度数皆可。
- `persons[].school`：`lichun`（默认，立春分界）/ `solar`（公历年）。仅给年份时（如 `"birth": "1990"`）不做立春分界，报告中会提示。
- `external`：外部环境描述，原样回显到结果 JSON（供形煞评估节引用）。
- `annual_year`：流年盘年份。注意流年以立春换年——分析 2026 年 1 月的房屋应查 2025（乙巳）年盘。

## 六、参考文档索引（按需读取，勿全量加载）

| 文档 | 何时读 |
|---|---|
| references/sanyuan-jiuyun.md | 第 1 步定运；跨运争议 |
| references/zuoxiang-24shan.md | 第 2 步定坐向；兼向替卦边界 |
| references/xuankong-feixing.md | 第 3 步读盘；组合断诀 |
| references/bazhai-dayou.md | 第 4 步命卦/宅卦/门主灶 |
| references/layout-checklist.md | 第 5 步户型核查 |
| references/waixing-shasha.md | 第 7 步外部环境 |
| references/pailong-shoushan.md | 第 7 步排龙诀；第 3 步收山出煞 |
| references/rique-zhai.md | 第 8 步日课择吉 |
| references/liunian-feixing.md | 第 6 步流年叠加 |

脚本自检：`python scripts/fengshui.py selftest`（改动脚本后必跑，应全部 ✅）。

输入模板：`templates/intake-form.md`（问诊单，贴给用户填）· `templates/house-input.json`（house.json 空模板）。
