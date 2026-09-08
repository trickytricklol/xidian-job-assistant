# -*- coding: utf-8 -*-
"""招聘信息整理助手 · 命令行入口

用法示例：
  python main.py                          # 抓未来14天线下宣讲并增量更新Excel
  python main.py --horizon 30             # 抓未来30天
  python main.py --output ./my.xlsx       # 指定输出文件
"""
import argparse
import datetime as dt
import json
import os
import sys

import config
from crawler import crawl_offline_teachins
from resume_parser import parse_resume, describe
from storage import (load_existing, merge_incremental, build_rows,
                     write_excel, MAIN_SHEET)


def log(msg: str):
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="西电就业网·线下宣讲会信息整理助手")
    parser.add_argument("--horizon", type=int, default=config.DEFAULT_HORIZON_DAYS,
                        help="抓取未来N天内的线下宣讲会")
    parser.add_argument("--output", default=None, help="输出Excel路径")
    parser.add_argument("--dump-json", default=None,
                        help="同时输出原始数据JSON（便于二次分析）")
    parser.add_argument("--from-json", default=None,
                        help="跳过抓取，直接从上次导出的JSON重建Excel（配合--dump-json使用）")
    parser.add_argument("--resume", default=config.RESUME_PATH,
                        help="简历文件路径（PDF/TXT/MD），用于简历驱动推荐；"
                             "不传则用默认路径 resume/resume.pdf")
    args = parser.parse_args()

    # 0. 简历画像
    profile = parse_resume(args.resume)
    if profile:
        log(f"简历画像：{describe(profile)}")
    else:
        log("未解析到简历（或路径不存在），推荐回退 USER_MAJORS 专业规则")

    out_path = args.output or os.path.join(config.OUTPUT_DIR, config.EXCEL_FILENAME)

    # 1. 抓取（或从缓存JSON重建）
    if args.from_json:
        log(f"从缓存JSON读取：{args.from_json}")
        with open(args.from_json, encoding="utf-8") as f:
            data = json.load(f)
        from crawler import TeachinRecord
        records = [TeachinRecord(**{k: (v if k != "jobs" else [dict(j) for j in v])
                                    for k, v in r.items()}) for r in data["records"]]
        log(f"读取 {len(records)} 场宣讲记录")
    else:
        log(f"开始抓取未来 {args.horizon} 天内的线下宣讲会 ...")

        def _progress(page, n):
            if page > 0:
                log(f"  列表第{page}页完成，累计 {n} 场")
            else:
                log(f"  详情已抓取 {n} 场")

        records = crawl_offline_teachins(horizon_days=args.horizon,
                                         progress=_progress)
        log(f"列表抓取完成，共 {len(records)} 场线下宣讲（含详情）")

    # 2. 展开数据
    main_rows, job_rows = build_rows(records, profile)
    if not main_rows:
        log("本次未抓到有效数据，退出")
        return 1

    # 3. 增量合并（首次运行无旧表则为全量新增）
    existing = load_existing(out_path)
    merged_rows, stats = merge_incremental(existing, main_rows)
    log(f"增量合并完成：新增 {stats['新增']}，更新 {stats['更新']}，"
        f"已结束 {stats['已结束']}，未变化 {stats['未变化']}")

    # 4. 写 Excel
    crawl_time = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    write_excel(out_path, merged_rows, job_rows, crawl_time, args.horizon, stats)
    log(f"Excel 已写入：{out_path}")

    # 5. 可选 JSON
    if args.dump_json:
        os.makedirs(os.path.dirname(os.path.abspath(args.dump_json)), exist_ok=True)
        with open(args.dump_json, "w", encoding="utf-8") as f:
            json.dump({"crawl_time": crawl_time, "records": [
                {k: (v if not isinstance(v, list) else v)
                 for k, v in r.__dict__.items()} for r in records
            ]}, f, ensure_ascii=False, indent=2)
        log(f"JSON 已写入：{args.dump_json}")

    # 6. 控制台总结
    print("\n========== 抓取总结 ==========")
    print(f"数据范围：未来 {args.horizon} 天 · 共 {len(merged_rows)} 场")
    print(f"增量：新增 {stats['新增']} / 更新 {stats['更新']} / "
          f"已结束 {stats['已结束']}")
    from collections import Counter
    cats = Counter(r["岗位类别(主)"] for r in merged_rows)
    print("\n岗位类别分布：")
    for cat, n in cats.most_common():
        print(f"  {cat}: {n} 场")
    opps = Counter(r["笔试面试机会"] for r in merged_rows)
    print("\n笔试面试机会分布：")
    for op, n in opps.most_common():
        print(f"  {op}: {n} 场")
    highs = [r for r in merged_rows if r["推荐度"] == "高"]
    print(f"\n高推荐场次：{len(highs)} 场")
    for r in highs[:10]:
        print(f"  [{r['举办日期']}] {r['公司/单位']} | {r['笔试面试机会']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
