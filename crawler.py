# -*- coding: utf-8 -*-
"""爬虫模块：抓取线下宣讲会列表 + 详情页，解析结构化数据。

站点防爬说明：
- 列表页与详情页的正文均以 base64+zlib 压缩后内嵌在页面脚本中，
  由 JS 调用 Base64.decode(unzip("...").substr(n)).substr(m) 还原。
  本模块按相同逻辑在 Python 端还原。
"""
import base64
import re
import time
import zlib
from dataclasses import dataclass, field, asdict
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

import config


# ---------------------------------------------------------------- 通用请求
def fetch_text(url: str) -> Optional[str]:
    """带 UA/超时/重试的页面抓取"""
    for attempt in range(config.REQUEST_RETRY + 1):
        try:
            resp = requests.get(
                url, timeout=config.REQUEST_TIMEOUT,
                headers={"User-Agent": config.USER_AGENT})
            resp.encoding = resp.apparent_encoding or "utf-8"
            if resp.status_code == 200:
                return resp.text
        except requests.RequestException:
            pass
        time.sleep(1 + attempt)
    return None


def _js_b64decode(s: str) -> str:
    """还原 JS 的 Base64.decode（字符串→解码→utf8 文本）"""
    pad = "=" * (-len(s) % 4)
    return base64.b64decode(s + pad).decode("utf-8", errors="replace")


def decode_embedded(html: str) -> str:
    """还原列表页内嵌的压缩 HTML（多层 base64 + zlib + view1d/view2d 头）"""
    m = re.search(r'unzip\("([A-Za-z0-9+/=]+)"\)', html)
    if not m:
        return ""
    data = zlib.decompress(base64.b64decode(m.group(1)), 15)
    s = data.decode("utf-8", errors="replace").strip()
    for _ in range(4):  # 最多剥 4 层 viewX 头
        if s.startswith("view2d"):
            s = _js_b64decode(s[len("view2d"):].strip())
        elif s.startswith("view1d"):
            s = s[len("view1d"):].strip()
        else:
            break
    return s


def decode_detail_blocks(html: str) -> List[tuple]:
    """还原详情页所有 #contentXXXX 容器的内容。

    返回 [(容器id, 解码后文本), ...]，按页面出现顺序。
    """
    pat = re.compile(
        r'#(content\d+)"[\s\S]{0,400}?'
        r'Base64\.decode\(unzip\("([A-Za-z0-9+/=]+)"\)'
        r'(?:\.substr\((\d+)\))?\)(?:\.substr\((\d+)\))?')
    out = []
    for cid, payload, a, b in pat.findall(html):
        try:
            s = zlib.decompress(base64.b64decode(payload), 15).decode(
                "utf-8", errors="replace")
            if a:
                s = s[int(a):]
            d = _js_b64decode(s)
            if b:
                d = d[int(b):]
            # 再剥 view 头
            d2 = d.strip()
            for _ in range(4):
                if d2.startswith("view2d"):
                    d2 = _js_b64decode(d2[len("view2d"):].strip())
                elif d2.startswith("view1d"):
                    d2 = d2[len("view1d"):].strip()
                else:
                    break
            out.append((cid, d2))
        except Exception:
            out.append((cid, ""))
    return out


# ---------------------------------------------------------------- 数据模型
@dataclass
class TeachinRecord:
    """一场线下宣讲会"""
    id: str                       # 站点记录 id
    title: str                    # 宣讲会名称
    company: str = ""             # 公司/单位名（取标题精简）
    status: str = "线下"           # 线下/空中
    location: str = ""            # 举办地点
    time_text: str = ""           # 举办时间原文
    date: str = ""                # 举办日期 YYYY-MM-DD
    industry: str = ""            # 单位行业
    company_nature: str = ""      # 单位性质
    company_scale: str = ""       # 单位规模
    detail_body: str = ""         # 宣讲详情正文（做什么、环节安排等）
    detail_url: str = ""          # 详情页链接
    has_written_test: bool = False    # 是否有笔试机会
    has_interview: bool = False       # 是否有面试机会
    opp_level: str = ""               # 机会等级：现场笔试面试/宣讲后安排/仅投递/未提及
    opp_evidence: str = ""            # 依据原文（用于人工复核）
    jobs: List[dict] = field(default_factory=list)  # 职位列表


# ---------------------------------------------------------------- 列表页
def parse_teachin_list(html: str) -> List[TeachinRecord]:
    """解析线下宣讲列表页，返回记录（不含详情）"""
    inner = decode_embedded(html)
    if not inner:
        return []
    soup = BeautifulSoup(inner, "lxml")
    records = []
    for ul in soup.select("ul.teachinList"):
        try:
            a = ul.select_one("li.span9 a")
            if not a or not a.get("href"):
                continue
            mid = re.search(r"/teachin/view/id/(\d+)", a["href"])
            if not mid:
                continue
            loc_li = ul.select_one("li.span5")
            time_li = ul.find_all("li")[-1]
            status_span = ul.select_one("li.span9 .status-text")
            rec = TeachinRecord(
                id=mid.group(1),
                title=a.get("title") or a.get_text(strip=True),
                status=status_span.get_text(strip=True) if status_span else "线下",
                location=loc_li.get_text(strip=True) if loc_li else "",
                time_text=time_li.get_text(strip=True) if time_li else "",
                detail_url=config.BASE_URL + a["href"],
            )
            mdate = re.search(r"(20\d{2}-\d{2}-\d{2})", rec.time_text)
            rec.date = mdate.group(1) if mdate else ""
            rec.company = re.sub(r"【.*?】|（.*?）|\(.*?\)", "", rec.title).strip()
            records.append(rec)
        except Exception:
            continue
    return records


def fetch_teachin_page(page: int) -> Optional[List[TeachinRecord]]:
    url = f"{config.TEACHIN_LIST_URL}/page/{page}"
    html = fetch_text(url)
    if not html:
        return None
    return parse_teachin_list(html)


# ---------------------------------------------------------------- 详情页
def _parse_basic_info(block_html: str) -> dict:
    """解析详情页基本信息块（单位性质/行业/规模/宣讲时间/地点/类别…）"""
    info = {}
    soup = BeautifulSoup(block_html, "lxml")
    for li in soup.select("li"):
        text = li.get_text(" ", strip=True)
        if "：" in text:
            k, v = text.split("：", 1)
            info[k.strip()] = v.strip()
    return info


def _parse_jobs(html: str) -> List[dict]:
    """解析职位列表表格"""
    jobs = []
    soup = BeautifulSoup(html, "lxml")
    for tr in soup.select("table tbody tr"):
        try:
            cells = tr.find_all("td")
            if len(cells) < 3:
                continue
            job_cell = cells[1].get_text("|", strip=True)
            parts = [p.strip() for p in job_cell.split("|") if p.strip()]
            # 常见形态：[职位名, 薪资, 省市-城市, 工作性质, 学历]
            name = parts[0] if parts else ""
            salary = parts[1] if len(parts) > 1 else ""
            city = parts[2] if len(parts) > 2 else ""
            nature = parts[3] if len(parts) > 3 else ""
            degree = parts[4] if len(parts) > 4 else ""
            majors = cells[2].get_text(" ", strip=True) if len(cells) > 2 else ""
            op = cells[-1].get_text(" ", strip=True).strip() if len(cells) > 3 else ""
            jobs.append({
                "job_name": name,
                "salary": salary,
                "city": city,
                "nature": nature,
                "degree": degree,
                "majors": majors,
                "operation": op,
            })
        except Exception:
            continue
    return jobs


def fetch_detail(rec: TeachinRecord) -> TeachinRecord:
    """抓取并解析一场宣讲会的详情页"""
    html = fetch_text(rec.detail_url)
    if not html:
        return rec
    blocks = decode_detail_blocks(html)
    # 基本信息块：含“单位性质/宣讲时间”等 <ul class=clearfix><li>标签：值</li>
    basic = {}
    body = ""
    for _, content in blocks:
        if not content:
            continue
        if "<li>单位性质" in content or "宣讲类别" in content or "单位行业" in content:
            basic.update(_parse_basic_info(content))
        elif "<p" in content or "宣讲" in content:
            # 详情正文：取最长的富文本块
            if len(content) > len(body):
                body = content
    rec.industry = basic.get("单位行业", "")
    rec.company_nature = basic.get("单位性质", "")
    rec.company_scale = basic.get("单位规模", "")
    if not rec.location and basic.get("举办地点"):
        rec.location = basic["举办地点"]
    if not rec.time_text and basic.get("宣讲时间"):
        rec.time_text = basic["宣讲时间"]
        mdate = re.search(r"(20\d{2}-\d{2}-\d{2})", rec.time_text)
        rec.date = mdate.group(1) if mdate else rec.date
    # 去掉正文里的 HTML 标签，保留纯文本便于关键词判断
    if body:
        rec.detail_body = BeautifulSoup(body, "lxml").get_text("\n", strip=True)
    rec.jobs = _parse_jobs(html)
    return rec


# ---------------------------------------------------------------- 主流程
def crawl_offline_teachins(horizon_days: int = None,
                           start_page: int = 1,
                           max_pages: int = 200,
                           progress=None) -> List[TeachinRecord]:
    """抓取未来 N 天内的线下宣讲会（列表按举办时间升序）。

    返回按举办日期排序的记录（已含详情信息）。
    """
    import datetime as dt
    horizon_days = horizon_days or config.DEFAULT_HORIZON_DAYS
    today = dt.date.today()
    cutoff = today + dt.timedelta(days=horizon_days)
    records = []
    page = start_page
    while page <= max_pages:
        items = fetch_teachin_page(page)
        if items is None:
            break
        if not items:
            break
        # 列表按举办时间升序：一旦越过截止日就停止
        page_dates = [i.date for i in items if i.date]
        if page_dates:
            last_date = max(page_dates)
            if last_date > cutoff.isoformat():
                items = [i for i in items
                         if i.date and i.date <= cutoff.isoformat()]
                records.extend(items)
                break
        records.extend(items)
        if progress:
            progress(page, len(records))
        page += 1
        time.sleep(config.REQUEST_DELAY)

    # 抓详情
    result = []
    for i, rec in enumerate(records):
        if rec.date and rec.date < today.isoformat():
            continue  # 已结束的不进本次结果（增量时保留旧状态）
        fetch_detail(rec)
        result.append(rec)
        if progress:
            progress(-1, len(result))
        time.sleep(config.REQUEST_DELAY)
    return result
