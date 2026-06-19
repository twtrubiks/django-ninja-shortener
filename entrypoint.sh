#!/bin/sh

# 如果任何指令失敗，立即退出
set -e

# entrypoint 只負責執行傳入的指令，本身不碰任何會變更狀態的釋出步驟。
#
# migrate / createcachetable / collectstatic 這類「變更 DB schema 或寫入共用靜態檔」
# 的動作，一律交給專屬的一次性 `migrate` 服務集中執行一次（見 docker-compose*.yml）。
# 長駐服務（web / qcluster）改以 depends_on: service_completed_successfully 等它跑完，
# 因此這些容器的啟動路徑裡「沒有」migrate —— 從結構上杜絕了多個容器開機各自 migrate
# 造成的並發競態（relation already exists），而非靠旗標壓制。
exec "$@"
