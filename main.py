# -*- coding: utf-8 -*-
import os
import json
import logging
import http.server
import socketserver
from concurrent.futures import ThreadPoolExecutor
from google import genai

from news_scraper import fetch_all_news, save_to_json as save_news
from market_data import fetch_all_market_data, save_to_json as save_market

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PORT = 8000

def generate_ai_summary():
    """讀取抓好的新聞，並呼叫 Gemini 產生專屬早報。若失敗則自動啟用備用機制。"""
    logger.info("開始處理 AI 摘要...")
    
    # 這是我們的「系統保險絲」，如果 AI 當機，網頁依然會顯示這段備用文字
    fallback_html = """
    <p>⚠️ <strong>系統提示：</strong>目前無法取得雲端 AI 伺服器連線。</p>
    <p>請直接參考下方的「市場行情」與「焦點頭條」，尋找今日適合穩健收息與擴大現金流之標的。</p>
    """
    
    summary_html = fallback_html
    status = "error"

    try:
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise ValueError("未設定 GEMINI_API_KEY 金鑰")

        with open("news_data.json", "r", encoding="utf-8") as f:
            news_data = json.load(f)

        news_titles = []
        for source, data in news_data.get("sources", {}).items():
            for item in data.get("news", []):
                news_titles.append(f"- {item['title']}")
        news_text = "\n".join(news_titles)

        client = genai.Client(api_key=api_key)
        prompt = f"""
        你是一位資深的金融市場分析師。請根據以下今日最新的財經新聞標題，整理一份「3分鐘市場早報」。
        請聚焦於：如何透過這些資訊協助客戶尋找「擴大現金流部位、穩健收息」的投資機會與避險方向。
        請輸出一段 300 字以內的精華摘要，請直接使用 HTML 格式輸出（可包含 <h3>, <ul>, <li>, <strong> 等標籤，但不要包含 <html>, <body>，也不要輸出 Markdown 的 ```html 標記）。
        今日新聞標題：\n{news_text}
        """
        
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt,
        )
        summary_html = response.text.replace("```html", "").replace("```", "").strip()
        status = "ok"

    except Exception as e:
        logger.error(f"❌ [AI 摘要] 處理失敗，自動切換至備用機制: {e}")

    # 🛑 最重要的一步：無論上面成功還是失敗，這裡「絕對」會強制建立檔案！
    try:
        with open("ai_summary.json", "w", encoding="utf-8") as f:
            json.dump({"summary_html": summary_html, "status": status}, f, ensure_ascii=False, indent=2)
        logger.info("✅ [AI 摘要] 檔案已成功建立 (ai_summary.json)")
    except Exception as write_error:
        logger.error(f"❌ 嚴重錯誤：無法寫入檔案: {write_error}")

def update_data_job():
    logger.info("========================================")
    logger.info("🔄 開始執行資料抓取與 AI 分析任務...")
    
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_news = executor.submit(fetch_all_news, max_items_per_source=10)
        future_market = executor.submit(fetch_all_market_data)

        try:
            save_news(future_news.result(), "news_data.json")
            logger.info("✅ [新聞數據] 抓取完成")
        except Exception as e:
            logger.error(f"❌ [新聞數據] 失敗: {e}")

        try:
            save_market(future_market.result(), "market_data.json")
            logger.info("✅ [市場行情] 抓取完成")
        except Exception as e:
            logger.error(f"❌ [市場行情] 失敗: {e}")

    generate_ai_summary()
    logger.info("✨ 資料更新與任務執行完畢！")
    logger.info("========================================")

if __name__ == "__main__":
    update_data_job()
