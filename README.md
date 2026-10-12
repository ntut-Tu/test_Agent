# Codebase analysis

This package analyzes Java/Spring/Maven PRs and merge requests. It reads remote source, Jenkins coverage, existing tests, and optional per-test invocation traces. Java AST analysis maps uncovered patch lines to methods. Observed test callers are retained as evidence; LangChain explains coverage gaps and recommends test contexts for methods without observed callers. Jenkins submits completed builds to the FastAPI controller through shared Traefik. A persistent worker runs a checkpointed LangGraph through `CodebaseAnalysisAgent`; shell scripts provide deployment, setup, local tests, and live collection checks.

功能設計與實作報告：

- [Coverage 缺口分析](structure/coverage-analysis.md)
- [Existing Tests 上下文分析](structure/existing-tests-analysis.md)

## Structure

實際目錄、模組職責、依賴關係、物件組裝與執行流程見
[目前專案架構](structure/README.md)。

```text
AGENTS.md / BACKLOG.md      工作規則、PBI 與驗收紀錄
structure/                 目前架構、功能報告、部署與 artifact 契約
scripts/                   安裝、測試、smoke、服務與部署入口
deploy/ / Dockerfile        本專案的容器及共用 Traefik 路由
values.yaml                使用者設定與 secrets（不進 Git）
src/codebase_analysis/
  server.py / controller.py ASGI 生命週期與 HTTP 入口
  bootstrap.py             依賴組裝與固定 build URLs
  settings.py              YAML 設定載入與驗證
  interfaces.py            收集與模型分析的 Protocol
  collection.py            確定性證據收集
  workflow.py              LangGraph 流程、checkpoint 相容性與恢復
  tasks.py / worker.py     任務協調與背景執行
  smoke.py                 非 LLM 檢查流程
  nodes/                   三個 LLM 分析操作與輸入整理
  prompts/                 各操作的提示
  tools/                   擷取工具的薄入口
  lib/clients/             對外服務通訊
  lib/parsers/             回應與檔案格式解析
  lib/rules/               純規則、比對與驗證
  models/                  程式內 dataclass 資料型別
  schemas/                 HTTP、LLM 與 artifact 邊界契約
  repositories/            任務儲存介面與 SQLite
tests/                     行為、HTTP、儲存、基準與依賴邊界驗證
```

維持單一 Python 套件，以元件類型分類。`tools` 組合內部 `lib`，
`nodes` 組合提示、schema 與模型 client，`workflow` 決定順序。
目前使用 LangGraph 固定流程；HTTP service 將 checkpoint 存在既有資料 volume。
`retry` 恢復同一 generation，`restart` 建立新 generation；詳見 [執行與恢復契約](structure/langgraph-execution.md)。

[BACKLOG.md](BACKLOG.md) 保存 PBI 的價值、範圍、順序、驗收條件、狀態與證據；
[AGENTS.md](AGENTS.md) 指示接續工作時讀取並更新。後續指定 PBI 編號即可，列入待辦不代表授權實作。

## 設定與腳本

在專案根目錄執行：

```bash
./scripts/setup.sh
```

腳本使用 `uv sync --locked` 安裝環境，並在缺少 `values.yaml` 時從範本建立檔案（權限 `600`）；重複執行會保留既有設定。腳本可從其他工作目錄以絕對路徑執行。

直接編輯根目錄的 `values.yaml`：

- `llm`：provider、model、api_key，以及 provider 專用的 `options`。
- `code_host`：GitLab／GitHub、repository、API URL 與 token。
- `jenkins`：coverage artifact URL、`metadata_url`、可選 `trace_url`、username 與 api_token。
- `analysis`：擷取測試檔案的數量上限。
- `service`：controller token、路徑前綴、任務資料目錄與佇列上限。
- `deployment`：Docker context、共用 Traefik 與 Jenkins 網路。

這是 YAML 設定檔；部署腳本直接讀取其中設定，不使用 Helm template。`values.example.yaml` 僅保留空白 secret；實際填寫的 `values.yaml` 已加入 `.gitignore`。

已包含 Gemini 的 `langchain-google-genai`，provider 填 `google_genai`。若改用其他供應商，以 `uv add <對應整合套件名稱>` 安裝其 LangChain 套件。`llm.options` 會傳給 [`init_chat_model`](https://reference.langchain.com/python/langchain/chat_models/base)，參數名稱依 provider 而定；需要不同憑證參數的 provider 也可在此填寫。模型需支援目前使用的 `with_structured_output`。

既有服務可用明確的設定檔路徑組裝 agent；PR／MR 編號由呼叫端提供：

```python
from codebase_analysis.bootstrap import build_agent
from codebase_analysis.settings import load_settings

settings = load_settings("/path/to/project/values.yaml")
agent = build_agent(settings)
result = agent.run(42)
```

`result.context.focal_methods` 提供缺口方法與原始碼；
`result.findings.existing_tests` 現在回傳 `TestContext`，可從 `item.test.path`、
`item.test.source`、`item.test.file_context` 取得測試位置、方法與宣告檔案，
`item.evidence` 區分 `dynamic` 與 `llm`。

Jenkins 尚無 profiler 時，`trace_url` 留為 `null`。Agent 仍可建立 LLM 推薦，
但沒有動態呼叫證據；此時必須提供 `metadata_url` 以核對 coverage 版本。
Metadata 或 trace 至少一項必須通過 commit 與 XML SHA-256 驗證，才能進行行號比對。
Metadata 格式與 Jenkins 接入見 [coverage 報告](structure/coverage-analysis.md)；trace 格式見
[trace 契約](structure/existing-tests-analysis.md)。

執行測試：`./scripts/test.sh`。測試使用替身，不需要填入真實 secret 或呼叫遠端服務。

## 遠端 smoke test（不呼叫 LLM）

填好根目錄 `values.yaml` 的 `code_host`、`jenkins`、`analysis` 後執行，
將 `42` 換成要檢查的 PR 編號或 GitLab MR IID：

```bash
./scripts/smoke-test.sh 42
# 也可指定另一份設定檔；相對路徑以執行時的工作目錄為準
./scripts/smoke-test.sh 42 --values /path/to/values.yaml
```

此腳本使用正式 HTTP adapter，實際檢查：

1. 設定所選的 GitLab 或 GitHub：取得 PR／MR metadata 與 diff。
2. Jenkins：下載並解析指定 build 的 coverage XML。
3. Repo：從 PR／MR 的來源 commit 擷取既有測試，遵守 `max_test_files`。
4. Coverage：將解析結果與變更路徑、新增行進行比對。
5. Java：讀取缺口方法的 source 並解析方法及測試上下文。
6. Trace：有配置時下載、解析並核對 commit 與 coverage artifact 雜湊。

`llm` 區段可留空或省略，不會初始化模型。腳本只讀取資料，不執行 repo 內的測試、
不觸發 Jenkins build。請將 coverage URL 指向與待檢查 PR／MR 對應的 build；
`coverage_binding` 核對 metadata 或 trace 宣告的 revision 與 XML 雜湊；
缺少或不符時顯示 FAIL 並跳過 coverage_match。trace 未配置仍會顯示 WARN。

每項輸出 `PASS`、`WARN`、`FAIL` 或 `SKIP`。Coverage 無資料、找不到測試候選、
或 coverage 路徑無法對應時會顯示 `WARN` 與數量，供判斷資料是否符合預期。
獨立項目會繼續執行；缺少前置資料的項目顯示 `SKIP`。

- Exit code `0`：所有可執行項目完成，可能包含資料不足的警告。
- Exit code `1`：至少一項失敗或因前置失敗而略過。
- Exit code `2`：參數或設定有誤。

輸出不列印 secret、原始遠端回應或含認證資訊的 URL。

## 程式文件（docstring）

公開類別與函式使用 Google style docstring，說明用途，並依需要包含
`Args`、`Returns`、`Yields`、`Raises` 或 `Attributes`。型別由 Python type hints
表達；文件補充參數含義、單位、限制與例外條件。

可在 IDE 查看說明，或用 Python 內建的 `help()`／`pydoc` 查閱：

```bash
uv run python -m pydoc codebase_analysis.workflow
uv run python -m pydoc codebase_analysis.settings
```

更新公開介面時，同步更新相應 docstring。

## Import 風格

由 `pyproject.toml` 的 Ruff 設定統一管理 `src/`、`tests/`、`scripts/`：

1. 有使用 `from __future__` 時放在最前面（module docstring 之後）。
2. 依序排列標準庫、第三方套件、專案模組；各組之間空一行。
3. 每組先放 `import ...`，再放 `from ... import ...`，由 Ruff 排序。
4. 專案內統一使用絕對匯入，例如 `from codebase_analysis.models.pull_request import PullRequest`。
5. 過長的匯入清單以括號分行；不使用 `import *`，移除未使用的匯入。

Ruff 是 uv 的開發依賴，`./scripts/setup.sh` 會一併安裝。
排序與分組規則參考 [Ruff 設定文件](https://docs.astral.sh/ruff/settings/)。

```bash
# 檢查匯入規則
uv run ruff check src tests scripts
# 自動整理排序與可安全修正的問題
uv run ruff check --fix src tests scripts
```

## Java trace producer spike

Java producer 位於 `/home/mo/Documents/PDD/jenkins-pipelines/tools/java-test-trace/`，
由 Jenkins agent 或 sandbox 的測試 JVM 載入。它獨立產生 coverage 與 trace JSON，
不依賴本 Python 專案；LLM Agent pod 僅下載、解析與分析 artifacts。

此專案保留開發期的唯讀 consumer 相容性檢查：

```bash
./scripts/verify-trace-spike.sh /下載解壓路徑/tools/java-test-trace/spike-fixture
```

先依報告在 Jenkins 執行 `pdd/java-trace-spike`，下載該 build 全部 artifacts 並保留目錄結構。
Job DSL／Jenkinsfile 已備妥，尚待發布來源並執行 seed；目前尚無 Jenkins spike 執行結果。
Consumer 指令只使用 uv／Python，不啟動 JVM 或重新產生 trace。
PR #31／Jenkins build #7 已產生真實 trace，Agent 容器已完成下載、綁定與 Gemini 分析驗證；trace 的 `complete=false` 表示部分追蹤。詳見 [設計與結果報告](structure/java-trace-spike.md)。


## HTTP controller 與容器

Jenkins 透過共用 Traefik 的 `/test-agent/analyses` 提交 build 身分。
Controller 回傳任務 ID；worker 自動下載該 build 的 coverage／trace、核對版本並執行三個 LLM 分析。
任務與 LangGraph checkpoint 以 SQLite 保存於 container volume，相同請求重送沿用既有任務。
被程序中斷的 running 任務在 worker 啟動時恢復；一般失敗需明確 retry。
本機程式的 PBI-002 改動尚未部署到既有 Agent 容器。

部署程式、Dockerfile 與 Traefik 路由均放在本專案。
設定、API、Jenkins 接線、部署方式與限制見 [controller 與部署說明](structure/controller-deployment.md)。
