#!/usr/bin/env python3
"""Ежедневный дайджест по технопаркам мира -> Telegram.

Каждая новость приводится к одному виду: заголовок, площадка, что сделали, ссылка.

    python3 digest.py --dry-run     # показать в консоли, ничего не отправлять
    python3 digest.py               # отправить (нужны TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID)
"""
import argparse
import datetime as dt
import hashlib
import html
import json
import os
import pathlib
import sys
import time
import urllib.parse
import urllib.request

import feedparser
import yaml

import extract

ROOT = pathlib.Path(__file__).parent
SEEN_PATH = ROOT / "seen.json"
SEEN_TTL_DAYS = 30
TG_LIMIT = 3900  # запас к телеграмному лимиту в 4096 символов


def load_seen():
    if not SEEN_PATH.exists():
        return {}
    try:
        return json.loads(SEEN_PATH.read_text())
    except json.JSONDecodeError:
        return {}


def save_seen(seen):
    cutoff = time.time() - SEEN_TTL_DAYS * 86400
    SEEN_PATH.write_text(json.dumps({k: v for k, v in seen.items() if v > cutoff}))


def canonical(url):
    """Без utm-хвостов, чтобы одна статья не пришла дважды из разных фидов."""
    parts = urllib.parse.urlsplit(url)
    query = [
        (k, v)
        for k, v in urllib.parse.parse_qsl(parts.query)
        if not k.startswith(("utm_", "oc")) and k not in {"ref", "fbclid", "amp"}
    ]
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), "")
    )


def entry_time(entry):
    for field in ("published_parsed", "updated_parsed"):
        value = getattr(entry, field, None)
        if value:
            return dt.datetime.fromtimestamp(time.mktime(value), dt.timezone.utc)
    return None


def collect(config):
    keywords = [k.lower() for k in config.get("keywords", [])]
    trust_all = set(config.get("trust_all", []))
    horizon = dt.datetime.now(dt.timezone.utc) - dt.timedelta(
        hours=config.get("lookback_hours", 26)
    )

    seen = load_seen()
    fresh_keys, items, problems = set(), [], []

    for feed in config["feeds"]:
        name, url = feed["name"], feed["url"]
        try:
            parsed = feedparser.parse(url, agent="technopark-digest/1.0")
            if parsed.bozo and not parsed.entries:
                raise RuntimeError(parsed.bozo_exception)
        except Exception as exc:  # один упавший фид не должен ронять дайджест
            problems.append(f"{name}: {exc}")
            continue

        for entry in parsed.entries:
            link = getattr(entry, "link", "")
            raw_title = getattr(entry, "title", "")
            if not link or not raw_title.strip():
                continue

            published = entry_time(entry)
            if published and published < horizon:
                continue

            raw_summary = getattr(entry, "summary", "")
            haystack = extract.clean_text(f"{raw_title} {raw_summary}").lower()
            if name not in trust_all and keywords:
                if not any(k in haystack for k in keywords):
                    continue

            key = hashlib.sha1(canonical(link).encode()).hexdigest()
            if key in seen or key in fresh_keys:
                continue
            fresh_keys.add(key)

            card = extract.normalize(raw_title, raw_summary)
            card.update(
                link=link,
                key=key,
                source=name,
                published=published or dt.datetime.now(dt.timezone.utc),
            )
            items.append(card)

    items.sort(key=lambda i: i["published"], reverse=True)
    return items[: config.get("max_items", 10)], problems, seen


def enrich(items, enabled=True):
    """Добираем 'что сделали' со страницы статьи там, где фид его не дал."""
    if not enabled:
        return
    for item in items:
        if item["what"]:
            continue
        description = extract.fetch_description(item["link"])
        if description:
            item["what"] = extract.summarize(description, item["title"])


def render(items, problems):
    esc = html.escape
    today = dt.datetime.now().strftime("%d.%m.%Y")
    lines = [f"<b>🏗 ТЕХНОПАРКИ МИРА — {today}</b>", f"<i>Материалов: {len(items)}</i>", ""]

    if not items:
        lines.append("Сегодня по заданным фильтрам ничего нового не вышло.")

    for n, item in enumerate(items, 1):
        park = item["park"] or "не определён"
        if item["country"]:
            park = f"{park} ({item['country']} {item['flag']})".replace(" )", ")")

        lines.append(f"<b>{n}. {esc(item['title'])}</b>")
        lines.append(f"🏢 <b>Технопарк:</b> {esc(park)}")
        lines.append(f"📌 <b>Что сделали:</b> {esc(item['what'] or 'подробности по ссылке')}")
        lines.append(f'🔗 <a href="{esc(item["link"], quote=True)}">{esc(item["source"])}</a>')
        lines.append("")

    if problems:
        lines.append(f"<i>⚠️ Источников не ответило: {len(problems)}</i>")
    return "\n".join(lines)


def chunks(text, limit=TG_LIMIT):
    """Режем по строкам, чтобы не разорвать HTML-разметку посреди тега."""
    buf = ""
    for line in text.split("\n"):
        if len(buf) + len(line) + 1 > limit:
            yield buf
            buf = ""
        buf += line + "\n"
    if buf.strip():
        yield buf


def send(text, token, chat_id):
    for chunk in chunks(text):
        payload = urllib.parse.urlencode(
            {
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            }
        ).encode()
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=payload
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read())
            if not body.get("ok"):
                raise RuntimeError(body)
        time.sleep(1)  # не упираемся в rate limit


def load_env():
    """Читаем .env рядом со скриптом. Файл в .gitignore — в репозиторий не уедет.

    Переменные окружения имеют приоритет: в CI секреты приходят от GitHub.
    """
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def credentials(send_test=False):
    """Достаём токен и chat_id, при --ping сразу проверяем связь."""
    try:
        token = os.environ["TELEGRAM_BOT_TOKEN"]
        chat_id = os.environ["TELEGRAM_CHAT_ID"]
    except KeyError as missing:
        sys.exit(
            f"Не задано {missing}. Пропиши его в файл .env рядом со скриптом "
            "или передай переменной окружения."
        )

    if send_test:
        send("<b>✅ Связь есть.</b> Дайджест по технопаркам подключён.", token, chat_id)
        print("Тестовое сообщение отправлено.")
    return token, chat_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="печать в консоль")
    parser.add_argument("--no-enrich", action="store_true", help="не ходить за описаниями")
    parser.add_argument("--ping", action="store_true",
                        help="отправить тестовое сообщение и выйти")
    parser.add_argument("--config", default=str(ROOT / "feeds.yml"))
    args = parser.parse_args()

    load_env()

    if args.ping:
        credentials(send_test=True)
        return

    config = yaml.safe_load(pathlib.Path(args.config).read_text())
    items, problems, seen = collect(config)
    enrich(items, enabled=not args.no_enrich)
    text = render(items, problems)

    if args.dry_run:
        print(text)
        for problem in problems:
            print("WARN", problem, file=sys.stderr)
        return

    token, chat_id = credentials()
    send(text, token, chat_id)
    for item in items:
        seen[item["key"]] = time.time()
    save_seen(seen)  # помечаем отправленным только после успешной отправки
    print(f"sent {len(items)} items")


if __name__ == "__main__":
    main()
