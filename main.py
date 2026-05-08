#!/usr/bin/env python3
"""
Bio-AI 科研情报雷达：抓取 GitHub Bio-AI 项目，生成中文情报摘要并邮件推送。

本地运行示例：
python main.py --skip-email --output bio_radar_report.md
python main.py --skip-ai --output github_projects.json
python main.py --dry-run
python main.py --skip-email --archive-dir reports
"""

import argparse
import json
import os
import re
import smtplib
import time
from datetime import date, datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from pathlib import Path
from typing import Dict, List, Optional

import requests

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
GITHUB_REPO_URL = "https://api.github.com/repos"
REQUEST_TIMEOUT = 20
MAX_RETRIES = 3
BACKOFF_SECONDS = [2, 4, 8]

TRACK1_KEYWORDS = [
    "bioinformatics",
    "computational biology",
    "genomics",
    "single-cell",
    "pangenome",
    "bioinformatics workflow",
]

TRACK2_KEYWORDS = [
    "biomedical LLM",
    "foundation model biology",
    "protein language model",
    "DNA language model",
    "LLM agent",
    "RAG framework",
    "LLM inference",
    "LLM evaluation",
]

SYSTEM_PROMPT = """你是一位“计算生物学情报分析师”，熟悉生物信息学、AI for Science、大语言模型、基因组/蛋白质语言模型、、单细胞组学、泛基因组、作物基因组学和科研代码生态。

请根据输入的 GitHub 项目 JSON，生成中文科研情报日报。报告必须分为三部分：

第一部分：Top 高星区技术风向
- 只分析 track 包含“高星”的项目。
- 总结近期高星 Bio-AI 项目的技术趋势。
- 判断哪些方向更偏工具化、平台化、LLM Agent 化或多模态化。
- 不要简单罗列项目，要给出趋势判断。

第二部分：最新更新区低星潜力项目深挖
- 重点分析 track 包含“最新更新”的项目。
- 优先关注 stars 较低但 updated_at 很新的项目。
- 从 description 和 readme_excerpt 中寻找以下线索：paper、arXiv、bioRxiv、manuscript、model、checkpoint、weights、dataset、benchmark、reproducibility。
- 判断哪些项目可能对应新论文、新模型、新数据集或可复现实验代码。
- 给出值得继续跟踪的项目清单，并说明理由。

第三部分：逐条项目速览
- 必须覆盖输入 JSON 中的所有去重项目，不要只挑选少数项目。
- 每个项目写 2-3 句话中文总结。
- 每条总结应包含：项目做什么、和 Bio-AI 的关系、是否存在论文/模型/数据线索。
- 如果信息不足，要明确写“线索不足”，不要编造。
- 每个项目必须包含 GitHub 链接。
- 按 track 分组：先“高星项目速览”，再“最新更新项目速览”。
- 若项目同时属于两个 track，只出现一次，并标注“高星 + 最新更新”。

输出要求：
- 使用 Markdown。
- 中文输出。
- 标题清晰。
- 推荐项目必须包含 GitHub 链接。
- 对不确定信息明确写“线索不足”或“需要进一步核验”。
- 不要编造论文、作者、模型权重或实验结果。

最终结构：
# Bio-AI 科研情报雷达 - YYYY-MM-DD
## 一、Top 高星区技术风向
## 二、最新更新区低星潜力项目深挖
## 三、逐条项目速览
"""


def log(message: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {message}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bio-AI 科研情报雷达")
    parser.add_argument("--dry-run", action="store_true", help="等价于 --skip-email")
    parser.add_argument("--skip-ai", action="store_true", help="仅抓取项目，不调用 DeepSeek")
    parser.add_argument("--skip-email", action="store_true", help="生成报告但不发送邮件")
    parser.add_argument("--max-readme", type=int, default=800, help="README 截取长度，默认 800")
    parser.add_argument("--output", type=str, default="", help="可选输出文件路径")
    parser.add_argument(
        "--archive-dir",
        type=str,
        default="",
        help="可选，按日期自动归档报告目录，例如 reports",
    )
    return parser.parse_args()


def safe_output_path(path_str: str) -> Path:
    path = Path(path_str)
    if not path.exists():
        return path

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = path.suffix
    stem = path.stem
    alt_name = f"{stem}_{stamp}{suffix}" if suffix else f"{stem}_{stamp}"
    alt_path = path.with_name(alt_name)
    log(f"输出文件已存在，避免覆盖，改为写入: {alt_path}")
    return alt_path


def write_output(path_str: str, content: str) -> Path:
    output_path = safe_output_path(path_str)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path


def archive_report(run_date: str, report_markdown: str, archive_dir: str) -> Path:
    archive_base = Path(archive_dir)
    file_path = archive_base / f"bio_radar_{run_date}.md"
    final_path = safe_output_path(str(file_path))
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_text(report_markdown, encoding="utf-8")
    return final_path


def extract_daily_summary(report_markdown: str, max_paragraphs: int = 2, max_chars: int = 160) -> str:
    lines = report_markdown.splitlines()
    section_start = -1
    section_end = len(lines)

    for idx, line in enumerate(lines):
        if line.strip().startswith("## 一、Top 高星区技术风向"):
            section_start = idx + 1
            break

    if section_start >= 0:
        for idx in range(section_start, len(lines)):
            if lines[idx].strip().startswith("## "):
                section_end = idx
                break
        source_lines = lines[section_start:section_end]
    else:
        source_lines = lines

    paragraphs: List[str] = []
    buffer: List[str] = []
    for raw in source_lines:
        s = raw.strip()
        if not s:
            if buffer:
                paragraphs.append(" ".join(buffer))
                buffer = []
            continue
        if s.startswith("#"):
            continue
        # 清理列表前缀，便于生成简短摘要。
        s = re.sub(r"^[-*]\s+", "", s)
        s = re.sub(r"^\d+\.\s*", "", s)
        buffer.append(s)

    if buffer:
        paragraphs.append(" ".join(buffer))

    cleaned = [p for p in paragraphs if p and not p.startswith("这里写")]
    if not cleaned:
        return "线索不足，需要进一步核验。"

    summary = " ".join(cleaned[:max_paragraphs])
    summary = re.sub(r"\s+", " ", summary).strip()
    if len(summary) > max_chars:
        summary = summary[: max_chars - 1].rstrip() + "…"
    return summary


def report_sort_key(path: Path) -> str:
    # 文件名示例：bio_radar_2026-05-08.md 或 bio_radar_2026-05-08_20260508_120000.md
    return path.stem.replace("bio_radar_", "")


def update_archive_index(archive_dir: str) -> Path:
    archive_base = Path(archive_dir)
    archive_base.mkdir(parents=True, exist_ok=True)

    report_files = sorted(
        archive_base.glob("bio_radar_*.md"),
        key=report_sort_key,
        reverse=True,
    )

    now_label = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# Bio-AI Radar Reports Archive",
        "",
        "自动生成的日报索引，按日期倒序列出历史报告。",
        f"最后更新：{now_label} (Asia/Shanghai)",
        "",
    ]

    if not report_files:
        lines.append("当前暂无归档报告。")
    else:
        latest = report_files[0]
        latest_text = latest.read_text(encoding="utf-8")
        latest_summary = extract_daily_summary(latest_text)
        lines.extend(
            [
                "## 最新一期",
                f"- [{latest.name}](./{latest.name})",
                f"摘要：{latest_summary}",
                "",
                "## 历史列表（倒序）",
            ]
        )

        for report_path in report_files:
            report_text = report_path.read_text(encoding="utf-8")
            summary = extract_daily_summary(report_text)
            date_match = re.search(r"bio_radar_(\d{4}-\d{2}-\d{2})", report_path.name)
            date_label = date_match.group(1) if date_match else "unknown-date"
            lines.append(f"- {date_label} | [{report_path.name}](./{report_path.name}) | 摘要：{summary}")

    index_path = archive_base / "README.md"
    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return index_path


def parse_gh_time(ts: str) -> datetime:
    if not ts:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


class GitHubClient:
    def __init__(self, token: str = ""):
        self.base_headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "bio-ai-radar-script",
        }
        if token:
            self.base_headers["Authorization"] = f"Bearer {token}"

    def request(
        self,
        method: str,
        url: str,
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None,
    ) -> Optional[requests.Response]:
        merged_headers = dict(self.base_headers)
        if headers:
            merged_headers.update(headers)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.request(
                    method,
                    url,
                    params=params,
                    headers=merged_headers,
                    timeout=REQUEST_TIMEOUT,
                )
            except requests.RequestException as exc:
                log(f"请求异常 (attempt {attempt}/{MAX_RETRIES}): {exc}")
                if attempt < MAX_RETRIES:
                    time.sleep(BACKOFF_SECONDS[attempt - 1])
                continue

            if resp.status_code in (403, 429):
                remaining = resp.headers.get("X-RateLimit-Remaining", "unknown")
                reset_ts = resp.headers.get("X-RateLimit-Reset", "")
                wait_seconds = 0
                if reset_ts.isdigit():
                    wait_seconds = max(0, int(reset_ts) - int(time.time()) + 1)

                log(
                    "触发 GitHub rate limit 或访问受限 "
                    f"(HTTP {resp.status_code}, remaining={remaining}, reset={reset_ts or 'unknown'})"
                )

                if remaining == "0" and wait_seconds > 0 and attempt < MAX_RETRIES:
                    # 最多等待 30 秒，避免阻塞过久。
                    if wait_seconds <= 30:
                        log(f"等待 {wait_seconds} 秒后重试")
                        time.sleep(wait_seconds)
                        continue
                    log("rate limit 重置等待时间过长，跳过本次请求")
                    return None

                if attempt < MAX_RETRIES:
                    time.sleep(BACKOFF_SECONDS[attempt - 1])
                    continue
                return None

            if resp.status_code >= 500:
                log(f"服务器错误 HTTP {resp.status_code} (attempt {attempt}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES:
                    time.sleep(BACKOFF_SECONDS[attempt - 1])
                    continue
                return None

            if resp.status_code >= 400:
                snippet = resp.text[:300].replace("\n", " ")
                log(f"请求失败 HTTP {resp.status_code}: {snippet}")
                return None

            return resp

        return None

    def search_repositories(self, query: str, sort: str, order: str, per_page: int) -> List[Dict]:
        params = {
            "q": query,
            "sort": sort,
            "order": order,
            "per_page": per_page,
        }
        resp = self.request("GET", GITHUB_SEARCH_URL, params=params)
        if not resp:
            return []

        try:
            data = resp.json()
        except ValueError:
            log("GitHub 搜索响应 JSON 解析失败")
            return []

        return data.get("items", [])

    def fetch_readme_excerpt(self, full_name: str, max_chars: int) -> str:
        url = f"{GITHUB_REPO_URL}/{full_name}/readme"
        resp = self.request(
            "GET",
            url,
            headers={"Accept": "application/vnd.github.raw"},
        )
        if not resp:
            return ""
        text = resp.text or ""
        return text[:max_chars]


def normalize_repo(item: Dict, track_name: str) -> Dict:
    return {
        "name": item.get("name", ""),
        "full_name": item.get("full_name", ""),
        "url": item.get("html_url", ""),
        "description": item.get("description") or "",
        "stars": item.get("stargazers_count", 0),
        "updated_at": item.get("updated_at", ""),
        "created_at": item.get("created_at", ""),
        "track": [track_name],
    }


def collect_track_high_star(client: GitHubClient) -> List[Dict]:
    since = (date.today() - timedelta(days=30)).isoformat()
    pool: Dict[str, Dict] = {}

    for keyword in TRACK1_KEYWORDS:
        query = f'"{keyword}" created:>={since}'
        items = client.search_repositories(query=query, sort="stars", order="desc", per_page=20)
        log(f"轨道一关键词 '{keyword}' 抓取: {len(items)}")

        for item in items:
            repo = normalize_repo(item, "高星")
            key = repo["full_name"]
            if not key:
                continue
            old = pool.get(key)
            if not old or repo["stars"] > old["stars"]:
                pool[key] = repo

    repos = sorted(pool.values(), key=lambda x: x.get("stars", 0), reverse=True)[:20]
    return repos


def collect_track_latest_updates(client: GitHubClient) -> List[Dict]:
    pool: Dict[str, Dict] = {}

    for keyword in TRACK2_KEYWORDS:
        query = f'"{keyword}"'
        items = client.search_repositories(query=query, sort="updated", order="desc", per_page=10)
        log(f"轨道二关键词 '{keyword}' 抓取: {len(items)}")

        for item in items:
            repo = normalize_repo(item, "最新更新")
            key = repo["full_name"]
            if not key:
                continue
            old = pool.get(key)
            if not old or parse_gh_time(repo["updated_at"]) > parse_gh_time(old["updated_at"]):
                pool[key] = repo

    repos = sorted(pool.values(), key=lambda x: parse_gh_time(x.get("updated_at", "")), reverse=True)[:30]
    return repos


def merge_tracks(track1: List[Dict], track2: List[Dict]) -> List[Dict]:
    merged: Dict[str, Dict] = {}

    for repo in track1 + track2:
        key = repo.get("full_name", "")
        if not key:
            continue

        if key not in merged:
            merged[key] = {
                "name": repo.get("name", ""),
                "full_name": key,
                "url": repo.get("url", ""),
                "description": repo.get("description", ""),
                "stars": repo.get("stars", 0),
                "updated_at": repo.get("updated_at", ""),
                "created_at": repo.get("created_at", ""),
                "track": list(repo.get("track", [])),
                "readme_excerpt": "",
            }
            continue

        row = merged[key]
        row["stars"] = max(row.get("stars", 0), repo.get("stars", 0))

        if parse_gh_time(repo.get("updated_at", "")) > parse_gh_time(row.get("updated_at", "")):
            row["updated_at"] = repo.get("updated_at", "")

        if parse_gh_time(repo.get("created_at", "")) > parse_gh_time(row.get("created_at", "")):
            row["created_at"] = repo.get("created_at", "")

        if repo.get("description") and len(repo["description"]) > len(row.get("description", "")):
            row["description"] = repo["description"]

        for track_name in repo.get("track", []):
            if track_name not in row["track"]:
                row["track"].append(track_name)

    order_map = {"高星": 0, "最新更新": 1}
    for item in merged.values():
        item["track"] = sorted(item["track"], key=lambda x: order_map.get(x, 9))

    return list(merged.values())


def enrich_readme(client: GitHubClient, repos: List[Dict], max_readme: int) -> int:
    success_count = 0
    for repo in repos:
        excerpt = client.fetch_readme_excerpt(repo["full_name"], max_readme)
        repo["readme_excerpt"] = excerpt
        if excerpt:
            success_count += 1
    return success_count


def build_user_prompt(run_date: str, repos: List[Dict]) -> str:
    payload = json.dumps(repos, ensure_ascii=False, indent=2)
    return (
        f"运行日期：{run_date}\n\n"
        "以下是去重后的 GitHub 项目 JSON，请按要求生成科研情报日报：\n\n"
        f"{payload}"
    )


def generate_deepseek_report(api_key: str, run_date: str, repos: List[Dict]) -> str:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("缺少 openai 依赖，请先执行: pip install -r requirements.txt") from exc

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    response = client.chat.completions.create(
        model="deepseek-chat",
        temperature=0.2,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(run_date, repos)},
        ],
    )

    content = response.choices[0].message.content if response.choices else ""
    if not content:
        raise RuntimeError("DeepSeek 返回空内容")
    return content.strip()


def build_fallback_report(run_date: str, repos: List[Dict], error_msg: str) -> str:
    lines = [
        f"# Bio-AI 科研情报雷达 - {run_date}",
        "",
        "## 一、Top 高星区技术风向",
        "",
        "DeepSeek 总结失败，暂无法自动生成趋势分析。",
        f"错误信息：`{error_msg}`",
        "",
        "## 二、最新更新区低星潜力项目深挖",
        "",
        "自动深挖失败，建议后续重跑任务；以下给出原始候选项目供人工快速筛选。",
        "",
        "## 三、逐条项目速览",
        "",
    ]

    for repo in repos:
        track_tag = " + ".join(repo.get("track", []))
        lines.append(
            f"- [{repo['full_name']}]({repo['url']})（{track_tag}，⭐ {repo['stars']}）"
            f"：{repo.get('description') or '线索不足'}"
        )

    return "\n".join(lines)


def format_inline(text: str) -> str:
    link_pattern = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
    pieces = []
    last = 0

    for match in link_pattern.finditer(text):
        pieces.append(escape(text[last:match.start()]))
        link_text = escape(match.group(1))
        link_url = escape(match.group(2), quote=True)
        pieces.append(f'<a href="{link_url}">{link_text}</a>')
        last = match.end()

    pieces.append(escape(text[last:]))
    return "".join(pieces)


def markdown_to_html(md_text: str) -> str:
    lines = md_text.splitlines()
    html_lines: List[str] = []
    in_ul = False

    def close_ul() -> None:
        nonlocal in_ul
        if in_ul:
            html_lines.append("</ul>")
            in_ul = False

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            close_ul()
            html_lines.append("<br/>")
            continue

        if stripped.startswith("### "):
            close_ul()
            html_lines.append(f"<h3>{format_inline(stripped[4:])}</h3>")
            continue

        if stripped.startswith("## "):
            close_ul()
            html_lines.append(f"<h2>{format_inline(stripped[3:])}</h2>")
            continue

        if stripped.startswith("# "):
            close_ul()
            html_lines.append(f"<h1>{format_inline(stripped[2:])}</h1>")
            continue

        if stripped.startswith("- "):
            if not in_ul:
                html_lines.append("<ul>")
                in_ul = True
            html_lines.append(f"<li>{format_inline(stripped[2:])}</li>")
            continue

        close_ul()
        html_lines.append(f"<p>{format_inline(stripped)}</p>")

    close_ul()

    body = "\n".join(html_lines)
    return (
        "<html><body>"
        "<div style='font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif; line-height: 1.6;'>"
        f"{body}"
        "</div></body></html>"
    )


def parse_recipients(raw: str) -> List[str]:
    return [addr.strip() for addr in raw.split(",") if addr.strip()]


def send_email(report_markdown: str, run_date: str) -> None:
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port_raw = os.getenv("SMTP_PORT", "").strip()
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASS", "").strip()
    mail_from = os.getenv("MAIL_FROM", "").strip()
    mail_to_raw = os.getenv("MAIL_TO", "").strip()

    missing = []
    for key, value in {
        "SMTP_HOST": smtp_host,
        "SMTP_PORT": smtp_port_raw,
        "SMTP_USER": smtp_user,
        "SMTP_PASS": smtp_pass,
        "MAIL_FROM": mail_from,
        "MAIL_TO": mail_to_raw,
    }.items():
        if not value:
            missing.append(key)

    if missing:
        raise ValueError(f"缺少邮件相关环境变量: {', '.join(missing)}")

    try:
        smtp_port = int(smtp_port_raw)
    except ValueError as exc:
        raise ValueError("SMTP_PORT 必须是整数") from exc

    recipients = parse_recipients(mail_to_raw)
    if not recipients:
        raise ValueError("MAIL_TO 没有有效收件人")

    subject = f"Bio-AI 科研情报雷达 - {run_date}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = ", ".join(recipients)

    html_body = markdown_to_html(report_markdown)
    msg.attach(MIMEText(report_markdown, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(mail_from, recipients, msg.as_string())
    else:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.ehlo()
            if smtp_port == 587:
                server.starttls()
                server.ehlo()
            server.login(smtp_user, smtp_pass)
            server.sendmail(mail_from, recipients, msg.as_string())


def main() -> int:
    args = parse_args()
    run_date = date.today().isoformat()

    log(f"当前运行日期: {run_date}")

    skip_email = args.skip_email or args.dry_run
    if args.dry_run and not args.skip_email:
        log("启用 --dry-run，邮件发送将自动跳过")

    if args.skip_ai and not skip_email:
        log("启用 --skip-ai 时仅抓取项目，邮件发送将自动跳过")
        skip_email = True

    github_token = os.getenv("GITHUB_TOKEN", "").strip()
    if not github_token:
        log("未检测到 GITHUB_TOKEN，将以未认证模式请求 GitHub API（更容易触发限流）")

    client = GitHubClient(token=github_token)

    track1 = collect_track_high_star(client)
    log(f"轨道一抓取完成: {len(track1)} 个项目")

    track2 = collect_track_latest_updates(client)
    log(f"轨道二抓取完成: {len(track2)} 个项目")

    repos = merge_tracks(track1, track2)
    log(f"合并去重后项目数: {len(repos)}")

    readme_success = enrich_readme(client, repos, max_readme=max(0, args.max_readme))
    log(f"README 获取成功: {readme_success}/{len(repos)}")

    if args.skip_ai:
        payload = json.dumps(repos, ensure_ascii=False, indent=2)
        if args.output:
            out_path = write_output(args.output, payload)
            log(f"项目 JSON 已写入: {out_path}")
        else:
            print(payload)
        return 0

    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    report_markdown = ""
    ai_ok = False

    try:
        if not deepseek_api_key:
            raise ValueError("缺少 DEEPSEEK_API_KEY")
        report_markdown = generate_deepseek_report(deepseek_api_key, run_date, repos)
        ai_ok = True
        log("DeepSeek 总结成功")
    except Exception as exc:  # noqa: BLE001
        log(f"DeepSeek 总结失败: {exc}")
        report_markdown = build_fallback_report(run_date, repos, str(exc))

    if args.output:
        out_path = write_output(args.output, report_markdown)
        log(f"报告已写入本地文件: {out_path}")

    if args.archive_dir:
        archive_path = archive_report(run_date, report_markdown, args.archive_dir)
        log(f"报告已归档保存: {archive_path}")
        index_path = update_archive_index(args.archive_dir)
        log(f"归档索引已更新: {index_path}")

    if skip_email:
        log("已按参数跳过邮件发送")
        return 0

    try:
        send_email(report_markdown, run_date)
        log("邮件发送成功")
    except Exception as exc:  # noqa: BLE001
        log(f"邮件发送失败: {exc}")
        return 1

    if not ai_ok:
        log("注意：本次邮件为 AI 失败后的错误通知/降级报告")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
