# Coverage 缺口分析：設計與實作報告

## 1. 範圍與目標

受測專案為 Java／Spring／Maven；Agent 本身以 Python 實作。
本功能重用 Jenkins 保存的 coverage XML，找出 PR／MR 新版本中變更且尚未被測試
執行的可執行行，再將缺口對應到 Java 方法，提供後續 LLM 分析。

論文 §3.1.1 使用 regression suite 的 coverage 找出 diff 缺口，再依目標函式整理
程式上下文；本專案將執行測試的責任放在 Jenkins，Agent 負責下載與分析。
參考：[Change And Cover，§3.1.1](https://arxiv.org/pdf/2601.10942#page=4)。

## 2. 已完成的處理流程

```text
PR/MR number
  → 取得 source commit SHA 與 diff
  → 下載 Jenkins coverage XML，計算原始 bytes 的 SHA-256
  → 解析 coverage 中的 executable / covered / uncovered 行
  → 以 coverage metadata 或 trace 核對 head SHA 與 XML SHA-256；缺少或不符即中止
  → 只處理 Java production 變更，排除 Maven 測試來源
  → 取 diff 新增行與 coverage 可執行行的交集
  → 取得該 source commit 的 Java 原始碼
  → Java AST 解析方法、建構子、overload 與巢狀類別
  → 將未覆蓋行分組到最小包覆方法
  → LLM 讀取標記 UNCOVERED 的方法程式碼，分析行為與測試需求
```

Git diff 中的「修改」在新版本側表現為新增行。因此以 diff 的 `+` 行計算
新增／修改位置；刪除行不列入新版本待補測試範圍。

### 計算定義

對每個能匹配報告且有 diff 的 production 檔案：

- `A`：diff 在新版本側新增的行。
- `E`：coverage 報告列出的可執行行。
- `U`：coverage 報告列出的未覆蓋行。
- 變更可執行行：`A ∩ E`。
- 待分析缺口：`A ∩ U`。
- 已覆蓋變更行：`(A ∩ E) − U`。

資料完整且分母大於零時，可用已覆蓋變更行數除以變更可執行行數。
目前回傳兩個計數，不把資料缺漏或零分母自動宣告為 100%。

## 3. Coverage 來源與重用條件

| Jenkins 現況 | 處理方式 |
| --- | --- |
| 已保存對應版本的逐行 XML | Agent 直接下載，不重跑測試 |
| 只保留原始 coverage 執行資料 | Jenkins 端轉出支援的 XML |
| 沒有收集／保存 coverage，或版本已變更 | Jenkins 重新執行需要的測試範圍並收集 |
| 只有彙總百分比或測試通過／失敗結果 | 不足以做逐行缺口分析 |

Jenkins 的 artifact 歸檔能力可保存 XML 供下載，保留時間取決於 build／artifact
保存策略。參考：[Jenkins archiveArtifacts](https://www.jenkins.io/doc/pipeline/steps/core/#archiveartifacts-archive-the-artifacts)。

`values.yaml` 範例：

```yaml
jenkins:
  artifact_url: "https://jenkins.example/job/project/42/artifact/reports/jacoco.xml"
  metadata_url: "https://jenkins.example/job/project/42/artifact/reports/coverage-metadata.json"
  trace_url: null
  username: "your-user"
  api_token: "your-token"
```

`metadata_url` 指向 [coverage metadata JSON 契約](contracts/coverage-metadata.schema.json)。
欄位為 `schema_version: 1`、`revision`、`coverage_sha256`、`build_id`、`scope`。
`revision` 是真正執行測試的 commit；XML 的 digest 由產生端與下載端分別計算。

`trace_url` 可以為 `null`。沒有 trace 時，metadata 仍能核對 coverage 版本；
沒有 metadata 時，可由同份 XML 的有效 trace 提供版本證據。兩者都存在時必須全部符合。
兩者都缺少、revision 不等於 PR head 或 digest 不符，完整分析會中止。
Smoke test 顯示 `coverage_binding: FAIL`，略過 coverage 比對；獨立的測試檔擷取仍繼續。

這個核對建立 artifact 之間的一致性；Jenkins 仍負責正確填寫 metadata，
並非密碼學上證明 Jenkins 確實執行了該版本。metadata 不等於 per-test trace，
也不代表所有測試通過。測試範圍保留在 `coverage_provenance.scope`。
若 Jenkins 測試的是合成 merge commit，不能直接把它標成 PR head SHA。

### 對接現有 Jenkins pipeline

`/home/mo/Documents/PDD/jenkins-pipelines/pipelines/github-pr-test.Jenkinsfile`
現在先在固定 PR head 執行 Maven／JaCoCo，保存
`agent-analysis/jacoco.xml`、`agent-analysis/coverage-metadata.json` 與 `agent-analysis/java-test-trace.json`，
再進行原有的合併後測試。Agent 讀取 head 報告，避免合併帶來的行號差異。

Maven 執行 `clean`、JaCoCo `prepare-agent`、`verify`、`report`，使用專案 POM 的測試範圍。
一般 assertion 失敗透過 JUnit 呈現為 UNSTABLE，仍可保存 coverage；
沒有產生有效 exec/XML、編譯或容器錯誤會失敗，不產生可用 metadata。
此 pipeline 針對目前的單一 Maven module；未加入任意多 module 的自動彙整。
JaCoCo 的 agent 透過 `argLine` 接入，若目標 POM 日後覆寫該值，須保留 agent 參數。
參考：[JaCoCo prepare-agent](https://www.jacoco.org/jacoco/trunk/doc/prepare-agent-mojo.html)、
[JaCoCo report](https://www.jacoco.org/jacoco/trunk/doc/report-mojo.html)。

使用 `pdd/test-all-server` 中同一個固定 build 的 URL：

```text
/job/pdd/job/test-all-server/<N>/artifact/agent-analysis/jacoco.xml
/job/pdd/job/test-all-server/<N>/artifact/agent-analysis/coverage-metadata.json
```

`<N>` 必須替換為實際 build number。不要使用舊的 `cloth-shop-api-test` 分支報告。
`lastSuccessfulBuild` 可能漏掉有效的 UNSTABLE coverage；latest alias 也可能在兩次下載間變動，
固定編號能避免這種情況。PR head 更新後，應選擇重新執行該 head 的 build。

## 4. 格式與路徑處理

| 格式 | 可執行行 | 未覆蓋判斷 |
| --- | --- | --- |
| JaCoCo XML | `mi + ci > 0` 的 line | `mi > 0` 且 `ci == 0` |
| Cobertura XML | 報告列出的 line | `hits == 0` |

同一路徑、同一行若有多筆資料，只要有命中紀錄就視為已覆蓋。
全覆蓋的檔案仍保留，與「報告沒有該檔案」分開處理。

路徑依序採用原始完整匹配、Maven `src/main/java` 正規化後匹配、唯一後綴匹配。
JaCoCo aggregate report 的 `group` 名稱會保留在路徑中，用於區分 module。
Group 名稱需能對應 repo 中的 module 路徑；模糊或無法匹配時列為 unmatched，
不把不同 module 的同名來源檔當成同一份 coverage。

目前聚焦 line coverage，未將部分命中的分支獨立建模為 branch coverage 缺口。

## 5. Java 函式上下文

使用 Tree-sitter Java grammar 解析 source commit 的原始碼，取得：

- Repository path、package 與巢狀 class 名稱。
- 方法／建構子名稱、參數宣告、起訖行與完整宣告內容。
- 保留 source parameter 宣告及起始行的唯一 `identity`，區分 overload。

同一行落在多個宣告範圍時，使用最小包覆方法；若最小範圍仍有歧義則不猜測。
不在可辨識方法內的未覆蓋行放入 `unassigned_uncovered_lines`，不交給方法級
測試上下文分析。語法解析失敗會回報錯誤，不使用 parser recovery 的部分結果。

LLM 可分析候選的語意；收集到的未覆蓋事實仍保留在 `AnalysisResult`。
模型回傳的行號必須存在於候選，不能新增任意行號。

## 6. 程式位置與輸出

| 責任 | 程式位置（相對於 `src/codebase_analysis/`） |
| --- | --- |
| Jenkins 下載與 XML 雜湊 | `tools/coverage.py` |
| Metadata JSON 契約解析 | `lib/parsers/metadata.py`、`schemas/metadata.py` |
| XML 正規化 | `lib/parsers/coverage.py` |
| Diff 與 coverage 交集 | `lib/rules/coverage.py`、`lib/rules/provenance.py` |
| Maven 來源分類 | `lib/rules/paths.py` |
| Source commit 的原始碼讀取 | `tools/source.py` |
| Java AST | `lib/parsers/java.py` |
| 未覆蓋行與方法分組 | `lib/rules/context.py` |
| 收集與版本核對編排 | `collection.py`、`workflow.py` |
| LLM 分析 | `nodes/coverage.py` |

`AnalysisResult` 主要欄位：

| 欄位 | 含義 |
| --- | --- |
| `uncovered_lines` | 能對應 Java 方法的未覆蓋變更行 |
| `focal_methods` | 每個目標方法、原始碼與該方法中的缺口行 |
| `unassigned_uncovered_lines` | 位於方法外或無法唯一歸屬的缺口行 |
| `changed_executable_count` | 已匹配報告中的變更可執行行數 |
| `covered_changed_count` | 上述範圍內已覆蓋的行數 |
| `coverage_unmatched_paths` | 無法唯一對應 coverage 的 production 路徑 |
| `coverage_missing_patch_paths` | 有 coverage，但 PR API 未提供 diff 的路徑 |
| `trace` | 可選的 Jenkins 執行範圍、完整性及版本資訊 |
| `coverage_provenance` | 已核對的 coverage metadata，包括版本、build 與測試範圍 |

計數包含報告中可辨識的 production 變更行；方法外缺口可能計入分母，但不進入
`focal_methods`。缺少檔案報告／diff 時，計數僅描述已知範圍。

## 7. 驗證與接入狀態

本機案例涵蓋 diff 舊行排除、覆蓋計數、missing patch、全覆蓋檔案、路徑歧義、
重複 coverage 紀錄、Java overload、巢狀類別，以及 revision／digest 不一致。
本機測試使用固定 XML、Java source 與 trace。另已使用 PR #31／Jenkins
`test-all-server #6` 的真實 artifacts 驗證下載、版本綁定與 Java 上下文解析。

目前固定 `tree-sitter==0.25.2`：0.26.0 在真實檔案解析中出現行號損壞與退出時
segmentation fault，新增大型 Java 子程序回歸測試可重現舊版故障，改版後通過。
上游已記錄 [Point 引用計數回歸問題](https://github.com/tree-sitter/py-tree-sitter/issues/472)。

Jenkins build #7 已封存 PR #31 的 head coverage、metadata 與 per-test trace。
Agent 容器經真實遠端下載與版本／digest 核對，取得 22 個未覆蓋變更行、7 個 focal methods，
沒有 unmatched paths 或 unassigned lines。2026-10-09（台灣時間）經使用者授權，
透過 controller 執行 Gemini 完整分析成功，產出 22 筆行號分析。
Trace 契約及 producer 責任見 [Existing Tests 設計與實作報告](existing-tests-analysis.md)；
HTTP 與本機部署驗證見 [controller 部署說明](controller-deployment.md)。
