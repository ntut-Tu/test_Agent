# HTTP controller、任務與容器部署

## 執行流程

```text
PR poll → test-all-server → head tests → coverage / trace 歸檔
                                          ↓ POST /test-agent/analyses
                                共用 Traefik（移除 /test-agent）
                                          ↓
                             FastAPI controller → SQLite queued job
                                          ↓
                             worker → 收集與版本核對 → 三個 LLM 分析
                                          ↓
                                  succeeded / failed + result
```

Jenkins 提交的是 provider、repository、PR number、head SHA、job name、build number。
Controller 只接受 `values.yaml` 配置的 repository／job，從 `jenkins.base_url` 組裝該 build 的固定 artifact URL。
不使用 latest 指標、不改寫全域設定、不要求每個 PR 手動填 URL。
下載後仍核對目前 PR head、XML digest 及 metadata／trace 的 build ID；不符時不呼叫模型。

## 專案分層

| 路徑 | 責任 |
| --- | --- |
| `controller.py` | HTTP controller、Bearer 認證、狀態碼與回應 |
| `schemas/http.py` | HTTP request DTO／欄位驗證 |
| `tasks.py`、`repositories/base.py` | 任務提交範圍、執行協調、JobStore port |
| `collection.py`、`workflow.py` | 收集、CI 身分核對、三個 LLM 操作 |
| `models/task.py` | 不依賴 HTTP／DB 的 build 身分與任務資料 |
| `repositories/sqlite.py` | SQLite 持久化、原子 enqueue／claim／retry |
| `worker.py` | 背景 worker 與 volume 排他鎖 |
| `bootstrap.py` | 由可信設定建立單次 build 的 artifact URL |
| `server.py` | ASGI composition root，組合上述元件與生命週期 |
| `Dockerfile`、`deploy/compose.yaml` | uv 鎖定依賴、非 root 容器與持久 volume |
| `deploy/traefik/test-agent.yaml` | 共用 Traefik 的原生 file-provider 路由 |
| `scripts/serve.sh`、`scripts/deploy.sh` | 本機 server／容器部署入口 |
| `scripts/register-traefik-route.sh`、`scripts/register_traefik_route.py` | 獨立掛載本專案路由；既有掛載送出 SIGHUP 重新載入 |

所有 Test Agent 部署來源放在此 repo。`pdd_deploy_tools` 僅提供既有網路／Traefik 架構參考。
共用 Traefik 額外唯讀掛載本 repo 的路由目錄；不複製 Agent 路由檔到 PDD repo。

## API

除了健康檢查，其餘 API 都要求 `Authorization: Bearer <service.api_token>`。

| HTTP | 外部路徑 | 回應 |
| --- | --- | --- |
| POST | `/test-agent/analyses` | 202 與任務 ID；已完成的重送回 200 |
| GET | `/test-agent/analyses/{id}` | 狀態、版本、時間及去除敏感資訊的錯誤類型 |
| GET | `/test-agent/analyses/{id}/result` | 成功結果；尚未成功回 409 |
| POST | `/test-agent/analyses/{id}/retry` | 只將 failed 任務重新排隊，active／succeeded 保持原狀 |
| GET | `/test-agent/health/live` | HTTP server 存活 |
| GET | `/test-agent/health/ready` | worker 已啟動 |

提交範例（build_number 必須是已歸檔的真實 build）：

```json
{
  "provider": "github",
  "repository": "ntut-Tu/cloth_shop_server",
  "number": 31,
  "head_sha": "<40 或 64 位完整 commit SHA>",
  "job_name": "pdd/test-all-server",
  "build_number": 7
}
```

回應中的 `id` 由完整請求的身分計算。相同 build 請求重送不會再呼叫 LLM。
`GET /result` 的 `context` 包含收集的版本與證據，`findings` 是三個綠色步驟的分析結果。
不存在任務回 404，認證失敗回 401，格式／來源範圍不符回 422，佇列額滿回 503。

## 設定與網路

Secrets 仍直接填根目錄 `values.yaml`，不寫入 image 或 Traefik YAML。

```yaml
jenkins:
  base_url: "http://pdd-jenkins-controller-1:8080"
  job_name: "pdd/test-all-server"
  # username、api_token 沿用既有憑證
  # artifact_url、metadata_url、trace_url 僅供手動 smoke test
service:
  api_token: "<至少 32 字元的隨機 token>"
  root_path: "/test-agent"
  data_directory: "/data"
  max_pending: 100
```

根目錄 `deployment` 設定選擇 Docker context、共用 `pdd-network` 與 Jenkins 的 `pdd-jenkins_default`。
部署入口依設定組合 Compose overlays；不切換使用者的目前 Docker context。
若 Jenkins 在其他主機，應調整 Compose network 與 `base_url`；`127.0.0.1` 在容器內指向容器自身。
Agent 不公開 host port；Traefik 將 `/test-agent` 轉送到 `http://test-agent:8080`。
路由 priority=200，優先於 PDD frontend 的 catch-all。

`values.yaml` 以唯讀掛載，保持主機 600 權限；部署腳本以目前使用者 UID/GID 建置服務使用者，
使容器能讀取設定並寫入自己的資料 volume。請用持有該檔案的非 root 使用者部署。

```bash
./scripts/deploy.sh
```

先確認共用網路／Traefik 已啟動。部署入口在 Agent healthy 後呼叫 `register_traefik_route.py`：

- 原有 PDD `/etc/traefik` 掛載保持不變。
- 將本 repo 的 `deploy/traefik/` 唯讀掛載到 `/etc/traefik/dynamic/test-agent/`。
- PDD 主機來源目錄只建立一個空 mount point，不存放 Agent 路由檔。
- 第一次增加 mount 會重建共用 Traefik，保留 image、port、network、labels 與原有設定。
  舊容器停止並保留為 `pdd-traefik-before-test-agent`，失敗時自動恢復。
- 後續部署只送出 SIGHUP，因 file provider 會讀取子目錄，但 watch 不遞迴監看。
  單純手改 Agent 路由後執行 `./scripts/register-traefik-route.sh` 即可重新載入。

若日後 PDD 工具用 `--replace` 重建共用代理，需要保留此額外 mount，或再執行 Agent 路由註冊。
若 rollback 容器名稱已存在，工具會停止以免覆蓋；確認不需舊備份後再由操作者清理。
設定變更後重新建立 Agent 容器；不刪除 `analysis-data` volume。

## Jenkins 接線（一次性部署）

`jenkins-pipelines` 已新增 `scripts/submit_agent_analysis.py` 與提交 stage：

1. 建立 Jenkins Secret text credential `test-agent-api-token`，內容與 `service.api_token` 相同。
2. Job 的 `AGENT_API_URL` 填寫從 Jenkins 執行容器可達的共用 Traefik 入口。
   本機 Docker Desktop 範例為 `http://host.docker.internal:18487/test-agent`。
3. 發布 pipeline source 並執行 seed；後續 PR poll 都會自動使用此設定。

提交失敗重試最多三次；重新提交使用相同任務 ID。
Jenkins 封存 `agent-analysis/controller-receipt.json`，接收成功後即繼續合併測試。
LLM 任務於 Agent 容器持續執行；其後續失敗不會回寫已完成的 Jenkins build 狀態，需查任務 API。
HTTP 提交失敗會將提交 stage 標為失敗、build 至少為 UNSTABLE，原有合併測試仍繼續。

## 持久化與限制

- SQLite 與結果位於 named volume；重建 container 保留任務。刪除 volume 才會刪除歷史。
- 目前為單一 instance、單一 worker；volume 排他鎖拒絕另一個同時處理者。
- queued 任務在重啟後繼續；被中斷的 running 任務標為 `failed / Interrupted`，可明確 retry。
  外部模型呼叫在斷線瞬間可能已完成，retry 可能再次產生模型費用，不宣稱 exactly-once。
- 此版本不含多副本分散式 queue；不含 Step 2 測試生成／sandbox 執行。
- Trace 的 `complete=false` 仍代表部分追蹤；已有觀察可作證據，不代表所有呼叫都已記錄。

參考：[FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/)、
[uv Docker integration](https://docs.astral.sh/uv/guides/integration/docker/)。


本機部署的設定範例：

```yaml
deployment:
  docker_context: desktop-linux
  traefik_container: pdd-traefik
  traefik_network: pdd-network
  jenkins_network: pdd-jenkins_default
  published_port: null
```

跨引擎時才使用 `published_port`，並另外配置代理可達的 upstream；本機目前全在同一引擎，不需要公開 Agent port。

## 本機部署驗證：2026-10-09（台灣時間）

已部署於 `desktop-linux`，Agent container 為 `test-agent`；共用入口為
`http://127.0.0.1:18487/test-agent`。Agent 沒有直接發布 host port。

| 檢查 | 結果 |
| --- | --- |
| Traefik `/test-agent/health/ready` | HTTP 200；container healthy |
| 未提供 Bearer token | HTTP 401 |
| 提交其他 repository | HTTP 422，未建立任務 |
| Agent 連線 Jenkins | 容器網路連線成功 |
| PR #31／`pdd/test-all-server/7` artifacts | coverage／trace revision、build 身分及 digest 通過 |
| 實際 Gemini 分析 | `succeeded`；PR 摘要、22 筆行號分析、1 筆測試推薦 |
| 相同 build 重送 | 沿用同一 ID 與完成結果，沒有重新排隊 |
| Jenkins Secret text | 已建立 `test-agent-api-token`，值來自根目錄設定 |

經使用者授權的一次完整任務由 Jenkins 網路內的驗證容器經共享 Traefik 送入，
不是實際觸發新的 Jenkins build。模型為設定中的 `google_genai / gemini-3.5-flash-lite`。

任務 ID：`be6aa328c866c5531a0d05919e0d7b2614000191440349104e4faafed3615b53`。
結果保存在 Agent volume，另下載至本機忽略版本控制的 `.state/pr31-build7-result.json`（權限 600）。
Trace 有 3 筆 tests、`complete=false`；7 個缺口方法沒有取得 dynamic context，
本次 Existing Tests 的 1 筆結果為 `evidence=llm`，不能當作實測呼叫證據。

Controller／持久化／路由遷移及既有分析測試共 50 項通過；Ruff、shell 語法及 diff 空白檢查通過。
Jenkins helper 測試 25 項通過，5 份 Jenkinsfile 通過 linter，3 份 Job DSL 通過 Groovy 語法解析。

**尚待發布的接線**：`jenkins-pipelines` 的 controller 提交 stage、helper 及 Job DSL
仍為本機變更。遵照使用者要求未執行 git push。將這些變更發布至 seed 使用的分支並執行 seed 後，
後續 PR poll build 才會使用新增的自動提交 stage；不能把本次 HTTP 驗證當作該 stage 已上線。
