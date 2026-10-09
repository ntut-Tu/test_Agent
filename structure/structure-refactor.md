# PBI-001：架構重整與驗證

日期：2026-10-09。對應原待辦第 1 項（保存基準）與第 2 項（架構重整）。

## 交付

- 按元件類型區分 nodes、prompts、tools、models、schemas、repositories 及 lib 下的 clients／parsers／rules。
- 將原本同一個類別內的三個模型操作、提示與 provider 呼叫拆開；由 `AnalysisNodes` 組合共用 `LangChainClient`。
- 將遠端認證、URL、分頁、tree／blob 讀取放入 clients；格式正規化放入 parsers；篩選、排序及比對放入 rules。
- tools 保留一次擷取操作的協調，collection 保留證據收集，workflow 保留分析順序。
- HTTP controller、任務協調、持久化及 worker 生命週期分開。沒有增加 service 層或拆成多個 Python 專案。

完整現況見[架構文件](README.md)。

## 引用遷移

公開的 `codebase_analysis` 套件匯出、`bootstrap.build_agent()`、`bootstrap.build_collector()`、
`server.create_app()` 維持；HTTP 路由、設定欄位、SQLite schema 與輸出資料欄位維持。
舊的內部模組路徑已移除，直接引用它們的呼叫端需要調整：

| 舊位置 | 新位置 |
| --- | --- |
| `application/agent.py` | `collection.py`、`workflow.py` |
| `application/ports.py` | `interfaces.py` |
| `application/jobs.py` | `tasks.py`、`repositories/base.py` |
| `application/smoke.py` | `smoke.py` |
| `domain/models.py`、`context.py`、`trace.py` | `models/` 資料型別；規則至 `lib/rules/` |
| `domain/coverage.py`、`paths.py`、`validation.py` | `lib/rules/`；CoverageMatch 至 `models/coverage.py` |
| `domain/jobs.py` | `models/task.py` |
| `infrastructure/settings.py` | `settings.py` |
| `infrastructure/jobs/` | `repositories/sqlite.py`、`worker.py`；build 設定至 `bootstrap.py` |
| `infrastructure/code_hosts/`、`coverage/`、`source/`、`trace/` | `tools/` 入口、`lib/clients/`、`lib/parsers/`、`schemas/` |
| `infrastructure/llm/langchain.py` | `nodes/`、`prompts/`、`schemas/llm.py`、`lib/clients/langchain.py` |
| `presentation/http/` | `controller.py`、`schemas/http.py` |

例如：

```python
from codebase_analysis.bootstrap import build_agent
from codebase_analysis.settings import load_settings

agent = build_agent(load_settings("values.yaml"))
```

`schemas/llm.py` 暫時保留既有 `_PrSummary` 等 class 名稱，因為它們會影響 structured output 的 schema title／參照名稱。
這次保留模型契約；後續若調整 schema，需明確更新基準與相容策略。

## 基準與驗收證據

原始基準 commit：`68093ed871997d025be3ca36ae342036a4fd5756`。

| 驗證 | 結果 |
| --- | --- |
| 重整前完整本機測試 | 50 項通過 |
| 重整後完整本機測試 | 51 項通過，包含 HTTP、SQLite、worker、工具與 smoke 的替身測試 |
| 合成案例基準 | 收集資料、三次模型訊息、JSON schema、結果序列化後逐字一致 |
| 依賴邊界 | 改為檢查實際新元件，缺少目錄會失敗；限制 lib 反向依賴與純規則的框架引用 |
| Ruff | 既有 import 規則及另行檢查 F821 通過 |
| Wheel | `uv build --wheel` 成功；64 個 Python 檔案與 source 逐一比對相同，並全部從 wheel 成功匯入 |
| 操作入口 | smoke `--help`、workflow `pydoc` 成功；scripts 的 import 已更新 |
| 差異檢查 | `git diff --check` 通過 |

可重跑：

```bash
./scripts/test.sh
uv run --locked ruff check src tests scripts
uv run --locked python -m unittest tests.test_analysis_baseline tests.test_architecture -v
uv build --wheel
```

合成基準：`tests/fixtures/analysis_before_refactor.json`。
SHA-256：`64277015b34e529da00c572100c7f708ff35aa117321c69da9cd8c4bc3a1b220`。
這個基準在重整前產生；測試不會自動覆寫它。

本機 `.state/baselines/structure-refactor/` 另保存原始碼、前後測試記錄、manifest，
以及先前 PR #31／Jenkins build #7 的真實分析結果。真實結果是既有資料的保存，這次沒有重新呼叫 Gemini。
`.state` 已排除版本控制；可提交的 fixture 僅含合成資料。

## 驗證範圍

初次驗收涵蓋本機行為與套件完整性；後續補跑的遠端 smoke 結果如下。未部署新版 Agent 容器或測量 LLM 回答品質。
目前 prompt、候選上限、呼叫順序、dynamic／llm 判定沿用既有行為。
LangGraph、限流、觀測、Uncovered 品質改進留在後續 PBI。


## 補充：實際遠端 Smoke Test

2026-10-09 使用根目錄 `values.yaml` 執行 `./scripts/smoke-test.sh 31`。
初次遠端檢查發現 Jenkins 無法連線；確認 `desktop-linux` 的現有容器均停止後，
啟動 `pdd-jenkins-controller-1`，待 HTTP 就緒後重跑，**exit code 0**。
此次僅啟動既有 Jenkins controller，未重建映像，未啟動其他容器，未呼叫 LLM。

| 檢查 | 結果 |
| --- | --- |
| configuration | PASS |
| pr_fetch | PASS；changed_files=3 |
| coverage_fetch | PASS；coverage_files=212 |
| trace_fetch | WARN；tests=3、complete=False |
| trace_binding | PASS；revision 與 coverage artifact 一致 |
| coverage_binding | PASS；PR head 與 coverage SHA-256 一致 |
| existing_tests | PASS；retrieved=1、candidates=1、truncated=False |
| coverage_match | PASS；uncovered_lines=22、unmatched_paths=0、missing_patches=0 |
| java_context | PASS；focal_methods=7、test_declarations=4、unassigned_lines=0 |

Trace 的 WARN 表示 producer 宣告追蹤不完整；下載及版本綁定成功。
