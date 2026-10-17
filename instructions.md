# CM 產品程式碼

先讀上層 `../instructions.md`、`../Implementation-decisions.md`、`../CONTEXT.md`。現行規格與任務位於 `../planning/cm-v1/`，tracker 配置見 `../docs/agents/issue-tracker.md`。

本目錄為獨立 Git repo，只提交產品程式碼與執行文件，不使用 Brain remote。禁止批量刪除。工程技能路由及流程見 [Side Projects 指引](../../instructions.md)；技能路徑相對於 Brain Vault 根目錄，不是本 app repo。

採 React／TypeScript／Vite、Django／DRF、PostgreSQL。以 Django Session 與 CSRF 實作同源登入。班級角色依 membership 判斷，不把導師變成 Django 超級使用者。

測試邊界已確認：HTTP 工作流 API → PostgreSQL，以及核心 Playwright／Edge 工作流（含登入與角色隔離），不重問既定邊界。產品行為修改先寫失敗測試，再完成最小功能；純文件修改只做相應文件驗證。Review 以本次工作開始前的 baseline commit 比較本次已提交變更；未提交內容須另行明列審查，不能視為已被 HEAD diff 涵蓋。

保留使用者既有變更；`my_test/` 不讀寫，`.local/` 資料庫及本機資料不因測試收尾而刪除。依上層指引區分本機提交、推送與部署，使用者未授權的推送／部署不自動執行。最新產品狀態與下一步只維護在 `../instructions.md`，本檔保留穩定的產品工作規則。
