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

# 输出目标：local = 仅生成本地Excel；feishu = 本地Excel + 上传飞书在线表格
# 命令行可用 --output-target local/feishu 临时覆盖（默认取这里的配置）
OUTPUT_TARGET = "local"
# 飞书表格存放文件夹 token（留空 = 存到飞书云空间根目录）
# 获取方式：飞书云空间网页版打开目标文件夹，URL 中 .../space/<token> 一段
FEISHU_FOLDER_TOKEN = ""

# 简历（用于简历驱动推荐；支持 PDF/TXT/MD）
RESUME_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "resume", "resume.pdf")

# 用户专业背景（用于岗位匹配推荐，可按需修改；简历解析失败时作为回退）
USER_MAJORS = ["计算机", "软件", "人工智能", "电子信息", "通信", "自动化",
               "集成电路", "数学", "数据科学", "控制"]
