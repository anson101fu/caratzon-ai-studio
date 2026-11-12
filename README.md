# Caratzon.com AI Studio V1 — 部署說明（繁體中文）

目標網址：`https://ai.caratzon.com`（尚未部署）。這是獨立新網站，不覆蓋現有 Showroom。

## 1. 先部署演示版（不需要 API Key）

1. 解壓縮 ZIP，進入 `caratzon-ai-studio` 資料夾。
2. 在 GitHub 建立新 repository，建議名稱 `caratzon-ai-studio`。把 **public 資料夾、functions 資料夾、README.md、.gitignore** 一起上傳到 repository 根目錄（不要只上傳 index.html）。
3. Cloudflare Dashboard → Workers & Pages → Create application → Pages → Connect to Git，選擇新 repository。
4. Build settings：Framework preset 選 None；Build command 留空；Build output directory 填 `public`；Root directory 留空。部署分支選 main（或你的實際分支）。
5. 部署完成後先打開 Cloudflare 分配的 `*.pages.dev` 網址，檢查三語、示例、作品儲存與 3D。
6. 在 Pages project → Custom domains → Set up a domain，輸入 `ai.caratzon.com`。若域名不由 Cloudflare 管理，按畫面指示在現有 DNS 服務商新增對應 CNAME。不要改動主域名或現有 Showroom 記錄。待 SSL 生效後再測試。

## 2. 開啟真正 AI 功能（可選）

Cloudflare Pages project → Settings → Variables and Secrets → Add，選 Secret/Encrypt，新增：

| 名稱 | 用途 |
| --- | --- |
| `STUDIO_ACCESS_CODE` | 自行設定至少 16 字元的高強度隨機私人測試碼，不要公開 |
| `OPENAI_API_KEY` | OpenAI 開發者平台的 API Key；用於生圖及改圖 |
| `MESHY_API_KEY` | Meshy API Key；用於圖片轉 3D |
| `OPENAI_IMAGE_MODEL` | 可選，預設 `gpt-image-2.5-flare`；依帳戶支援情況調整 |

設定完成後重新部署。打開網站右上角「測試登入」，輸入自己設定的訪問碼。只設定某個供應商的 Key，就只有相應功能可使用。API 帳戶需要獨立充值/計費與相應模型權限；ChatGPT 訂閱不包含 API 額度。不要把 Secret、API Key 或私人訪問碼上傳 GitHub，也不要貼到聊天中。

這是私人 Beta，不是完整公開會員/積分系統。共用訪問碼僅供管理員或少量可信測試者使用，無每人額度、分帳或持久工作佇列。公開推廣付費功能前，必須接入 Supabase Auth、伺服器端每帳戶限額、扣點交易、Cloudflare WAF/速率限制和供應商帳單預算。未做這些設定前請勿分享測試碼。可另外在 Cloudflare 設定 Access 保護整個站點或 API。

## 3. 已實作

- 簡體中文、English、Русский，可手動切換；桌面及手機版。
- AI 珠寶設計、手稿轉效果圖、改款、多角度概念圖、佩戴圖、產品精修、浮雕概念圖：後端對接 OpenAI Image API。
- 圖片轉 3D：後端對接 Meshy，非同步輪詢 GLB 生成結果；GLB 本地開啟、下載。模型預覽使用 model-viewer CDN，需要瀏覽器網絡與 WebGL 支援，未測試中國/俄羅斯網絡。
- 示例是原創 SVG 插畫及程序生成的 GLB 概念模型，非 AI 即時生成、非精準工廠 CAD。
- 本地作品儲存（瀏覽器容量有限，請下載備份）；正式會員、雲端同步、充值、真正浮雕網格、影片、訂單及電郵通知未接入。
- OEM 詢價資料以 JSON 本地下載，設計圖與模型需另行下載附上；未自動送出訂單或郵件。
- API Key 僅存後端；沒有配置訪問碼時 API 拒絕請求；訪問碼保存在當前瀏覽器 session，離開測試後可登出。

## 4. 測試與限制

已做 JavaScript 語法檢查及 GLB 結構驗證；真實付費 API 未使用（未提供憑證）。正式部署後，先用管理員測試 1 次生圖、1 次改圖及 1 次 3D，再評估成本、模型細節與網絡地區可用性。供應商模型生成的 GLB 連結可能過期，請立即下載保存。AI 模型不是生產用 CAD，打板前應由專業人員審核尺寸、鑲嵌、厚度、扣位及網格。

官方參考：
- https://developers.cloudflare.com/pages/functions/bindings/
- https://developers.cloudflare.com/pages/configuration/custom-domains/
- https://developers.openai.com/api/docs/guides/image-generation
- https://docs.meshy.ai/en/api/image-to-3d
