# -*- coding: utf-8 -*-
"""存储模块：Excel 读写 + 增量更新合并。

增量更新逻辑（按宣讲会 id 去重）：
- 历史记录中举办日期已过去且本次未抓到 → 状态标记为「已结束」保留
- 本次抓到的记录 → 若已存在则更新字段（状态「更新」），否则新增（状态「新增」）
"""
import datetime as dt
import os
from typing import List, Tuple

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

import config
from crawler import TeachinRecord
from classifier import classify_teachin, classify_job, detect_opportunity, recommend

MAIN_SHEET = "宣讲会明细"
JOB_SHEET = "岗位明细"
SUMMARY_SHEET = "分类汇总"
RECOMMEND_SHEET = "推荐清单"
NOTE_SHEET = "说明"

HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
THIN = Side(style="thin", color="D9D9D9")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)


# ---------------------------------------------------------------- 数据准备
def build_rows(records: List[TeachinRecord],
               profile: dict = None) -> Tuple[List[dict], List[dict]]:
    """把记录展开成 明细行 + 岗位行。

    profile 为 resume_parser.parse_resume 的画像；None 时推荐走
    USER_MAJORS 专业规则。
    """
    main_rows, job_rows = [], []
    for rec in records:
        detect_opportunity(rec)          # 先识别笔试/面试机会
        category = classify_teachin(rec)
        opp, reason, hits = recommend(rec, profile)
        hit_col = "、".join(f"{t}:{v}" for t, v in hits)
        main_rows.append({
            "宣讲会id": rec.id,
            "公司/单位": rec.company,
            "宣讲会名称": rec.title,
            "举办日期": rec.date,
            "举办时间": rec.time_text,
            "举办地点": rec.location,
            "单位行业": rec.industry,
            "单位性质": rec.company_nature,
            "单位规模": rec.company_scale,
            "岗位类别(主)": category,
            "是否有笔试": "是" if rec.has_written_test else "否",
            "是否有面试": "是" if rec.has_interview else "否",
            "笔试面试机会": rec.opp_level,
            "判断依据": rec.opp_evidence,
            "推荐度": opp,
            "推荐理由": reason,
            "简历命中": hit_col,
            "职位数": len(rec.jobs),
            "详情页": rec.detail_url,
            "宣讲内容摘要": rec.detail_body[:200] if rec.detail_body else "",
            "状态": rec.status,
        })
        for j in rec.jobs:
            job_rows.append({
                "宣讲会id": rec.id,
                "公司/单位": rec.company,
                "宣讲会名称": rec.title,
                "举办日期": rec.date,
                "岗位类别": classify_job(j["job_name"]),
                "职位名称": j["job_name"],
                "薪资": j["salary"],
                "工作城市": j["city"],
                "工作性质": j["nature"],
                "学历要求": j["degree"],
                "需求专业": j["majors"],
                "操作状态": j["operation"],
            })
    return main_rows, job_rows


# ---------------------------------------------------------------- 增量合并
def merge_incremental(existing: pd.DataFrame,
                      new_rows: List[dict]) -> Tuple[List[dict], dict]:
    """合并旧表与新抓数据，返回 (合并后明细行, 增量统计)"""
    stats = {"新增": 0, "更新": 0, "已结束": 0, "未变化": 0}
    today = dt.date.today().isoformat()
    merged: dict = {}

    # 旧数据
    if existing is not None and not existing.empty:
        for _, r in existing.iterrows():
            merged[str(r["宣讲会id"])] = dict(r)

    # 新数据
    for row in new_rows:
        rid = str(row["宣讲会id"])
        if rid in merged:
            old = merged[rid]
            # 判断是否有实质变化
            changed = any(str(old.get(k) or "") != str(row.get(k) or "")
                          for k in ["举办时间", "举办地点", "单位行业",
                                    "笔试面试机会", "推荐度"])
            merged[rid] = row
            stats["更新" if changed else "未变化"] += 1
        else:
            merged[rid] = row
            stats["新增"] += 1

    # 结束判定：旧数据里举办日期已过去、本次不在新数据中
    new_ids = {str(r["宣讲会id"]) for r in new_rows}
    for rid, row in merged.items():
        if rid not in new_ids:
            d = row.get("举办日期") or ""
            if isinstance(d, str) and d and d < today:
                row["状态"] = "已结束"
                stats["已结束"] += 1

    rows = list(merged.values())
    rows.sort(key=lambda r: (r.get("举办日期") or "", r.get("宣讲会id") or ""))
    return rows, stats


# ---------------------------------------------------------------- Excel 写入
def _style_sheet(ws, widths: dict, freeze: str = "A2"):
    for col, w in widths.items():
        ws.column_dimensions[col].width = w
    for cell in ws[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER
        cell.border = BORDER
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = LEFT if cell.column_letter not in ("A",) else CENTER
            cell.border = BORDER
    ws.freeze_panes = freeze
    ws.auto_filter.ref = ws.dimensions


def write_excel(path: str, main_rows: List[dict], job_rows: List[dict],
                crawl_time: str, horizon_days: int, stats: dict = None):
    """生成最终 Excel（多 sheet）"""
    wb = Workbook()
    # 1. 宣讲会明细
    ws = wb.active
    ws.title = MAIN_SHEET
    df = pd.DataFrame(main_rows)
    ws.append(list(df.columns))
    for _, r in df.iterrows():
        ws.append(["" if pd.isna(v) else v for v in r.tolist()])
    widths = {"A": 10, "B": 24, "C": 44, "D": 12, "E": 20, "F": 22, "G": 24,
              "H": 18, "I": 12, "J": 12, "K": 10, "L": 10, "M": 14, "N": 40,
              "O": 8, "P": 30, "Q": 30, "R": 8, "S": 34, "T": 45, "U": 8}
    _style_sheet(ws, widths)

    # 2. 岗位明细
    ws2 = wb.create_sheet(JOB_SHEET)
    df2 = pd.DataFrame(job_rows)
    ws2.append(list(df2.columns))
    for _, r in df2.iterrows():
        ws2.append(["" if pd.isna(v) else v for v in r.tolist()])
    _style_sheet(ws2, {"A": 10, "B": 22, "C": 40, "D": 12, "E": 12, "F": 26,
                       "G": 14, "H": 16, "I": 12, "J": 12, "K": 40, "L": 10})

    # 3. 分类汇总
    ws3 = wb.create_sheet(SUMMARY_SHEET)
    ws3.append(["岗位类别", "宣讲会场次", "职位数", "涉及公司数",
                "代表公司(前8)", "有笔试机会场次", "有面试机会场次",
                "高推荐场次", "中推荐场次"])
    dfm = pd.DataFrame(main_rows)
    if not dfm.empty:
        for cat, g in dfm.groupby("岗位类别(主)"):
            comps = g["公司/单位"].dropna().unique()[:8]
            ws3.append([
                cat, len(g), int(g["职位数"].sum()),
                g["公司/单位"].nunique(),
                "、".join(str(c) for c in comps),
                int((g["是否有笔试"] == "是").sum()),
                int((g["是否有面试"] == "是").sum()),
                int((g["推荐度"] == "高").sum()),
                int((g["推荐度"] == "中").sum()),
            ])
    ws3.append([])
    ws3.append(["合计", len(dfm), int(dfm["职位数"].sum()) if not dfm.empty else 0,
                dfm["公司/单位"].nunique() if not dfm.empty else 0])
    _style_sheet(ws3, {"A": 16, "B": 12, "C": 10, "D": 12, "E": 60, "F": 14,
                       "G": 14, "H": 12, "I": 12})

    # 4. 推荐清单（高/中推荐度优先）
    ws4 = wb.create_sheet(RECOMMEND_SHEET)
    ws4.append(["推荐度", "举办日期", "公司/单位", "宣讲会名称", "举办时间",
                "举办地点", "岗位类别(主)", "笔试面试机会", "推荐理由", "详情页"])
    if not dfm.empty:
        rec_df = dfm[dfm["推荐度"].isin(["高", "中"])].copy()
        rec_df = rec_df.sort_values(["推荐度", "举办日期"], ascending=[True, True])
        for _, r in rec_df.iterrows():
            ws4.append([r["推荐度"], r["举办日期"], r["公司/单位"], r["宣讲会名称"],
                        r["举办时间"], r["举办地点"], r["岗位类别(主)"],
                        r["笔试面试机会"], r["推荐理由"], r["详情页"]])
    _style_sheet(ws4, {"A": 8, "B": 12, "C": 24, "D": 44, "E": 20, "F": 22,
                       "G": 12, "H": 14, "I": 30, "J": 34})

    # 5. 说明
    ws5 = wb.create_sheet(NOTE_SHEET)
    notes = [
        ["招聘信息整理助手 · 数据说明", ""],
        ["数据来源", "西安电子科技大学就业信息网 job.xidian.edu.cn（线下宣讲会栏目）"],
        ["抓取时间", crawl_time],
        ["抓取范围", f"未来 {horizon_days} 天内的线下宣讲会（列表按举办时间升序）"],
        ["更新方式", "增量更新：按宣讲会id去重，新场次标「新增」，变更场次标「更新」，"
                      "历史已结束场次标「已结束」保留"],
        ["岗位类别", "按职位名称关键词规则归类（算法/AI、数据、芯片/硬件、软件开发、"
                      "通信/网络、产品/设计、运营/市场/销售、职能/管理、制造/供应链、其他）"],
        ["笔试面试机会", "根据宣讲会标题与宣讲详情正文关键词识别：现场笔试/面试、宣讲后安排、"
                          "仅投递/简历筛选、未提及；「判断依据」列保留原文便于人工复核"],
        ["推荐度", "规则：机会等级 × 简历画像匹配（专业/技能/意向岗位命中点见「简历命中」列）；"
                      "未配置简历时回退 config.py USER_MAJORS 专业规则；简历解析为本地规则，不调用大模型"],
        ["注意事项", "① 详情页正文由站点 JS 压缩内嵌，本工具按浏览器同等逻辑还原；"
                      "② 联系电话/邮箱为站点登录后可见，爬取显示掩码；"
                      "③ 部分单位详情正文为空或更新滞后，请以宣讲现场为准；"
                      "④ 本工具仅作信息整理，请遵守站点使用条款，控制抓取频率。"],
    ]
    for row in notes:
        ws5.append(row)
    ws5.column_dimensions["A"].width = 18
    ws5.column_dimensions["B"].width = 120
    for cell in ws5["A"]:
        cell.font = Font(bold=True)
    for row in ws5.iter_rows(min_row=2):
        row[1].alignment = LEFT

    os.makedirs(os.path.dirname(path), exist_ok=True)
    wb.save(path)
    return path


# ---------------------------------------------------------------- 读取旧表
def load_existing(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return None
    try:
        return pd.read_excel(path, sheet_name=MAIN_SHEET, dtype={"宣讲会id": str})
    except Exception:
        return None
