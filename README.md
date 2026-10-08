# Codebase analysis

This package analyzes Java/Spring/Maven PRs and merge requests. It reads remote source, Jenkins coverage, existing tests, and optional per-test invocation traces. Java AST analysis maps uncovered patch lines to methods. Observed test callers are retained as evidence; LangChain explains coverage gaps and recommends test contexts for methods without observed callers. The surrounding workflow calls `CodebaseAnalysisAgent`; shell scripts provide setup, local tests, and live collection checks.

功能設計與實作報告：

- [Coverage 缺口分析](structure/coverage-analysis.md)
- [Existing Tests 上下文分析](structure/existing-tests-analysis.md)

## Structure

實際目錄、模組職責、依賴關係、物件組裝與執行流程見
[目前專案架構](structure/README.md)。

```text
structure/
  README.md                current project architecture
  coverage-analysis.md     coverage design and implementation report
  existing-tests-analysis.md  test-context design and implementation report
  contracts/               Jenkins coverage/trace schemas and trace example
values.example.yaml        versioned configuration template
values.yaml                user configuration and secrets (ignored by Git)
scripts/
  setup.sh                 install locked dependencies and create missing values.yaml
  test.sh                  run tests
  smoke-test.sh            live remote checks without LLM calls
  smoke_test.py            smoke-test argument parsing and output formatting
src/codebase_analysis/
  bootstrap.py             composition root for configured concrete dependencies
  domain/
    models.py              normalized data types
    context.py             Java methods, focal methods, and test contexts
    trace.py               per-test evidence and revision/artifact verification
    paths.py               Maven Java source-role conventions
    coverage.py            coverage and changed-line matching
    validation.py          validate model findings against collected evidence
  application/
    agent.py               collection and three LLM operations, composed via interfaces
    smoke.py               independent checks of the collection capabilities
    ports.py               tool and model interfaces
  infrastructure/
    settings.py            YAML loading, validation, and secret fields
    http.py                HTTP transport
    errors.py              remote integration errors
    code_hosts/
      api.py               shared GitHub / GitLab API access
      pr_fetch.py          PR / MR retrieval
      test_retriever.py    remote existing-test retrieval
    coverage/
      jenkins.py           Jenkins artifact retrieval
      metadata.py          coverage provenance contract
      xml.py               JaCoCo / Cobertura normalization
    source/
      java.py              Java AST declarations and declaring-file context
      repository.py        source retrieval at the PR/MR commit
    trace/
      jenkins.py           versioned per-test Java trace artifact
    llm/
      langchain.py         structured model calls for the three green operations
tests/                     behavior and dependency-boundary tests
```

The domain depends only on the standard library. The application depends on the domain and its own interfaces. Infrastructure implements those interfaces; callers compose the concrete dependencies. Coverage crosses the application boundary as `CoverageReport`, and every model implementation's findings pass through the same domain validation.

Remote retrieval and parsing are deterministic infrastructure operations. Coverage intersections, method grouping and observed test associations are domain rules. LangChain provides PR summaries, coverage explanations and test-method recommendations where dynamic context is absent. The application coordinates these operations.

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

這是 YAML 設定檔，不包含 Helm template 或部署功能。`values.example.yaml` 僅保留空白 secret；實際填寫的 `values.yaml` 已加入 `.gitignore`。

選定模型供應商後，以 `uv add <對應整合套件名稱>` 安裝其 LangChain 套件。`llm.options` 會傳給 [`init_chat_model`](https://reference.langchain.com/python/langchain/chat_models/base)，參數名稱依 provider 而定；需要不同憑證參數的 provider 也可在此填寫。模型需支援目前使用的 `with_structured_output`。

既有服務可用明確的設定檔路徑組裝 agent；PR／MR 編號由呼叫端提供：

```python
from codebase_analysis.bootstrap import build_agent
from codebase_analysis.infrastructure.settings import load_settings

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
uv run python -m pydoc codebase_analysis.application.agent
uv run python -m pydoc codebase_analysis.infrastructure.settings
```

更新公開介面時，同步更新相應 docstring。

## Import 風格

由 `pyproject.toml` 的 Ruff 設定統一管理 `src/`、`tests/`、`scripts/`：

1. 有使用 `from __future__` 時放在最前面（module docstring 之後）。
2. 依序排列標準庫、第三方套件、專案模組；各組之間空一行。
3. 每組先放 `import ...`，再放 `from ... import ...`，由 Ruff 排序。
4. 專案內統一使用絕對匯入，例如 `from codebase_analysis.domain.models import PullRequest`。
5. 過長的匯入清單以括號分行；不使用 `import *`，移除未使用的匯入。

Ruff 是 uv 的開發依賴，`./scripts/setup.sh` 會一併安裝。
排序與分組規則參考 [Ruff 設定文件](https://docs.astral.sh/ruff/settings/)。

```bash
# 檢查匯入規則
uv run ruff check src tests scripts
# 自動整理排序與可安全修正的問題
uv run ruff check --fix src tests scripts
```
