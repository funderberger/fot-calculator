#!/usr/bin/env python3
"""Самопроверка: гоняется в CI перед отправкой, сети не требует."""
import datetime as dt
import email.utils
import pathlib
import sys
import tempfile

import digest
import extract

FAILURES = []


def check(name, condition, detail=""):
    if condition:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        FAILURES.append(name)


def make_feed(path):
    now = dt.datetime.now(dt.timezone.utc)
    rows = [
        ("Cambridge Science Park submits masterplan",
         "The expansion would unlock 20,000 jobs and triple annual output to over &#163;3bn.", 3),
        ("Ho Chi Minh City High-Tech Park to expand with science focus",
         "The park expands by nearly 195 hectares, targeting $1.6bn of investment. - VIR", 6),
        ("Celebrity buys a mansion", "Totally unrelated content.", 2),
        ("Old story about a research park", "Stale item.", 200),
    ]
    body = "".join(
        f"<item><title>{t}</title><link>https://example.org/{i}</link>"
        f"<description><![CDATA[{d}]]></description>"
        f"<pubDate>{email.utils.format_datetime(now - dt.timedelta(hours=h))}</pubDate></item>"
        for i, (t, d, h) in enumerate(rows)
    )
    path.write_text(
        f'<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>{body}</channel></rss>'
    )


def main():
    print("extract:")
    card = extract.normalize(
        "Cambridge Science Park submits masterplan",
        "<p>The expansion would unlock 20,000 jobs.</p>",
    )
    check("название площадки", card["park"] == "Cambridge Science Park", card["park"])
    check("страна", card["country"] == "Великобритания", card["country"])
    check("html вычищен", "<p>" not in card["what"], card["what"])

    ru = extract.normalize("Технопарк «Иннополис» открыл корпус",
                           "ОЭЗ Иннополис ввела корпус на 40 тыс. кв. м.")
    check("русская площадка", ru["park"] == "Иннополис", ru["park"])
    check("не режет сокращения", ru["what"].endswith("кв. м."), ru["what"])

    check("нет площадки -> пусто, а не выдумка",
          extract.normalize("Generic story", "Nothing here.")["park"] == "")

    # Регрессии по боевому прогону 16.09.2026: см. лог run 35082825442.
    gn = extract.normalize(
        "Fortinet Opens New Company-Owned Innovation Hub in New York City - marketscreener.com",
        "Fortinet Opens New Company-Owned Innovation Hub in New York City",
    )
    check("хвост издания отрезан от заголовка",
          gn["title"].endswith("New York City"), gn["title"])
    check("издание вынуто отдельно", gn["publisher"] == "marketscreener.com", gn["publisher"])
    check("глагол не попал в название площадки",
          gn["park"] == "Fortinet Innovation Hub", gn["park"])

    junk = extract.normalize(
        "Baptist Health, Nvidia Launch New AI-Powered Healthcare Innovation Hub - Becker's",
        "x",
    )
    check("без собственного имени площадка не выдумывается", junk["park"] == "", junk["park"])

    check("скрипт аналитики не принимается за статью",
          extract.resolve_google_news(
              b'<script src="https://www.google-analytics.com/a.js"></script>'
              b'<a href="https://vir.com.vn/real">t</a>'
          ) == "https://vir.com.vn/real")

    check("имя издания не выдаётся за технопарк",
          extract.normalize(
              "United States Space Academy starts to become a reality - EdTech Innovation Hub",
              "United States Space Academy starts to become a reality EdTech Innovation Hub",
          )["park"] == "")

    check("'Helps Fund' не попадает в название площадки",
          extract.normalize("Ohio Helps Fund Cleveland Housing Innovation District - X", "y")["park"] == "")

    check("промежуточная страница Google News разворачивается",
          extract.resolve_google_news(
              b'<a href="https://www.gstatic.com/x.js"></a>'
              b'<a href="https://vir.com.vn/real-article">t</a>'
          ) == "https://vir.com.vn/real-article")

    page = b'<meta property="og:description" content="Park expands by 195 hectares.">'
    check("og:description", extract.extract_meta_description(page) == "Park expands by 195 hectares.")

    print("digest:")
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = pathlib.Path(tmp)
        feed, config = tmpdir / "f.xml", tmpdir / "c.yml"
        make_feed(feed)
        config.write_text(
            f'feeds:\n  - name: "Test"\n    url: "{feed}"\n'
            'keywords: ["science park","high-tech park","research park"]\n'
            "trust_all: []\nmax_items: 10\nlookback_hours: 26\n"
        )
        digest.SEEN_PATH = tmpdir / "seen.json"

        import yaml
        cfg = yaml.safe_load(config.read_text())

        items, _, seen = digest.collect(cfg)
        check("нерелевантное отфильтровано", all("mansion" not in i["title"] for i in items))
        check("устаревшее отброшено", all("Old story" not in i["title"] for i in items))
        check("осталось 2 новости", len(items) == 2, len(items))

        for item in items:
            seen[item["key"]] = __import__("time").time()
        digest.save_seen(seen)
        check("дедупликация", len(digest.collect(cfg)[0]) == 0)

        text = digest.render(items, [])
        check("есть строка 'Технопарк'", "🏢 <b>Технопарк:</b>" in text)
        check("есть строка 'Что сделали'", "📌 <b>Что сделали:</b>" in text)
        check("есть ссылка", '🔗 <a href="' in text)

        long_text = digest.render(items * 300, [])
        parts = list(digest.chunks(long_text))
        check("нарезка под лимит Telegram",
              max(len(p) for p in parts) <= digest.TG_LIMIT, max(len(p) for p in parts))

    print()
    if FAILURES:
        print(f"ПРОВАЛЕНО: {len(FAILURES)}")
        return 1
    print("Все проверки пройдены.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
