# AGENTS.md — free 工作区规则

## 工作区定位

`free` 是一个轻量、自由的个人工作区，用于处理临时性、生活化、探索性的任务，例如：

- 写小爬虫；
- 抓取 RSS；
- 爬取或整理 GitHub 内容；
- 处理日常文件、表格、文本；
- 写一次性脚本或小工具。

这个目录不是正式科研课题目录，不需要默认建立复杂的 `docs/`、`config/`、`src/`、`results/` 等结构。除非任务明显变复杂，否则保持简单。

## 核心原则

1. 优先简单直接，避免过度工程化。
2. 能一个脚本解决的，不拆成多个模块。
3. 能一个 README 说明的，不建立 docs 目录。
4. 能命令行参数解决的，不额外写复杂配置系统。
5. 能本地临时运行的，不默认做服务化、守护进程或定时任务。
6. 不为了“规范”而创建空目录。
7. 每个小任务完成后，要留下清楚的运行方式和输入输出说明。

## 默认目录风格

对于简单任务，优先使用扁平结构，例如：

```text
free/
  AGENTS.md
  github_rss.py
  rss_fetch.py
  notes.md
  requirements.txt
````

只有在满足以下情况时，才创建子目录：

* 文件数量明显增多；
* 任务会反复维护；
* 有多个脚本共享同一批数据；
* 输入、输出、中间文件需要分开管理；
* 项目已经从“一次性脚本”变成“小工具”。

可选的轻量目录如下：

```text
free/
  task_name/
    README.md
    main.py
    requirements.txt
    data/
    output/
```

不要默认创建以下目录，除非确实需要：

```text
docs/
config/
src/
tests/
results/
logs/
notebooks/
```

## 命名规则

文件名应能直接说明用途，优先使用小写、下划线：

```text
github_trending_rss.py
fetch_papers.py
clean_csv.py
rename_files.py
```

长期保留的小工具应去掉日期，使用稳定名称。

## 编程规则

默认优先使用 Python，除非用户明确要求其他语言。

写脚本时应做到：

* 顶部写简短注释说明用途；
* 提供清楚的运行命令；
* 使用 `argparse` 处理必要参数；
* 网络请求设置 timeout；
* 爬虫或 API 请求要考虑限速；
* 不把 token、cookie、密码写进代码；
* 使用环境变量或 `.env` 保存敏感信息；
* 输出文件不要覆盖重要文件，除非用户明确允许；
* 对危险操作先打印计划，再执行。

简单脚本不需要复杂包结构。不要为了一个脚本创建 `src/`。

## 依赖管理

只有确实需要第三方库时，才创建 `requirements.txt`。

不要为了很小的任务引入重量级框架。

优先使用标准库。比如：

* `pathlib`
* `json`
* `csv`
* `argparse`
* `subprocess`
* `datetime`
* `urllib`
* `sqlite3`

如果需要网络请求，可以使用：

```text
requests
feedparser
beautifulsoup4
```

如果需要浏览器自动化，再考虑：

```text
playwright
selenium
```

但不要默认使用浏览器自动化，优先尝试 RSS、API、静态 HTML。

## 数据与输出

小任务可以直接在当前目录生成输出文件，例如：

```text
github_repos.csv
rss_items.json
output.md
```

如果输出文件较多，再建立：

```text
output/
```

下载的原始数据较多时，再建立：

```text
data/
```

临时文件可以放在：

```text
tmp/
```

大型中间文件、缓存文件、压缩包、数据库文件不要随意提交到 git。

## README 规则

简单脚本不强制写 README。

如果一个任务有以下任一情况，应写一个简短 `README.md`：

* 需要多步运行；
* 需要 API token；
* 有输入输出文件；
* 以后可能复用；
* 目录中超过 3 个相关文件。

README 只需要包含：

```text
# 任务名

用途：

运行：

输入：

输出：

注意事项：
```

不要写长篇文档。

## Git 与版本控制

不要自动执行 `git commit`、`git push`、`git reset --hard`、`git clean -fd` 等操作，除非用户明确要求。

在执行任何可能删除、覆盖、移动大量文件的命令前，必须先说明计划并等待确认。

优先建议维护一个 `.gitignore`，忽略：

```text
__pycache__/
*.pyc
.env
tmp/
data/
output/
*.log
*.sqlite
*.db
```

但如果某个输出文件是最终成果，可以保留。

## 安全规则

在执行命令前，先确认当前目录，避免误操作其他课题目录：

```bash
pwd
ls
```

不要修改 `cold_stress/`、`anno/`、`gpt/`、`TSS-Seq/` 等其他课题目录，除非用户明确要求。

不要删除用户已有文件。

不要覆盖同名文件，除非已经确认。

不要把敏感信息写入代码、README 或日志。

网络爬取时要尊重网站限制，不进行高频请求。

## Codex 工作方式

Codex 在 `free` 目录下工作时，应优先：

1. 理解当前任务目标；
2. 查看当前目录文件；
3. 判断是否能用单文件脚本解决；
4. 只创建必要文件；
5. 给出清楚的运行命令；
6. 简要说明结果文件在哪里；
7. 不主动扩大项目结构。

默认不创建复杂工程结构。

当任务只是一次性处理，优先生成：

```text
task_name.py
```

当任务可能复用，生成：

```text
task_name.py
README.md
requirements.txt
```

当任务变复杂，再升级为：

```text
task_name/
  README.md
  main.py
  requirements.txt
  data/
  output/
```

## 判断是否需要复杂结构

只有满足以下至少两个条件时，才考虑建立独立目录或更正式结构：

* 代码超过 300 行；
* 有多个功能模块；
* 有多个输入输出文件；
* 需要长期维护；
* 需要配置文件；
* 需要测试；
* 需要多人协作；
* 会反复运行或部署。

否则保持扁平、轻量、可读。

```
