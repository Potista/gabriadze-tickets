import os
import sys
import requests
from playwright.sync_api import sync_playwright

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Настройки площадок: для сайта театра ищем и месяц, и даты,
# а для TKT.GE — только конкретные даты 5 и 6 января, чтобы избежать ложных срабатываний
TARGETS = [
    {
        "name": "Официальный сайт театра (RU)",
        "url": "https://gabriadze.com/ru/tickets/",
        "keywords": [
            "январ", "05.01", "06.01", "5.01", "6.01",
            "5 январ", "6 январ"
        ]
    },
    {
        "name": "Официальный сайт театра (EN)",
        "url": "https://gabriadze.com/en/tickets/",
        "keywords": [
            "january", "05.01", "06.01", "5.01", "6.01",
            "5 jan", "6 jan", "jan 5", "jan 6"
        ]
    },
    {
        "name": "TKT.GE (Поиск по театру Габриадзе — EN)",
        "url": "https://tkt.ge/en/search?q=Gabriadze",
        "keywords": [
            "05.01", "06.01", "5 jan", "6 jan",
            "05 jan", "06 jan", "jan 5", "jan 6", "jan 05", "jan 06"
        ]
    },
    {
        "name": "TKT.GE (Поиск по театру Габриадзе — KA)",
        "url": "https://tkt.ge/ka/search?q=%E1%83%92%E1%83%90%E1%83%91%E1%83%A0%E1%83%98%E1%83%90%E1%83%AB%E1%83%94",
        "keywords": [
            "05.01", "06.01", "5 იან", "6 იან", "05 იან", "06 იან"
        ]
    }
]

def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Ошибка: Не заданы TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        print("Уведомление успешно отправлено в Telegram!")
    except Exception as e:
        print(f"Ошибка отправки в Telegram: {e}")

def check_schedule():
    found_any = False
    with sync_playwright() as p:
        # Аргумент disable-blink-features помогает обходить базовую защиту от ботов на tkt.ge
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768}
        )
        page = context.new_page()

        for target in TARGETS:
            try:
                print(f"Проверяю: {target['name']} ({target['url']})")
                
                # Используем domcontentloaded + паузу, так как tkt.ge держит фоновые соединения
                page.goto(target["url"], wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(6000)  # Ждем 6 секунд для рендеринга карточек спектаклей
                
                content = page.inner_text("body").lower()
                
                # Проверяем, не заблокировал ли страницу экран Cloudflare
                if "just a moment" in content or "enable javascript and cookies" in content:
                    print(f"⚠️ Внимание: {target['name']} запросил проверку Cloudflare. Пропускаем.")
                    continue

                matched = [word for word in target["keywords"] if word in content]
                
                if matched:
                    msg = (
                        f"🎭 <b>Найдены билеты или афиша в театр Габриадзе!</b>\n\n"
                        f"📍 <b>Источник:</b> {target['name']}\n"
                        f"🔍 <b>Совпадения:</b> <code>{', '.join(matched)}</code>\n\n"
                        f"👉 <a href='{target['url']}'>Перейти к покупке</a>\n"
                        f"👉 <a href='https://gabriadze.com/ru/tickets/'>Сайт театра</a>"
                    )
                    send_telegram_message(msg)
                    found_any = True
                    break  # Останавливаем цикл после первого найденного совпадения
            except Exception as e:
                print(f"Ошибка при проверке {target['name']}: {e}")

        browser.close()
        
    if not found_any:
        print("Целевых дат (5-6 января) пока не обнаружено.")

if __name__ == "__main__":
    if "--test" in sys.argv:
        send_telegram_message(
            "✅ <b>Тест успешен!</b>\n"
            "Бот отслеживает официальный сайт театра Габриадзе и выдачу TKT.GE."
        )
    check_schedule()
