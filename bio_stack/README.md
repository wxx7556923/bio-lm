# Bio Stack

用途：
统一放置本地 Bio 相关工作区，包括自动化情报雷达与本地 Python 运行环境。

目录结构：
- `bio_ai_radar/`：Bio-AI 科研情报雷达脚本与历史报告归档。
- `Bio-LLM/`：本地 Python 虚拟环境目录（venv），用于隔离依赖，不是业务源码。

本地运行（从仓库根目录执行）：
```bash
python bio_stack/bio_ai_radar/main.py --skip-email --archive-dir bio_stack/bio_ai_radar/reports
```

可选调试：
```bash
python bio_stack/bio_ai_radar/main.py --skip-ai --output bio_stack/bio_ai_radar/github_projects.json
python bio_stack/bio_ai_radar/main.py --dry-run
```

自动化说明：
- GitHub Actions workflow 位于 `.github/workflows/bio_radar.yml`。
- workflow 已配置在 `bio_stack/bio_ai_radar/` 下安装依赖并运行脚本。
- 每日报告会写入 `bio_stack/bio_ai_radar/reports/`，并自动提交回仓库。

注意事项：
- `Bio-LLM/` 仅供本地使用，建议不要提交到远端仓库。
- 敏感信息通过 GitHub Secrets 和本地 `.env` 管理，不写入代码。
