# Existing Tests 上下文分析：設計與實作報告

## 1. 目的與輸出

針對含 coverage 缺口的 Java 方法，找出可供補測試時參考的既有測試方法，
並保留其所在檔案的 imports、Spring 設定、class 欄位、setup 與 helpers。

例如 `ShippingService.fee(amount, express)` 的 express 分支未覆蓋，但
`ShippingServiceTest.regularShipping()` 已執行一般分支。
這個測試可以提供服務初始化與斷言寫法；它呼叫目標方法，不代表已覆蓋缺口。

每筆輸出為 `TestContext`：

| 欄位 | 內容 |
| --- | --- |
| `focal_id` | 缺 coverage 的 production 方法唯一識別 |
| `test` | 既有測試方法的 `SourceMethod`，含路徑、class、參數、行號、方法內容、完整宣告檔案 |
| `evidence` | `dynamic`：有 trace 呼叫證據；`llm`：模型推薦 |
| `reason` | 對應原因 |

原本 `LlmFindings.existing_tests` 的檔案路徑 tuple，已改為 `tuple[TestContext, ...]`。
呼叫端若要取路徑，使用 `item.test.path`；完整測試檔案內容為 `item.test.file_context`。

## 2. 方法與原文的關係

論文 §3.1.3／Algorithm 1 結合候選檔案選擇、動態呼叫分析，以及沒有呼叫者時的
LLM fallback，最後擷取測試周邊上下文。本專案使用 Java source AST，動態紀錄
由 Jenkins 提供，Agent 不執行目標 repo 的程式。
參考：[Change And Cover，§3.1.3 與 Algorithm 1](https://arxiv.org/pdf/2601.10942#page=5)。

目前候選檔案由路徑規則與變更檔案排序；LLM fallback 直接在方法級候選中選擇。
沒有額外複製論文的 LLM 檔案選擇階段，也不在 Agent 重建完整 JVM call graph。

## 3. 已實作的流程

```text
coverage 缺口 → Java focal methods
                  ↓
讀取 Jenkins trace（若已配置）
  → 驗證 schema、commit、coverage SHA-256
  → 找出觀察到 focal method 的 test records
                  ↓
選擇測試候選檔案
  → 動態呼叫者路徑優先
  → PR 有修改測試檔時採用該組候選
  → 否則依測試命名／路徑及變更檔名相關性排序
  → 遵守 max_test_files
                  ↓
從同一 source commit 讀取測試檔並解析 Java methods
                  ↓
有可解析的 trace caller → dynamic TestContext
沒有 caller 的 focal method → LLM 推薦 → llm TestContext
                  ↓
驗證 ID、方法內容與 evidence，回傳兩類上下文
```

### 靜態候選

支援 Maven `src/test/`、`src/it/` 下的 Java 檔案，以及常見 `Test*`、`*Test`、
`*Tests`、`*IT`、`*ITCase` 命名；`src/main/java/` 優先判定為 production。
完整來源以 GitHub／GitLab API 讀取，包含 fork，固定在 PR／MR 的 source SHA。

標準測試候選辨識 JUnit `Test`、`ParameterizedTest`、`RepeatedTest`、`TestFactory`、
`TestTemplate`、`Theory` annotation，以及直接繼承 `TestCase` 的 `test*` 方法。
動態 trace 指定的可解析方法不要求符合這些 annotation 名稱。
自訂 Maven source roots、跨層繼承與 meta-annotation 的完整語意解析尚未支援。

### 動態證據

每筆 trace record 必須保留「哪一個測試」的身份，並列出在該測試執行範圍內
觀察到的直接／間接呼叫。Agent 使用 path、class、method name、source line 比對。
不能把整個 suite 的呼叫集合掛到每個測試，否則會產生錯誤對應。

### LLM fallback

僅針對尚無 dynamic context 的 focal method 呼叫 LLM。模型收到 PR diff、
標記缺口的方法內容、測試方法內容與宣告檔案前 12,000 字元，並看到截斷標記。
所選 `TestContext` 仍保存完整已讀取的宣告檔案，不用截斷片段取代它。

模型只能選取提供的 focal／test identity。未知 ID 會拒絕；領域驗證也禁止
模型自行宣稱 dynamic evidence，或丟棄已有的 dynamic context。
沒有候選或模型不選取時，該 focal method 保持沒有對應，不虛構結果。

## 4. Jenkins trace artifact 契約

契約檔案：

- [JSON Schema](contracts/java-test-trace.schema.json)
- [完整範例](contracts/java-test-trace.example.json)：合成測試資料，不是真實 build。

`values.yaml` 以 `jenkins.trace_url` 指向 JSON artifact，沿用 Jenkins 的認證。
未配置時必須由 `metadata_url` 提供 coverage 版本證據，才可繼續做 LLM 推薦；
coverage metadata 本身不提供 test-to-method 執行證據。配置 trace 後下載失敗、格式錯誤或版本
不一致會中止完整分析，不把失敗悄悄解讀成「沒有呼叫者」。

| 欄位 | 要求 |
| --- | --- |
| `schema_version` | 整數 `1` |
| `revision` | 被測原始碼完整 commit SHA，40 或 64 位小寫 hex |
| `coverage_sha256` | 同版本 coverage XML 原始 bytes 的 SHA-256 |
| `build_id` | 可辨識 build 的字串，不放認證 URL／secret |
| `scope` | 實際測試範圍，例如 Maven profile、module、Surefire／Failsafe 選擇 |
| `complete` | Producer 是否完整捕捉宣告 scope 內的呼叫，布林值 |
| `tests` | Per-test records，每筆有 `test` 與 `calls` |

`test` 與每筆 `calls` 的 source reference 都包含：

```json
{
  "path": "src/main/java/demo/ShippingService.java",
  "class_name": "demo.ShippingService",
  "name": "fee",
  "line": 3
}
```

`path` 必須是 repo-relative `.java` 路徑，不能包含 `..`、絕對路徑或 Windows drive。
`class_name` 使用 source-qualified 名稱，巢狀類別以 `.` 分隔。
`line` 是**被呼叫方法內的行號**，不是呼叫端的 call-site 行號；用來區分 overload。
Constructor 的 `name` 使用 source 類別名稱。
同一測試的多個參數化 invocation 可分成多筆記錄，Agent 對方法對應去重。

`complete: false` 的已觀察正向證據仍可使用；沒有紀錄不能解釋成從未呼叫。
即使 `complete: true`，也只代表宣告 scope，不代表整個 repo 的全部測試。

## 5. Jenkins producer 自動接入與驗證狀態

已完成 Agent 端契約與解析，以及經使用者同意的 [Java trace spike](java-trace-spike.md)。
Spike 已驗證 Byte Buddy＋JUnit listener＋Spring HTTP 上下文傳遞。
`test-all-server` 已補上自動接入程式；每個 PR 由 poll 自動排入，不需逐次修改 POM 或填 URL。
程式已通過設定測試、Java 編譯與 Jenkinsfile linter；PR #31／Jenkins build #7 已產生 trace，Agent 已驗證下載、解析及版本綁定。
目前 producer 的責任與驗證條件如下：

1. 在正確 commit 執行 Java 測試，產生 coverage 與 per-test 呼叫紀錄。
2. 在測試執行環境呼叫 Java finalizer，傳入真實 commit／build metadata；Python 端只讀取產物。
3. 正確標記測試邊界，避免平行測試、非同步工作或 Spring 背景執行緒被歸到錯誤測試。
4. 將 JVM class／method 位置轉成正確 module、source file、class name 與方法行號。
   不能把 Spring proxy 或合成方法的名稱直接冒充 source 方法。
5. 填寫 source revision、實際測試範圍與完整性；計算歸檔 XML 的 SHA-256。
6. 將 XML 與 JSON 保存為同 build 的可下載 artifact。

可在 Jenkins 歸檔已產生的檔案，例如：

```groovy
archiveArtifacts artifacts: 'agent-analysis/jacoco.xml,agent-analysis/java-test-trace.json',
                 allowEmptyArchive: false
```

這段只負責保存檔案，不會產生 trace。已完成的 spike 範圍與結果見上述報告；新增 spike 仍須先確認。
參考：[Jenkins artifact 歸檔](https://www.jenkins.io/doc/pipeline/steps/core/#archiveartifacts-archive-the-artifacts)。

## 6. 程式位置

| 責任 | 程式位置（相對於 `src/codebase_analysis/`） |
| --- | --- |
| Java AST、annotation 與方法範圍 | `lib/parsers/java.py` |
| 候選檔案與遠端內容 | `tools/existing_tests.py`、`lib/rules/selection.py` |
| Trace 下載與嚴格 schema 驗證 | `tools/trace.py`、`lib/parsers/trace.py`、`schemas/trace.py` |
| Trace／method／test context 資料型別 | `models/trace.py`、`models/source.py` |
| 依測試身份建立動態對應 | `lib/rules/context.py` → `dynamic_contexts()` |
| 收集、優先擷取 caller、來源版本核對 | `collection.py`、`workflow.py` |
| LLM fallback | `nodes/existing_tests.py` |
| 證據與模型引用驗證 | `lib/rules/validation.py` |

## 7. 驗證與限制

本機案例涵蓋 Java overload／巢狀 class、Spring 宣告檔案保留、per-test 身份隔離、
dynamic context 不呼叫 LLM 選擇、LLM 未知 ID 拒絕、動態證據不可偽造／丟棄、
trace schema／revision／coverage digest 驗證。

`max_test_files` 仍限制擷取範圍；被截斷或無法對應 source 的 trace caller 不會變成
dynamic context。結果保留候選總數、截斷狀態與原始 normalized trace 供判斷。

完整宣告檔案包含同檔案的 setup／helper，但尚未遞迴展開其他檔案的基底測試類別、
Spring configuration 或外部 helper 實作。Lambda、合成方法、無法還原 source 的
proxy 呼叫需由 producer 正規化或標示資料不完整。

PR #31／Jenkins build #7 的真實 trace 含 3 筆 test 記錄，`complete=false`。
2026-10-09（台灣時間）Agent 容器完成 Gemini 分析，取得 1 個候選測試檔案、4 個測試宣告。
這份 trace 沒有對應到 7 個缺口方法的 dynamic context，結果包含 1 筆 `evidence=llm` 的測試推薦。
這是模型推薦，不能當作已觀察到的測試呼叫；trace 下載成功也不表示覆蓋或呼叫追蹤完整。
Controller 與容器的實測結果詳見 [部署說明](controller-deployment.md)。
