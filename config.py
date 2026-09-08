# -*- coding: utf-8 -*-
"""西电就业信息网 · 招聘信息整理助手 配置文件"""
import os

# 站点
BASE_URL = "https://job.xidian.edu.cn"
TEACHIN_LIST_URL = BASE_URL + "/teachin/index/type/offline"  # 线下宣讲会列表
DETAIL_URL = BASE_URL + "/teachin/view/id/{id}"

# 抓取参数
DEFAULT_HORIZON_DAYS = 14          # 默认抓取未来 N 天内的线下宣讲
REQUEST_TIMEOUT = 30               # 单请求超时(秒)
REQUEST_RETRY = 2                  # 失败重试次数
REQUEST_DELAY = 0.4                # 请求间隔(秒)，避免对站点造成压力
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 输出
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
EXCEL_FILENAME = "西电线下宣讲会信息汇总.xlsx"
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# 简历（用于简历驱动推荐；支持 PDF/TXT/MD）
RESUME_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "resume", "resume.pdf")

# 用户专业背景（用于岗位匹配推荐，可按需修改；简历解析失败时作为回退）
USER_MAJORS = ["计算机", "软件", "人工智能", "电子信息", "通信", "自动化",
               "集成电路", "数学", "数据科学", "控制"]
