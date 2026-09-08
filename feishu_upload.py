# -*- coding: utf-8 -*-
"""飞书表格上传模块：把生成的本地 Excel 导入为飞书在线表格。

依赖：lark-cli（飞书命令行工具，需已安装且处于登录态）。
实现要点：
- lark-cli 的 --file 只接受"当前工作目录内的相对路径"，
  因此通过 subprocess 调用并显式指定 cwd=项目根目录，传相对路径。
- 成功返回新表格 URL；失败抛异常，由调用方捕获并回退本地交付。
"""
import json
import os
import shutil
import subprocess


def upload_to_feishu(xlsx_path: str,
                     folder_token: str = "",
                     name: str = "") -> str:
    """把本地 Excel 导入为飞书在线表格，返回新表格的 URL。

    Args:
        xlsx_path: 本地 Excel 文件路径（绝对或相对路径均可）
        folder_token: 飞书云空间目标文件夹 token，留空存根目录
        name: 导入后表格名称，留空用本地文件名（去扩展名）
    Returns:
        新表格的访问 URL
    Raises:
        RuntimeError: lark-cli 缺失 / 导入失败 / 输出解析失败
    """
    cli = shutil.which("lark-cli")
    if not cli:
        raise RuntimeError("未找到 lark-cli（飞书命令行工具），"
                           "请先安装并登录，或改用 --output-target local")

    project_root = os.path.dirname(os.path.abspath(__file__))
    try:
        rel = os.path.relpath(xlsx_path, project_root)
    except ValueError:  # 跨盘符时 os.path.relpath 会抛错，退化为绝对路径
        rel = os.path.abspath(xlsx_path)

    cmd = [cli, "sheets", "+workbook-import", "--file", rel]
    if folder_token:
        cmd += ["--folder-token", folder_token]
    if name:
        cmd += ["--name", name]

    proc = subprocess.run(cmd, cwd=project_root, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    out = (proc.stdout or "") + (proc.stderr or "")
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        raise RuntimeError(f"lark-cli 输出解析失败，无法确认导入结果：{out[:200]}")

    if not payload.get("ok"):
        detail = (payload.get("data") or {}).get("job_error_msg")
        raise RuntimeError(f"飞书导入失败：{detail or out[:200]}")

    url = (payload.get("data") or {}).get("url", "")
    if not url:
        raise RuntimeError(f"飞书导入未返回表格链接：{out[:200]}")
    return url
