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
| 八宅 | 命卦（立春精确分界，sxtwl）、东西四命、大游年 8×8 矩阵（程序生成+对称性断言）、门主灶三要 |
| 户型核查 | 缺角/中宫厨厕/穿堂煞/门冲/横梁等结构硬伤清单 + 逐房间落宫判定 |
| 流年 | 流年紫白盘、太岁/岁破/三煞（三宫扇区）、五黄二黑方位、与宅盘叠加 |
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

# 一键完整分析（读 house.json）
python scripts/fengshui.py all --house examples/case1-house.json --json out.json

# 生成 HTML 报告
python scripts/generate_report.py --input out.json --output 风水报告.html --validate

# 内置自检（77 项测试向量）
python scripts/fengshui.py selftest
```

`house.json` 结构（完整说明见 SKILL.md 第五节）：

```json
{
  "house": { "built_year": 2012, "sitting": "子山午向", "sitting_deg": 178, "annual_year": 2026 },
  "persons": [ { "name": "命主", "birth": "1990-05-21", "gender": "女" } ],
  "rooms": [ { "name": "大门", "pos": "南" }, { "name": "主卧", "pos": "西北" } ],
  "external": ["南面为小区花园，开阔"]
}
```

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
├── SKILL.md                  # Agent 主流程（信息采集 → 七步分析 → 报告）
├── references/               # 7 篇领域参考文档（按需加载）
├── scripts/
│   ├── fengshui.py           # 排盘引擎（纯 Python，sxtwl 可选）
│   └── generate_report.py    # HTML 报告生成器（内置校验）
└── examples/                 # 两个完整案例
```

## 免责声明

风水学属中国传统民俗文化，流派众多、结论各异。本项目仅供**传统文化研究与娱乐参考**，不构成任何置业、装修、医疗或其他人生决策依据。报告中所有化解建议均标注"民俗传统做法，供参考"。

## License

[个人免费·商业授权许可证](LICENSE) —— 个人学习研究免费使用，商业使用需联系作者授权。
