# Project instructions

- Do not git push.
- 使用 uv，不使用 pip。
- 任何 spike 在實作前先詢問使用者。
- Python 採合理 OOP、組合優先於繼承；按元件類型組織檔案，避免過度抽象。
- 使用根目錄 values.yaml 配置 secrets；不得輸出或提交 secrets。
- 操作 shell 放在 scripts/；部署檔留在本專案；structure/ 記錄實際架構。

# Backlog

- 接續專案工作時讀取 BACKLOG.md，依使用者指定的 PBI／範圍執行；列入 backlog 不代表授權。
- 更新該 PBI 的進度、驗收證據及未決事項；符合驗收條件後才標示完成。
- 保持 PBI 的交付價值與實作子任務分開，不擅自擴大範圍。

## PBI terminology and traceability

- Maintain PBI descriptions in English, using explicitly defined terms.
- A PBI ID is permanent and is distinct from backlog order, a conversation list number, and a workflow step.
- Record any split/merge or mapping from an earlier task list; never silently renumber or reinterpret authorization.
- Separate implemented behavior, acceptance requirements, proposals, open decisions, and verification evidence.
- Use “user story” only for that description format; do not imply every PBI is a user story.
- Describe resume/restart/checkpoint behavior precisely, including durability limits. Do not mark an item Done without evidence for its acceptance criteria.
