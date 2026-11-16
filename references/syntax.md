# 检索式语法速查与精确直达

> 需要构造检索式或走直达时读本文件。标【未】的**不得**进确定性 SOP。依据标签见 `limits.md` §4。
> 硬规则：先查本文件，避免反复改检索词重发请求。

## ⚠ 两处诚实边界

1. **PubMed 官方字段清单没有 `[DOI]`** → DOI 检索走 `[aid]`/`[lid]`，或直接粘 DOI 让 citation sensor 映射【联】。二手资料里的 `[doi]` 未核实【未】。
2. **万方字段标识符未在官方页核实**（页面只给运算符与中文字段名）→ 不编造 `TI=` 之类【未】。

其余未验证：CNKI 国内版是否支持 `DOI=` / `TKA=`【未】；ScienceDirect 旧版专家检索写法【未】。

## 1. 字段与运算符

| 平台 | 字段 | 运算符与要点 | 依据 |
|---|---|---|---|
| **CNKI 专业检索** | `SU`主题 `TKA`篇关摘 `TI`题名 `KY`关键词 `AB`摘要 `FT`全文 `AU`作者 `FI`第一责任人 `AF`机构 `JN`/`LY`来源 `YE`年 `FU`基金 `CLC`分类号 `CF`被引频次 | `=`精确、`%`模糊、`%=`相关匹配（SU 常用）、`BETWEEN('2010','2018')`、`>`；`AND/OR/NOT` **前后须空格**；`()`；字段内 `*`(与)`+`(或)`-`(非)；`/NEAR N`。例 `SU %= 大数据`、`KY = 知识管理 AND AU = 邱均平` | 【联】 |
| **万方** | 高级检索运算符 | `AND OR NOT`、`""` 整体精确、`()` 子查询、`?` 单字符；优先级 `()>NOT>AND>OR`；「主题」= 题名+关键词+摘要 | 【联】 |
| **维普** | `U`任意 `M`题名或关键词 `T`题名 `K`关键词 `R`摘要 `A`作者 `F`第一作者 `S`机构 `J`刊名 `C`分类号 `SU`主题（**标识符必须大写**） | `AND/and/*`、`OR/or/+`、`NOT/not/-`（前后空格）；优先级 `()>NOT>AND>OR`；半角 `""` | 【联】 |
| **Web of Science** | `TS`主题 `TI`标题 `AB`摘要 `AU`作者 `DO`DOI `SO`出版物 `PY`年 `UT`入藏号 `PMID` `ALL` | `AND/OR/NOT`、`SAME`、`NEAR`、`*` `?` `$`、引号短语、`#1 NOT #2`；`PY=` 须与另一字段组配，跨度 ≤5 年 | 【联】 |
| **PubMed** | `[ti]` `[tiab]` `[au]` `[1au]` `[ta]` `[mh]` `[majr]` `[dp]` `[pt]` `[pmid]` `[aid]` `[lid]` `[tw]` `[la]` `[all]` | 标签放方括号、会关闭自动映射；多词同字段须逐词加标签；`[mh]` 自动扩展下位词；邻近 `"hip pain"[tiab:~2]`；`*` 截词 | 【联】 |
| **arXiv** | `ti:` `au:` `abs:` `co:` `jr:` `cat:` `rn:` `id:` `all:` | `AND`/`OR`/`ANDNOT`；`""` 短语；`?` 单字符、`*` 任意（**不能在首位**）；多人作者 `;` 分隔 | 【联】 |
| **ScienceDirect** | 高级检索**表单字段**：terms / journal title / years / author / affiliation / title-abstract-keywords / title / references / DOI | 布尔**必须全大写**；连字符=NOT；引号=相邻词；优先级 `NOT>AND>OR`；年份四位 | 【联】 |
| **Google Scholar** | 无字段标签 | `"短语"`、`OR`（大写）、`-排除`、`intitle:`、`author:`、`site:`、`filetype:`；**无官方 API，禁自动抓取** | 【联】 |

## 2. 精确直达矩阵（最少请求）

| 目标 | 最短路径 | 依据 |
|---|---|---|
| 任意 DOI → 全文 | **先 `oa_fetch.py fetch --doi <DOI>`**（自动走 OA 候选 + 闸门）；失败再 `https://doi.org/{DOI}` 看落地页 | 【实】 |
| DOI → 元数据核验 | Crossref `https://api.crossref.org/works/{DOI}` | 【联】 |
| DOI → OA 状态 | OpenAlex `https://api.openalex.org/works/https://doi.org/{DOI}` | 【实】 |
| 精确题名 | CNKI 一框式完整题名（实测唯一命中）；WoS `TI=(...)`；PubMed `"题名"[ti]`；维普 `T="题名"` | 【实】/【联】 |
| PMID | `https://pubmed.ncbi.nlm.nih.gov/{PMID}/`；检索 `{PMID}[pmid]` | 【联】 |
| PMCID | `https://pmc.ncbi.nlm.nih.gov/articles/PMC{id}/`（旧 `www.ncbi.nlm.nih.gov/pmc/` 已 301） | 【联·二手】 |
| arXiv ID | 题录 `/abs/{id}`；全文 `/pdf/{id}.pdf`（可交给 `oa_fetch.py fetch --url`）；版本 `vN` | 【实】 |
| WoS 入藏号 | `UT=WOS:000292912900003` | 【联】 |
| CNKI DOI 字段 | `DOI=` 见国际版 LibGuide；国内版是否支持【未】 | 【未】 |

## 3. 使用规则

- **有标识符就别站内检索**；能直达就别翻页。
- 一次收敛（排序/筛选/每页条数一次设好），不反复重发同一检索。
- 同一 (平台, 题名/DOI) 不重复检索；命中已检索清单即跳过。
- 标【未】【联·二手】的语法**先在真实页面试一次**再用，不把推测写进结论。
