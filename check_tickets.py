import os
import sys
import requests
from playwright.sync_api import sync_playwright

# ==========================================
# НАСТРОЙКИ ДАТ ДЛЯ ПОИСКА БИЛЕТОВ
# ==========================================
TARGET_MONTH = 11          # Номер месяца (1 — январь, 2 — февраль, 12 — декабрь и т.д.)
TARGET_DAYS = [5, 6]      # Список нужных чисел месяца (например: [5, 6] или [10, 11, 12])
# ==========================================

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Справочник месяцев на трех языках (в нижнем регистре)
MONTHS_INFO = {
    1:  {"ru": "январ",   "en_full": "january",   "en": "jan", "ka": "იან"},
    2:  {"ru": "феврал",  "en_full": "february",  "en": "feb", "ka": "თებ"},
    3:  {"ru": "март",    "en_full": "march",     "en": "mar", "ka": "მარ"},
    4:  {"ru": "апрел",   "en_full": "april",     "en": "apr", "ka": "აპრ"},
    5:  {"ru": "ма",      "en_full": "may",       "en": "may", "ka": "მაი"},
    6:  {"ru": "июн",     "en_full": "june",      "en": "jun", "ka": "ივნ"},
    7:  {"ru": "июл",     "en_full": "july",      "en": "jul", "ka": "ივლ"},
    8:  {"ru": "август",  "en_full": "august",    "en": "aug", "ka": "აგვ"},
    9:  {"ru": "сентябр", "en_full": "september", "en": "sep", "ka": "სექ"},
    10: {"ru": "октябр",  "en_full": "october",   "en": "oct", "ka": "ოქტ"},
    11: {"ru": "ноябр",   "en_full": "november",  "en": "nov", "ka": "ნოე"},
    12: {"ru": "декабр",  "en_full": "december",  "en": "dec", "ka": "დეკ"},
}

def build_targets(month, days):
    m = MONTHS_INFO[month]
    m_num = f"{month:02d}"

    # Для официального сайта театра ищем как само появление месяца, так и конкретные даты
    ru_kw = [m["ru"]]
    en_kw = [m["en_full"]]
    
    # Для TKT.GE ищем строго конкретные даты (чтобы избежать ложных срабатываний на фильтр календаря)
    tkt_en_kw = []
    tkt_ka_kw = []

    for d in days:
        d_pad = f"{d:02d}"
        
        # Шаблоны для gabriadze.com
        ru_kw.extend([f"{d_pad}.{m_num}", f"{d}.{m_num}", f"{d} {m['ru']}", f"{d_pad} {m['ru']}"])
        en_kw.extend([
            f"{d_pad}.{m_num}", f"{d}.{m_num}",
            f"{d} {m['en']}", f"{d_pad} {m['en']}",
            f"{m['en']} {d}", f"{m['en']} {d_pad}"
        ])
        
        # Шаблоны для tkt.ge
        tkt_en_kw.extend([
            f"{d_pad}.{m_num}",
            f"{d} {m['en']}", f"{d_pad} {m['en']}",
            f"{m['en']} {d}", f"{m['en']} {d_pad}"
        ])
        tkt_ka_kw.extend([
            f"{d_pad}.{m_num}",
            f"{d} {m['ka']}", f"{d_pad} {m['ka']}"
        ])

    return [
        {
            "name": "Официальный сайт театра (RU)",
            "url": "hhttp://gabriadze.com/performances",
            "keywords": ru_kw
        },
        {
            "name": "Официальный сайт театра (EN)",
            "url": "http://gabriadze.com/performances",
            "keywords": en_kw
        },
        {
            "name": "TKT.GE (Поиск по театру Габриадзе — EN)",
            "url": "https://tkt.ge/en/search?q=Gabriadze",
            "keywords": tkt_en_kw
        },
        {
            "name": "TKT.GE (Поиск по театру Габриадзе — KA)",
            "url": "https://tkt.ge/ru/bilety-v-teatr/gabriadze-theatre",
            "keywords": tkt_ka_kw
        }
    ]

TARGETS = build_targets(TARGET_MONTH, TARGET_DAYS)

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
    days_str = ", ".join(str(d) for d in TARGET_DAYS)
    print(f"Ищем билеты: месяц #{TARGET_MONTH}, числа: [{days_str}]")

    with sync_playwright() as p:
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
                
                page.goto(target["url"], wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(6000)
                
                content = page.inner_text("body").lower()
                
                if "just a moment" in content or "enable javascript and cookies" in content:
                    print(f"⚠️ Внимание: {target['name']} запросил проверку Cloudflare. Пропускаем.")
                    continue

                matched = [word for word in target["keywords"] if word in content]
                
                if matched:
                    # Убираем дубликаты в списке совпадений для красивого вывода
                    unique_matched = list(dict.fromkeys(matched))
                    msg = (
                        f"🎭 <b>Найдены билеты или афиша в театр Габриадзе!</b>\n\n"
                        f"📍 <b>Источник:</b> {target['name']}\n"
                        f"📅 <b>Целевые даты:</b> числа {days_str} (месяц {TARGET_MONTH:02d})\n"
                        f"🔍 <b>Найдено на странице:</b> <code>{', '.join(unique_matched)}</code>\n\n"
                        f"👉 <a href='{target['url']}'>Перейти к покупке</a>\n"
                        f"👉 <a href='https://gabriadze.com/ru/tickets/'>Сайт театра</a>"
                    )
                    send_telegram_message(msg)
                    found_any = True
                    break
            except Exception as e:
                print(f"Ошибка при проверке {target['name']}: {e}")

        browser.close()
        
    if not found_any:
        print("Целевых дат пока не обнаружено.")

if __name__ == "__main__":
    if "--test" in sys.argv:
        days_str = ", ".join(str(d) for d in TARGET_DAYS)
        send_telegram_message(
            f"✅ <b>Тест успешен!</b>\n"
            f"Бот отслеживает билеты на числа: <b>{days_str}</b> (месяц: <b>{TARGET_MONTH:02d}</b>).\n"
            f"Проверяются gabriadze.com и выдача TKT.GE."
        )
    check_schedule()
