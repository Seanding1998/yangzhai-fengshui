# yangzhai-fengshui 阳宅风水分析 Agent Skill

专业阳宅风水分析技能：**房屋是否适合命主、户型布局是否合理**。适用于 ZCode / Codex 等 Agent CLI 的 Skill 机制，开箱即用、完全离线排盘。

> 三元九运定宅运 · 二十四山定坐向 · 玄空飞星三盘（运/山/向）· 兼向替卦 · 八宅命卦与大游年 · 门主灶核查 · 流年飞星叠加 · 外部形煞评估 · 图文 HTML 报告

## 功能特性

| 模块 | 能力 |
|---|---|
| 三元九运 | 按建成年份定 7/8/9 运（1864–2043），跨运争议处理，九运"无旺山旺向"特性 |
| 坐向判定 | 24 山度数对照、磁偏角提示、门向/阳向之争处理、兼向替卦触发（沈氏 ±4.5° 标准）、骑线/空亡警示 |
| 玄空飞星 | 运/山/向三盘自动排布、旺山旺向/上山下水/双星会坐/会向判定、旺衰分析、伏吟反吟/合十/三般卦/七星打劫/城门 |
| 替卦 | 沈氏十三星起星诀，顺逆法则经中州派口诀与无常派实例双重验证 |
| 排龙诀 | 中州派排龙：水口定来龙、十二宫起十二龙星、五吉七凶判定、当运河图权用（经原文三实例逐宫验证） |
| 收山出煞 | 中州派收山出煞诀：出煞十四山宜开扬、收山十山宜收敛，向首/坐山自动判定门厅设计取向 |
| 日课择吉 | 年月日时紫白四盘、十二建除黄黑道、月破/岁破/日冲、彭祖百忌、四离四绝、玄空五行五要件、董公择日144条断语（含月三煞与凶神日比对）、正体五行造命（扶山/冲山/相主纳音/贵人禄马） |
| 八宅 | 命卦（立春精确分界，sxtwl）、东西四命、大游年 8×8 矩阵（程序生成+对称性断言）、门主灶三要 |
| 户型核查 | 缺角/中宫厨厕/穿堂煞/门冲/横梁等结构硬伤清单 + 逐房间落宫判定 |
| 流年 | 流年紫白盘、太岁/岁破/三煞（三宫扇区）、五黄二黑方位、与宅盘叠加 |
| 信息采集 | 结构化问诊单（从报告结论反推字段，含九宫格填空与降级路径）+ `validate-input` 录入校验（硬伤/降级清单，条目号映射回问诊单） |
| 立极测量 | 两步读数分工（定向/落宫）、三层太极、缺角与 L 形户型割补立极、测量干扰规避（≥3 独立来源考据） |
| 图纸解读 | 户型图/照片标准流程：图向优先级链、尺寸抽取量化缺角、读图结论四分法（事实/视觉/推断/缺失）、质检清单、坐向不明拒绝臆造 |
| 报告 | JSON → 校验 → 自包含 HTML 图文报告（九宫图、命卦卡、房间逐评、结论分级） |

## 安装

### ZCode

```bash
# 克隆到个人技能目录（Windows: %USERPROFILE%\.zcode\skills）
git clone https://github.com/Seanding1998/yangzhai-fengshui.git ~/.zcode/skills/yangzhai-fengshui
```

重启会话后，提到"看风水 / 坐向朝向 / 命卦 / 九宫飞星 / 房子适不适合我"等即可自动触发。

### Codex / 其他支持 Skill 机制的 CLI

克隆到对应 skills 目录即可（如 `~/.codex/skills/`）。

### 可选依赖

```bash
pip install sxtwl   # 命卦立春精确分界、干支计算；未安装时自动回退纯 Python 近似（立春按 2 月 4 日）
```

排盘引擎本体为纯 Python 标准库实现，无其他依赖。

## 快速上手（CLI）

```bash
# 命卦（八宅，立春分界）
python scripts/fengshui.py mingua 1990-05-21 女

# 玄空飞星排盘（下卦）
python scripts/fengshui.py feixing --period 8 --sitting "子山午向"

# 面向屋外实测的朝向度数（自动判正向/替卦）
python scripts/fengshui.py feixing --period 9 --sitting "午山子向" --facing 355

# 大游年八星方位表
python scripts/fengshui.py dayou 坎

# 流年紫白盘 + 太岁/岁破/三煞
python scripts/fengshui.py annual 2026

# 排龙诀（中州派，水口定来龙）
python scripts/fengshui.py pailong --shuikou 午 --facing 癸 --period 9

# 日课择吉（紫白四盘 + 建除 + 董公断语 + 正体五行造命，需 sxtwl）
python scripts/fengshui.py riche --date 2026-10-01 --hour 9 --sitting "子山午向" --person 1990-05-21

# 一键完整分析（读 house.json）
python scripts/fengshui.py validate-input examples/case1-house.json   # 先校验录入信息
python scripts/fengshui.py all --house examples/case1-house.json --json out.json

# 生成 HTML 报告
python scripts/generate_report.py --input out.json --output 风水报告.html --validate

# 内置自检（122 项测试向量）
python scripts/fengshui.py selftest
```

`house.json` 结构（完整说明见 SKILL.md 第五节，空模板见 `templates/house-input.json`）：

```json
{
  "house": { "built_year": 2012, "sitting": "子山午向", "sitting_deg": 178, "annual_year": 2026 },
  "persons": [ { "name": "命主", "birth": "1990-05-21", "gender": "女" } ],
  "rooms": [ { "name": "大门", "pos": "南" }, { "name": "主卧", "pos": "西北" } ],
  "external": ["南面为小区花园，开阔"]
}
```

## 信息采集：问诊单

AI 没有眼睛，房屋信息全靠用户输入，而口语描述（"朝南""缺个角"）结构化程度低、易有歧义。
本 skill 反向设计了一份[问诊单](templates/intake-form.md)：**从分析报告需要的每个结论反推出必填字段**
（每项标注"→ 决定报告里的什么"，并给"不知道怎么办"的降级路径，含九宫格填空表）。
Agent 会把已从描述中提取的项**预填**进问诊单回显请用户确认，用户补空后解析为 `house.json`，
先跑 `validate-input` 校验——❌ 硬伤（缺定运/坐向无效/方位无法识别/字段放错层级/`person` 笔误等）
逐条列出处方并映射回问诊单条目号①–⑧定向追问，⚠ 降级项（只给年份/缺性别/无度数等）声明后可继续。

## 示例报告

`examples/` 内含两个完整案例（排盘输入 → 分析数据 → HTML 报告），可直接用浏览器打开 `*-report.html` 查看：

- **案例一**：八运子山午向（双星会向）+ 1990 年女命（西四命住东四宅的补救分析）
- **案例二**：九运午山子向兼向替卦 + 2024 年男命与 1996 年女命双人合参（反吟、假打劫、天斩煞叠加流年五黄）

## 算法可靠性

- 排盘算法不靠手抄表格：大游年矩阵由歌诀+环序程序生成并断言 28 对关系对称；命卦用跨世纪统一公式（已修正常见的"2000 年后出生错一档"问题）。
- 关键盘面与出版资料交叉核对：七运/八运旺山旺向与上山下水各六局逐山吻合；九运 24 山全为双星局（印证《青囊奥语》"一、九两运无当旺之山向"）；替卦实例与中州派/无常派两系一致；五运十二局旺山旺向。
- 两轮独立审查（领域正确性 + 约 180 次对抗性输入测试）后发布，修复记录见 [CHANGELOG.md](CHANGELOG.md)。

## 项目结构

```
yangzhai-fengshui/
├── SKILL.md                  # Agent 主流程（问诊单采集 → 七步分析 → 报告）
├── references/               # 领域参考文档（按需加载）
├── templates/
│   ├── intake-form.md        # 结构化问诊单（贴给用户填，含九宫格与降级路径）
│   └── house-input.json      # house.json 空模板
├── scripts/
│   ├── fengshui.py           # 排盘引擎（纯 Python，sxtwl 可选）
│   ├── generate_report.py    # HTML 报告生成器（内置校验）
│   └── donggong_data.json    # 董公择日数据
└── examples/                 # 两个完整案例
```

## 免责声明

风水学属中国传统民俗文化，流派众多、结论各异。本项目仅供**传统文化研究与娱乐参考**，不构成任何置业、装修、医疗或其他人生决策依据。报告中所有化解建议均标注"民俗传统做法，供参考"。

## License

[个人免费·商业授权许可证](LICENSE) —— 个人学习研究免费使用，商业使用需联系作者授权。
