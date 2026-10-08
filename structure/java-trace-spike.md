# Java per-test trace spike：設計與驗證結果

## 範圍與結論

此 spike 已獲使用者同意，用來驗證 Java 呼叫追蹤的五項接入條件。
Java 17、Spring Boot 3.3.4、JUnit Platform、Byte Buddy 1.14.19、JaCoCo 0.8.15
在本機 Maven fixture 中完成整合。三個 JUnit 測試與 Python consumer 驗證均通過。

驗證範圍是直接方法呼叫與同一 JVM 中的同步 servlet HTTP 請求，包含兩個並行測試。
Fixture 採用目標 repo 目前的 `RANDOM_PORT`＋`TestRestTemplate` 模式。
它沒有使用目標 repo 的資料庫／Testcontainers，也沒有執行其完整測試 suite。
PR pipeline 的自動接入已在 PR #31／Jenkins build #7 產生真實 trace，Agent 下載及綁定驗證通過；controller 已新增，HTTP／容器接線見 [部署說明](controller-deployment.md)。

## 放置位置與執行邊界

| 環境／專案 | 責任 |
| --- | --- |
| `PDD/jenkins-pipelines/tools/java-test-trace/` | Java producer、Maven build、fixture |
| Jenkins agent／測試 sandbox | 測試 JVM 載入 JAR，執行測試、產生 XML／trace、組裝版本與雜湊 |
| LLM Agent pod／`test_Agent` | Python 下載、解析與分析 artifact；不建置／載入 Java producer |
| `test_Agent/tests/verify_java_trace_spike.py` | 開發期的唯讀 consumer 整合檢查，不屬於部署執行流程 |

初版為了 spike 驗證便利把 Java 放在 Python repo，現已移出。
已新增獨立 `pdd/java-trace-spike` 的 Job DSL 與 Jenkinsfile，固定使用 `pdd-test` agent。
Jenkins Declarative 語法驗證已通過；檔案尚待發布到 seed 讀取的分支，尚無 Jenkins 執行結果。
未來 sandbox 可以載入相同 producer JAR，但仍應由 sandbox 的測試 JVM 執行。

## Jenkins 手動驗證

1. 將 `jenkins-pipelines` 的 `jobs/java_trace_spike.groovy`、
   `pipelines/java-trace-spike.Jenkinsfile`、`scripts/trace-spike.sh` 與
   `tools/java-test-trace/` 發布到 Jenkins 設定的 pipeline repo／分支。
   本次沒有執行 git push；本機修改不會自動出現在 Jenkins。
2. Jenkins 執行既有 `seed` Job，等待 SUCCESS；或在管理機排入 seed：

   ```bash
   cd /home/mo/Documents/PDD/jenkins-config
   uv run --locked python -m jenkins_config seed
   ```

   這是排程命令，完成後仍須到 Jenkins 確認 seed 成功。
3. 開啟 `pdd/java-trace-spike`，按 **Build Now**。
4. **Console Output** 確認節點屬於 `pdd-test`，Maven 容器執行測試，
   最終顯示三個測試、零 failure／error／skip；**Test Result** 可查看個別結果。
5. **Artifacts** 查看下表的產物。`trace-observations.json` 的 `diagnostics`
   應為 `agent_attached: true`、`errors: []`；最終 trace 含三個測試，
   方法對應符合下方「五項驗收與反例」。
6. 下載此 build 的全部 artifacts 並保留目錄結構；在 Python 專案執行唯讀檢查：

   ```bash
   cd /home/mo/Documents/test_Agent
   ./scripts/verify-trace-spike.sh /下載解壓路徑/tools/java-test-trace/spike-fixture
   ```

Java 測試在 Jenkins agent 啟動的 Maven 3.9.9／JDK 17 容器執行。
本機的 seed 命令只觸發工作，consumer 命令只讀取下載的產物，兩者不執行 Java 測試。
Job 封存 fixture source、JUnit、coverage、trace 與 `trace-spike-source-revision.txt`，
後者記錄 producer checkout 的 commit。Jenkins SUCCESS 表示 Java fixture 與 finalizer 通過；
source mapping／並行隔離／Python 契約的完整驗收還包含第 6 步。

`./scripts/trace-spike.sh` 是 Jenkinsfile 的建置入口。開發者可在本機 JDK 17 下呼叫，
但這只能算本機開發驗證，不能當成 Jenkins 執行結果。

Producer 輸出在 `jenkins-pipelines/tools/java-test-trace/spike-fixture/target/`：

| 檔案 | 內容 |
| --- | --- |
| `surefire-reports/` | 三個測試的 JUnit 結果 |
| `jacoco.exec` | JaCoCo 執行資料 |
| `site/jacoco/jacoco.xml` | 與 trace 同次測試產生的 coverage |
| `trace-observations.json` | Java 產生的測試／方法對應與診斷 |
| `java-test-trace.json` | Java finalizer 組裝的 v1 契約產物，另經 Python consumer 唯讀驗證 |

最終 JSON 的 revision 固定為 40 個 `0`，build ID 為 `local-java-trace-spike`，
這是合成 fixture 標記；在 Jenkins 執行也保留此值，不能作為 PR #31 的證據。
`complete` 固定為 `false`；scope 列明尚未支援任意非同步傳遞。

## Maven 專案結構

```text
jenkins-pipelines/tools/java-test-trace/
├── pom.xml                         Reactor、JDK 與依賴版本
├── mvnw / mvnw.cmd / .mvn/         Maven Wrapper
├── trace-runtime/                  無框架依賴的 recorder、token 與方法身分
├── trace-agent/                    Byte Buddy premain 與方法入口 instrumentation
├── trace-test-support/             JUnit、Spring、source mapping、JSON adapter
│   └── src/main/java/dev/codebase/trace/
│       ├── junit/                  測試開始／結束與產物輸出編排
│       ├── spring/                 HTTP client interceptor、server filter、自動配置
│       ├── source/                 JVM descriptor／debug table → Java source
│       └── output/                 Observation JSON、final trace 組裝與 XML 雜湊
└── spike-fixture/                  可重現的 Spring 應用與測試
    ├── src/main/java/              Controller、Service、Application
    └── src/test/java/              普通 JUnit 與並行 RANDOM_PORT 測試
```

各 module 採 Maven 的 `src/main/java`、`src/main/resources`、`src/test/java` 結構。
Java agent 與測試支援共用 runtime；Byte Buddy 在 agent JAR 內 relocation，
避免直接佔用受測專案的 Byte Buddy namespace。測試支援依賴放在 test classpath。
Recorder 靜態入口供注入的 bytecode 與不同 adapter 呼叫；每個 invocation 的集合
及生命週期獨立保存，不以一個全域「目前測試」欄位承接並行資料。

## 執行流程

1. JVM 啟動 JaCoCo 與 trace Java agent。Agent 僅攔截 `trace.include` 指定 package 的方法。
2. JUnit listener 為每次測試 invocation 建立不可預測的 token，綁定 JUnit unique ID
   與測試方法的 class／name／JVM descriptor。
3. 同執行緒呼叫直接從 ThreadLocal 取得 token。
4. Spring BeanPostProcessor 對容器管理的 `TestRestTemplate`／`RestTemplate` 加入 interceptor；
   僅向該測試 server 的 loopback host＋實際 port 傳遞 `X-Codebase-Test-Trace`。
5. Server filter 只接受 recorder 中仍存活的 token，在 request 範圍內建立上下文，finally 還原。
6. 方法入口以 token 收集方法身分，同一 invocation 內去重。無 token、未知或已結束 token
   的呼叫只增加未歸屬計數，不根據時間窗口猜測測試身分。
7. 測試結束後關閉該 invocation；後續工作不能再加入其集合。
8. JUnit test plan 結束後，以 class debug line table 與 `SourceFile` 屬性解析原始碼位置，
   保留 JVM descriptor 區分 overload，再產生 raw observations。
9. Maven 完成 JaCoCo XML 後，由 Java `TraceArtifactAssembler` 計算 XML SHA-256、組裝 v1 trace。
10. Python 的獨立整合檢查讀取既有產物，呼叫 `parse_trace`、`verify` 與 `dynamic_contexts` 驗證。

第一次執行曾在 premain 階段因 `trace.include` 尚未生效而失敗。
已改為透過 Surefire `argLine` 的 `-Dtrace.include=...` 傳入，確保 agent 啟動前即可讀取；
JUnit／Spring 需要的其他設定仍放在 `systemPropertyVariables`。

## 五項驗收與反例（目前結果來自本機開發驗證）

| 驗證 | 測試方式 | 結果 |
| --- | --- | --- |
| 普通 JUnit 呼叫 | `directMethod()` 呼叫 `calculate(int)`，Python 確认未對到 `calculate(String)` | PASS |
| HTTP 跨執行緒 | `RANDOM_PORT`＋自動注入的 `TestRestTemplate`；回應檢查 server 與 test 執行緒不同 | PASS |
| 並行測試隔離 | `firstRequest`、`secondRequest` 同時跑，Service barrier 強制兩個 HTTP request 重疊 | PASS |
| JaCoCo 共存 | 相同 fork JVM 掛載兩個 agent，測試通過且 XML 有實際 covered lines | PASS |
| Python 契約與對應 | 解析實際 producer JSON、檢查所有 source reference 唯一對應、驗證 digest 與 dynamic contexts | PASS |
| 背景請求反例 | 測試期間以未管理的 HTTP client 呼叫 `/background`，沒有注入 token | 未歸到任何測試 |

實際觀察對應：

- `directMethod` → `WorkService.calculate(int)`。
- `firstRequest` → `WorkController.first`、`WorkService.first`、`WorkService.rendezvous`。
- `secondRequest` → `WorkController.second`、`WorkService.second`、`WorkService.rendezvous`。
- `WorkService.background`／`WorkController.background` 不出現在任一測試的 calls。

Python 的 association 驗證使用空的 uncovered-line 集合來檢查方法對應，
不把「有觀察到呼叫」誤稱為「缺口行已覆蓋」。本次沒有效能基準比較。

## 限制與正式接入前工作

- 尚未處理 `@Async`、CompletableFuture、Reactor、任意 executor 或跨 JVM HTTP 傳播。
  不依靠全域 active test 或繼承 ThreadLocal 來猜測背景呼叫。
- HTTP 範圍限定同 JVM 的同步 servlet request。不同 client 類型、redirect 與外部服務尚未驗證。
- Fixture 沒有驗證 Spring AOP／transaction proxy；正式 repo 的代理、反射與產生類別需驗證。
- 方法 instrumentation 排除 constructor、abstract、native、synthetic method；不保證 lambda 的完整紀錄。
- Source resolver 目前只接受單一 module 的 `src/main/java`、`src/test/java` 與 debug line table。
  缺少 debug 資料或來源位置有歧義會使輸出失敗，不猜路徑。
- 目前是一個 Surefire fork 與一個 test plan；多 fork、Failsafe、多 module 的獨立輸出與合併尚未實作。
- 測試範圍包含 listener 的 test execution 邊界，不保證 class-level setup／動態測試來源均能歸屬。
- Java finalizer 已獨立接收 observations、XML、revision、build ID、scope 與 output；
  PR pipeline 的參數注入與歸檔已在 PR #31／build #7 產生 artifacts；該目標與 build 已驗證，不代表所有 Maven 專案相容。

## PR poll 自動接入（build #7 artifacts 已驗證）

`fetch-pr` 按既有條件自動排入 `test-all-server`，傳入 PR／head／base 資訊。
`github-pr-test.Jenkinsfile` 自動 checkout producer source，執行：

1. `scripts/prepare_trace_pom.py`：依該 PR 的 POM 產生臨時測試 POM，保留原始檔與既有測試設定。
2. `scripts/pr-head-trace.sh`：在 Jenkins agent 的 Maven 容器建置 producer、執行 PR head 測試，
   同時產生 JaCoCo XML 與 observations，再由 Java finalizer 帶入 head SHA、job/build ID 組裝 trace。
3. 封存同 build 的 `agent-analysis/jacoco.xml`、`coverage-metadata.json`、`java-test-trace.json`。
4. 繼續原有合併測試。失敗時留下可取得的 raw observations，不把 trace 失敗當成功。

每個 PR 自動產生 source class 清單，不需 AI 或人工逐次改寫接入程式。
目前針對 `cloth_shop_server` 的單一 module／Surefire 一個 fork；
只攔截 `src/main/java` 的 top-level class，排除 generated code、proxy、test 與 nested class。
`complete=false`；profiles、Failsafe、multi-module、既有 argLine 會明確拒絕，不靜默覆寫。

`values.yaml` 的固定 URL 只供手動 smoke test。自動流程這次做到 Jenkins artifacts 封存，
Jenkins 觸發 controller 與 LLM 任務服務現已新增，見 [部署說明](controller-deployment.md)。

驗證：24 個 pipeline Python 測試通過；修改的 Java agent／runtime 編譯通過；
Jenkinsfile 通過 Jenkins linter。PR Java 測試由 Jenkins 執行；Agent 已下載 build #7 的 coverage／trace 並通過版本綁定。
本次未執行 git push；發布 pipeline 來源是一次性的部署步驟，不是每個 PR 的操作。

## 參考文件

- [Byte Buddy Java agent 與 instrumentation](https://bytebuddy.net/partial/tutorial.partial.html)
- [JUnit TestExecutionListener](https://docs.junit.org/5.11.0/api/org.junit.platform.launcher/org/junit/platform/launcher/TestExecutionListener.html)
- [Spring Boot auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
