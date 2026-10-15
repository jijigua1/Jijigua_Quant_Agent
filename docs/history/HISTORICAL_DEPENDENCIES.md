# 历史依赖与公开候选安全适配

以下为采集快照/初始可复现环境，不是新安装推荐。原始源码与SHA仍可追溯；公开安装入口已使用修复版本，数值库NumPy/Pandas/Matplotlib保持不变。公告匹配不是本项目可利用性证明。

## requirements.lock（适配前）

```text
# Validated on CPython 3.12.4 / Windows 11 and 3.11.10 / GPUShare Linux.
# Install into a dedicated venv. These pins include runtime, tests and wheel tooling.
jsonschema==4.19.2
attrs==24.2.0
jsonschema-specifications==2023.7.1
referencing==0.30.2
rpds-py==0.10.6
pytest==7.4.4
iniconfig==1.1.1
packaging==26.0
pluggy==1.0.0
colorama==0.4.6; sys_platform == "win32"
setuptools==69.5.1
wheel==0.43.0
```

## requirements-research.lock（适配前）

```text
# Reviewed numerical dependencies; installed only into Agent's dedicated venv.
numpy==1.26.4
pandas==2.3.3
matplotlib==3.8.4
contourpy==1.2.1
cycler==0.12.1
fonttools==4.51.0
kiwisolver==1.4.5
pillow==10.3.0
pyparsing==3.1.2
python-dateutil==2.9.0.post0
pytz==2024.1
tzdata==2024.1
six==1.16.0
```

## requirements-paper.lock（适配前）

```text
# Optional document parsers. Review PyMuPDF AGPL/commercial licensing before redistribution.
PyMuPDF==1.24.14
beautifulsoup4==4.12.3
soupsieve==2.5
python-docx==1.2.0
lxml==5.2.1
typing_extensions==4.11.0
```

## pyproject.toml（适配前）

```text
[build-system]
requires = ["setuptools==69.5.1"]
build-backend = "setuptools.build_meta"

[project]
name = "wty-research-agent"
version = "0.8.2"
description = "Model independent research core with controlled development API and read-only data tools"
requires-python = ">=3.11"
dependencies = ["jsonschema==4.19.2"]

[project.optional-dependencies]
test = ["pytest==7.4.4"]
parquet = ["numpy==1.26.4", "pyarrow==14.0.2"]
research = ["numpy==1.26.4", "pandas==2.3.3", "matplotlib==3.8.4"]
paper = ["PyMuPDF==1.24.14", "beautifulsoup4==4.12.3", "python-docx==1.2.0"]

[project.scripts]
qra = "research_agent.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
research_agent = ["resources/*.toml", "resources/*.json", "resources/skills/*/*.md", "resources/skills/*/*.toml", "resources/skills/*/*.json", "resources/visuals/*.js", "resources/visuals/*.txt"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"
```
