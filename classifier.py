# -*- coding: utf-8 -*-
"""分类器：岗位类别归类 + 笔试/面试机会识别 + 推荐度打分（规则透明可复核）"""
import re
from typing import List, Tuple

import config

# ---------------------------------------------------------------- 岗位分类
# 规则按优先级排列：命中前面的规则优先
JOB_CATEGORY_RULES: List[Tuple[str, List[str]]] = [
    ("算法/AI",
     ["算法", "人工智能", "机器学习", "深度学习", "大模型", "自然语言", "nlp",
      "推荐系统", "推荐算法", "搜索算法", "数据挖掘", "计算机视觉", "图像算法",
      "语音算法", "风控算法", "强化学习", "运筹优化", "ai", "智能算法", "机器学习"]),
    ("数据",
     ["数据分析", "数据开发", "数据仓库", "大数据", "数据科学", "数据工程",
      "bi", "数仓", "数据挖掘工程师", "数据平台"]),
    ("芯片/硬件",
     ["ic", "芯片", "半导体", "模拟", "数字ic", "版图", "器件", "工艺",
      "封装", "fpga", "硬件", "电路", "电源", "嵌入式", "射频", "天线",
      "微波", "微电子", "晶圆", "eda", "芯片设计", "验证工程师", "质量工程师"]),
    ("软件开发",
     ["开发", "软件", "前端", "后端", "客户端", "测试", "全栈", "运维",
      "sre", "devops", "架构师", "java", "c++", "python", "golang", "go开发",
      "工程师", "程序", "研发", "web", "app", "数据研发"]),
    ("通信/网络",
     ["通信", "网络", "协议", "5g", "6g", "无线", "光通信", "交换",
      "传输", "网络安全", "安全工程师"]),
    ("产品/设计",
     ["产品经理", "产品运营", "产品助理", "交互", "ui", "ux", "设计",
      "视觉设计", "平面设计"]),
    ("运营/市场/销售",
     ["运营", "市场", "销售", "商务", "营销", "客户经理", "渠道",
      "品牌", "推广", "售前", "售后", "顾问"]),
    ("职能/管理",
     ["人力", "hr", "财务", "会计", "行政", "法务", "采购", "审计",
      "税务", "董秘", "文秘", "合规"]),
    ("制造/供应链",
     ["制造", "生产", "供应链", "物流", "采购", "工艺工程师", "设备",
      "质量", "测试工程师"]),
]

# 兜底分类
DEFAULT_CATEGORY = "其他"


def classify_job(job_name: str) -> str:
    """按职位名称归类岗位类别"""
    name = (job_name or "").lower().replace(" ", "")
    for category, kws in JOB_CATEGORY_RULES:
        for kw in kws:
            if kw in name:
                return category
    return DEFAULT_CATEGORY


def classify_teachin(rec) -> str:
    """一场宣讲会的主类别：职位列表 → 标题 → 详情正文 → 行业，逐级兜底"""
    if rec.jobs:
        cats = [classify_job(j["job_name"]) for j in rec.jobs]
        # 用列表求众数：同票数时取职位列表中先出现的类别（确定性，避免 set 哈希随机）
        main_cat = max(cats, key=cats.count)
        # 职位能归类的以职位为准；若职位全为“其他”则继续用标题兜底
        if main_cat != DEFAULT_CATEGORY:
            return main_cat
    # 标题兜底
    for category, kws in JOB_CATEGORY_RULES:
        t = (rec.title or "").lower()
        for kw in kws:
            if kw in t:
                return category
    # 详情正文兜底（很多单位正文会列“招聘岗位：…”）；用强关键词避免泛词误判
    BODY_RULES: List[Tuple[str, List[str]]] = [
        ("算法/AI", ["算法工程师", "机器学习", "深度学习", "人工智能", "大模型",
                     "nlp", "计算机视觉", "数据挖掘", "推荐算法"]),
        ("数据", ["数据分析", "数据开发", "大数据", "数据仓库"]),
        ("芯片/硬件", ["集成电路", "ic设计", "芯片", "半导体", "微电子", "模拟ic",
                       "数字ic", "fpga", "射频", "版图", "器件工程师", "工艺工程师"]),
        ("软件开发", ["软件开发", "后端开发", "前端开发", "java开发", "c++开发",
                      "python开发", "测试开发", "软件工程师"]),
        ("通信/网络", ["通信工程师", "网络工程师", "5g", "6g", "通信工程"]),
        ("产品/设计", ["产品经理", "ui设计", "交互设计"]),
        ("运营/市场/销售", ["市场销售", "销售工程师", "客户经理", "运营专员"]),
        ("职能/管理", ["人力资源", "财务管理", "财务会计"]),
        ("制造/供应链", ["生产制造", "供应链", "质量工程师"]),
    ]
    body = (rec.detail_body or "").lower()
    for category, kws in BODY_RULES:
        for kw in kws:
            if kw in body:
                return category
    # 行业兜底
    industry_map = {
        "教育": "运营/市场/销售",   # 教培岗位多为教师/销售
        "软件": "软件开发",
        "信息技术": "软件开发",
        "科学研究": "其他",
        "制造": "制造/供应链",
        "金融": "职能/管理",
        "房地产": "运营/市场/销售",
        "电力": "芯片/硬件",
        "军工": "芯片/硬件",
    }
    ind = rec.industry or ""
    for k, v in industry_map.items():
        if k in ind:
            return v
    return DEFAULT_CATEGORY


# ---------------------------------------------------------------- 笔试/面试机会
# 关键词 → (是否笔试, 是否面试, 等级, 标签)
_OPP_PATTERNS = [
    # 现场/当场笔试、面试（最高等级）
    (r"现场笔试|当场笔试|宣讲[^。；]{0,20}笔试|宣讲结束后[^。；]{0,15}笔试|笔试环节",
     (True, False, "现场笔试/面试", "现场笔试")),
    (r"现场面试|当场面试|宣讲后[^。；]{0,15}面试|宣讲结束[^。；]{0,15}面试|即可安排面试|安排现场面试|面试环节|宣讲[^。；]{0,10}面试",
     (False, True, "现场笔试/面试", "现场面试")),
    # 宣讲后另行安排笔试/面试
    (r"笔试", (True, False, "宣讲后安排", "笔试")),
    (r"面试", (False, True, "宣讲后安排", "面试")),
    # 仅投递简历 / 简历筛选 / 测评
    (r"投递简历|简历投递|线上投递|简历筛选", (False, False, "仅投递/简历筛选", "简历投递")),
    (r"测评|性格测试|在线测评", (False, False, "仅投递/简历筛选", "测评")),
]

_OPP_TITLE_PATTERNS = [
    (r"现场笔试|当场笔试", (True, False, "现场笔试/面试", "标题含现场笔试")),
    (r"现场面试|当场面试", (False, True, "现场笔试/面试", "标题含现场面试")),
    (r"笔试", (True, False, "宣讲后安排", "标题含笔试")),
    (r"面试", (False, True, "宣讲后安排", "标题含面试")),
]

LEVEL_RANK = {"现场笔试/面试": 0, "宣讲后安排": 1, "仅投递/简历筛选": 2, "未提及": 3}


def detect_opportunity(rec) -> None:
    """识别笔试/面试机会，写入记录（含依据原文）"""
    texts = [rec.title, rec.detail_body]
    best = None  # (rank, has_wt, has_iv, level, evidence)

    def better(cand, cur):
        if cur is None:
            return True
        if cand[0] != cur[0]:
            return cand[0] < cur[0]   # rank 越小越优先（现场 < 宣讲后 < 仅投递 < 未提及）
        return (cand[1], cand[2]) > (cur[1], cur[2])  # 同等级时笔试/面试信号更多者优先

    # 标题（显式声明，rank 再降半级，即标题“仅投递”也优于正文同等级）
    for pat, (wt, iv, level, tag) in _OPP_TITLE_PATTERNS:
        m = re.search(pat, rec.title)
        if m:
            cand = (LEVEL_RANK[level] - 0.5, wt, iv, level,
                    f"[{tag}] {rec.title[max(0, m.start()-15):m.end()+15]}")
            if better(cand, best):
                best = cand
    # 正文
    for pat, (wt, iv, level, tag) in _OPP_PATTERNS:
        m = re.search(pat, rec.detail_body)
        if m:
            s = rec.detail_body.replace("\n", " ")
            cand = (LEVEL_RANK[level], wt, iv, level,
                    f"[{tag}] {s[max(0, m.start()-25):m.end()+25]}")
            if better(cand, best):
                best = cand
    if best:
        rec.has_written_test, rec.has_interview, rec.opp_level, rec.opp_evidence = \
            best[1], best[2], best[3], best[4]
    else:
        rec.has_written_test, rec.has_interview = False, False
        rec.opp_level, rec.opp_evidence = "未提及", ""


# ---------------------------------------------------------------- 推荐度
# 技术类岗位类别（作为匹配度兜底）
TECH_CATEGORIES = {"算法/AI", "数据", "芯片/硬件", "软件开发", "通信/网络"}


def _resume_match(rec, profile: dict, cat: str = None) -> List[Tuple[str, str]]:
    """简历画像与宣讲会匹配，返回命中点 [(类型, 内容), ...]，最多 4 条。

    匹配维度：
    1. 专业：简历专业关键词 命中 职位「需求专业」/ 单位「行业」
    2. 技能：简历技能 命中 职位名称（如 大模型、Python、RAG…）
    3. 意向岗位：简历「求职意向」文本 命中 职位名称 / 岗位类别
    """
    if cat is None:
        cat = classify_teachin(rec)
    hits = []
    majors = [m.lower() for m in (profile or {}).get("majors", [])]

    # 1. 专业命中
    major_hit = None
    if rec.jobs:
        majors_text = " ".join(j["majors"] for j in rec.jobs).lower()
        major_hit = next((m for m in majors if m in majors_text), None)
    if not major_hit:
        ind = (rec.industry or "").lower()
        major_hit = next((m for m in majors if m in ind), None)
    if major_hit:
        hits.append(("专业", major_hit))

    # 2. 技能 / 3. 意向岗位：职位名（无职位时用标题）文本
    job_text = (" ".join(j["job_name"] for j in rec.jobs).lower()
                if rec.jobs else (rec.title or "").lower())
    for name, alis in (profile or {}).get("skills", []):
        if any(a in job_text for a in alis):
            hits.append(("技能", name))

    # 意向岗位：整句命中 → 关键词命中（按 应用/开发/工程师 等切分）→ 类别映射
    target_cat = {"算法": "算法/AI", "大模型": "算法/AI", "人工智能": "算法/AI",
                  "数据": "数据", "开发": "软件开发", "前端": "软件开发",
                  "后端": "软件开发", "测试": "软件开发", "运维": "软件开发",
                  "芯片": "芯片/硬件", "硬件": "芯片/硬件", "嵌入式": "芯片/硬件",
                  "通信": "通信/网络", "网络": "通信/网络", "产品": "产品/设计",
                  "设计": "产品/设计", "运营": "运营/市场/销售",
                  "销售": "运营/市场/销售", "市场": "运营/市场/销售"}
    for t in (profile or {}).get("targets", []):
        tl = t.lower()
        if tl and tl in job_text:          # 整句命中
            hits.append(("意向岗位", t))
            break
        kws = [p for p in re.split(r"应用|开发|工程师|方向|岗位|研究|技术|相关",
                                   tl) if len(p) >= 2]
        if any(k in job_text for k in kws):   # 关键词命中职位名
            hits.append(("意向岗位", t))
            break
        if any(target_cat.get(k) == cat for k in kws):  # 命中岗位类别
            hits.append(("意向岗位", t))
            break
    return hits[:4]


def recommend(rec, profile: dict = None) -> Tuple[str, str, List[Tuple[str, str]]]:
    """基于机会等级 + 简历画像匹配给出推荐度（高/中/低）、理由与命中点。

    profile 为 resume_parser.parse_resume 的返回结果；
    为 None 时回退到 config.USER_MAJORS 专业规则（旧行为）。
    """
    if profile is None:
        profile = {"majors": list(config.USER_MAJORS), "skills": [], "targets": []}
    cat = classify_teachin(rec)
    hits = _resume_match(rec, profile, cat)
    hit_txt = ("；简历命中：" + "、".join(f"{t}:{v}" for t, v in hits)) if hits else ""
    cat_relevant = cat in TECH_CATEGORIES
    has_hit = bool(hits)
    level = rec.opp_level

    if level == "现场笔试/面试" and (has_hit or cat_relevant):
        return "高", "现场笔试/面试机会明确，岗位与简历相关" + hit_txt, hits
    if level == "现场笔试/面试":
        return "中", "现场笔试/面试机会明确，但岗位与简历匹配度一般", hits
    if level == "宣讲后安排" and (has_hit or cat_relevant):
        return "高", "宣讲后安排笔试/面试，岗位与简历相关" + hit_txt, hits
    if level == "宣讲后安排":
        return "中", "宣讲后安排笔试/面试，专业匹配度一般", hits
    if level == "仅投递/简历筛选" and (has_hit or cat_relevant):
        return "中", "仅简历投递环节，岗位与简历相关" + hit_txt, hits
    if has_hit and cat_relevant:
        return "中", "岗位与简历相关，未提及笔试面试安排" + hit_txt, hits
    return "低", "未提及笔试面试安排且岗位匹配度有限", hits
