"""Разбор новости на стандартизированные поля: технопарк, страна, суть.

Всё на правилах, без внешних API — боту не нужен ни один платный ключ.
"""
import html
import re

# Известные площадки: ловим их, даже если в заголовке нет слова "park".
# Ключ — подстрока в нижнем регистре, значение — (каноничное имя, страна, флаг).
KNOWN_PARKS = {
    "sophia antipolis": ("Sophia Antipolis", "Франция", "🇫🇷"),
    "zhongguancun": ("Zhongguancun", "Китай", "🇨🇳"),
    "hub71": ("Hub71", "ОАЭ", "🇦🇪"),
    "kendall square": ("Kendall Square", "США", "🇺🇸"),
    "research triangle": ("Research Triangle Park", "США", "🇺🇸"),
    "skolkovo": ("Сколково", "Россия", "🇷🇺"),
    "сколково": ("Сколково", "Россия", "🇷🇺"),
    "innopolis": ("Иннополис", "Россия", "🇷🇺"),
    "иннополис": ("Иннополис", "Россия", "🇷🇺"),
    "технополис москва": ("Технополис Москва", "Россия", "🇷🇺"),
    "silicon roundabout": ("Silicon Roundabout", "Великобритания", "🇬🇧"),
    "biopolis": ("Biopolis", "Сингапур", "🇸🇬"),
    "one-north": ("one-north", "Сингапур", "🇸🇬"),
    "hsinchu": ("Hsinchu Science Park", "Тайвань", "🇹🇼"),
    "longtan": ("Longtan Science Park", "Тайвань", "🇹🇼"),
    "tsukuba": ("Tsukuba Science City", "Япония", "🇯🇵"),
    "daedeok": ("Daedeok Innopolis", "Южная Корея", "🇰🇷"),
    "medicon valley": ("Medicon Valley", "Дания/Швеция", "🇩🇰"),
    "adlershof": ("Adlershof", "Германия", "🇩🇪"),
    "leuven": ("Leuven / imec", "Бельгия", "🇧🇪"),
    "technion": ("Technion", "Израиль", "🇮🇱"),
    "yachay": ("Yachay Tech City", "Эквадор", "🇪🇨"),
    "ruta n": ("Ruta N", "Колумбия", "🇨🇴"),
    "qiddiya": ("Qiddiya", "Саудовская Аравия", "🇸🇦"),
    "neom": ("NEOM / Oxagon", "Саудовская Аравия", "🇸🇦"),
    "katowice": ("Katowice SEZ", "Польша", "🇵🇱"),
}

# Страна по упоминанию в тексте — только однозначные маркеры.
COUNTRY_HINTS = [
    (r"\b(cambridge|oxford|manchester|london|uk|britain|british|england|scotland|wales)\b",
     "Великобритания", "🇬🇧"),
    (r"\b(vietnam|vietnamese|ho chi minh|hanoi|da nang)\b", "Вьетнам", "🇻🇳"),
    (r"\b(hong kong)\b", "Гонконг", "🇭🇰"),
    (r"\b(taiwan|taiwanese|taipei|tsmc)\b", "Тайвань", "🇹🇼"),
    (r"\b(singapore)\b", "Сингапур", "🇸🇬"),
    (r"\b(abu dhabi|dubai|uae|emirates)\b", "ОАЭ", "🇦🇪"),
    (r"\b(saudi|riyadh|jeddah)\b", "Саудовская Аравия", "🇸🇦"),
    (r"\b(china|chinese|shenzhen|beijing|shanghai|suzhou)\b", "Китай", "🇨🇳"),
    (r"\b(india|indian|bengaluru|bangalore|hyderabad|gujarat)\b", "Индия", "🇮🇳"),
    (r"\b(japan|japanese|tokyo|osaka)\b", "Япония", "🇯🇵"),
    (r"\b(korea|korean|seoul|daejeon)\b", "Южная Корея", "🇰🇷"),
    (r"\b(germany|german|berlin|munich|dresden)\b", "Германия", "🇩🇪"),
    (r"\b(france|french|paris|grenoble|toulouse|cannes)\b", "Франция", "🇫🇷"),
    (r"\b(spain|spanish|madrid|barcelona|malaga)\b", "Испания", "🇪🇸"),
    (r"\b(italy|italian|milan|turin)\b", "Италия", "🇮🇹"),
    (r"\b(netherlands|dutch|eindhoven|amsterdam|delft)\b", "Нидерланды", "🇳🇱"),
    (r"\b(belgium|belgian|brussels|leuven)\b", "Бельгия", "🇧🇪"),
    (r"\b(sweden|swedish|stockholm|lund)\b", "Швеция", "🇸🇪"),
    (r"\b(finland|finnish|helsinki|espoo|oulu)\b", "Финляндия", "🇫🇮"),
    (r"\b(denmark|danish|copenhagen)\b", "Дания", "🇩🇰"),
    (r"\b(norway|norwegian|oslo|trondheim)\b", "Норвегия", "🇳🇴"),
    (r"\b(poland|polish|warsaw|krakow|wroclaw)\b", "Польша", "🇵🇱"),
    (r"\b(ireland|irish|dublin|cork)\b", "Ирландия", "🇮🇪"),
    (r"\b(portugal|portuguese|lisbon|porto)\b", "Португалия", "🇵🇹"),
    (r"\b(israel|israeli|tel aviv|haifa)\b", "Израиль", "🇮🇱"),
    (r"\b(turkey|turkish|istanbul|ankara|teknopark)\b", "Турция", "🇹🇷"),
    (r"\b(brazil|brazilian|sao paulo|campinas)\b", "Бразилия", "🇧🇷"),
    (r"\b(colombia|colombian|medell)\b", "Колумбия", "🇨🇴"),
    (r"\b(mexico|mexican|monterrey|guadalajara)\b", "Мексика", "🇲🇽"),
    (r"\b(canada|canadian|toronto|montreal|waterloo|vancouver)\b", "Канада", "🇨🇦"),
    (r"\b(australia|australian|sydney|melbourne|brisbane)\b", "Австралия", "🇦🇺"),
    (r"\b(kazakhstan|almaty|astana)\b", "Казахстан", "🇰🇿"),
    (r"\b(uzbekistan|tashkent)\b", "Узбекистан", "🇺🇿"),
    (r"(россия|российск|москв|казан|новосибирск|татарстан|сколков|иннополис)",
     "Россия", "🇷🇺"),
    (r"\b(u\.s\.|usa|united states|american|california|texas|boston|massachusetts|"
     r"north carolina|san diego|arizona|ohio|michigan|georgia|florida)\b", "США", "🇺🇸"),
]

# Имя площадки прямо из текста: "<Название> Science Park", "<Название> Innovation District" и т.п.
PARK_PATTERN = re.compile(
    r"\b((?:[A-Z][\w&'’\-]*\.?\s+){1,4}"
    r"(?:Science|Technology|Tech|Research|Innovation|Industrial|Business|Medical|"
    r"High-Tech|Hi-Tech|Software|Digital)\s+"
    r"(?:Park|Parks|Campus|District|Districts|Hub|City|Zone|Valley|Centre|Center))\b"
)
PARK_PATTERN_RU = re.compile(
    r"(?:технопарк[а-я]*|технополис[а-я]*|ОЭЗ|особ[а-я]+\s+экономическ[а-я]+\s+зон[а-я]+)"
    r"\s+[«\"]?([А-ЯЁA-Z][\wА-Яа-яЁё\-\s]{2,40}?)[»\"]?(?=[\s,.;:—–-]|$)"
)

# Google News клеит к заголовку " - Название издания". Отрезаем последний
# такой хвост, если он короткий и не содержит внутри ещё одного разделителя.
TITLE_TAIL_RE = re.compile(r"\s+[-–—]\s+([^-–—]{2,45})$")

# Названием площадки не может быть глагол или оценочное слово. Берём только
# то, что стоит ЛЕВЕЕ первого такого слова: "Fortinet Opens New ... Innovation
# Hub" -> "Fortinet Innovation Hub", а "Launch New AI-Powered ..." -> ничего.
ACTION_WORDS = {
    "opens", "open", "opening", "opened", "launch", "launches", "launched",
    "launching", "announces", "announce", "announced", "unveils", "unveil",
    "unveiled", "plans", "plan", "planned", "builds", "build", "building",
    "backs", "back", "backed", "joins", "join", "joined", "hosts", "host",
    "hosted", "expands", "expand", "expanded", "adds", "add", "added",
    "creates", "create", "created", "approves", "approve", "approved",
    "reveals", "reveal", "revealed", "names", "named", "sets", "set",
    "new", "first", "second", "third", "major", "top", "best", "next",
    "company-owned", "ai-powered", "state-of-the-art", "multi-million",
    "the", "a", "an", "its", "his", "her", "their", "our", "this", "that",
    "to", "at", "in", "on", "with", "and", "of", "for", "from", "by",
    "helps", "help", "helped", "fund", "funds", "funded", "funding",
    "wins", "win", "won", "gets", "get", "got", "picks", "pick", "picked",
    "eyes", "eye", "seeks", "seek", "sought", "starts", "start", "started",
    "begins", "begin", "began", "boosts", "boost", "boosted", "marks",
    "hits", "hit", "tops", "top", "moves", "move", "moved", "brings",
    "bring", "brought", "takes", "take", "took", "makes", "make", "made",
}

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZА-ЯЁ0-9\"«])")
# Google News вешает на summary хвост вида "&nbsp;<источник>" — он мусорный.
GN_TAIL_RE = re.compile(r"\s*[-–—]\s*[A-Z][\w .&]{2,40}$")


def clean_text(raw):
    """HTML-разметка и сущности -> плоский текст в одну строку."""
    if not raw:
        return ""
    text = TAG_RE.sub(" ", raw)
    text = html.unescape(text)
    return WS_RE.sub(" ", text).strip()


def split_title_source(title):
    """'Заголовок - Издание' -> ('Заголовок', 'Издание')."""
    match = TITLE_TAIL_RE.search(title)
    if not match:
        return title, ""
    return title[: match.start()].strip(), match.group(1).strip()


def detect_country(text):
    lowered = text.lower()
    for pattern, country, flag in COUNTRY_HINTS:
        if re.search(pattern, lowered):
            return country, flag
    return "", ""


def trim_to_proper_name(phrase):
    """Оставляем только собственное имя перед типовым словом.

    Пустая строка означает "определить не удалось" — это честнее, чем
    выдать кусок заголовка за название технопарка.
    """
    words = phrase.split()
    # Типовое слово ("Park", "Hub", ...) и всё, что справа, оставляем как есть.
    tail_start = len(words) - 1
    while tail_start > 0 and words[tail_start - 1].lower() in {
        "science", "technology", "tech", "research", "innovation", "industrial",
        "business", "medical", "high-tech", "hi-tech", "software", "digital",
    }:
        tail_start -= 1

    head, tail = words[:tail_start], words[tail_start:]
    kept = []
    for word in head:
        if word.lower() in ACTION_WORDS:
            break
        kept.append(word)

    if not kept:
        return ""
    return " ".join(kept + tail)


def extract_park(title, summary):
    """Возвращает название площадки или '' — врать не надо, лучше пусто."""
    blob = f"{title}. {summary}"
    lowered = blob.lower()

    for needle, (name, _country, _flag) in KNOWN_PARKS.items():
        if needle in lowered:
            return name

    match = PARK_PATTERN.search(blob)
    if match:
        candidate = trim_to_proper_name(WS_RE.sub(" ", match.group(1)).strip())
        if candidate:
            return candidate

    match = PARK_PATTERN_RU.search(blob)
    if match:
        candidate = match.group(1).strip(" -—–")
        if len(candidate) > 2:
            return candidate
    return ""


def park_country(park, title, summary):
    for needle, (name, country, flag) in KNOWN_PARKS.items():
        if park and name.lower() == park.lower():
            return country, flag
        if needle in f"{title} {summary}".lower():
            return country, flag
    return detect_country(f"{title} {summary}")


def summarize(summary, title, limit=260):
    """Короткое 'что сделали': 1-2 предложения без хвостов и дублей заголовка."""
    text = clean_text(summary)
    text = GN_TAIL_RE.sub("", text).strip()

    # Многие фиды кладут в summary тот же заголовок — тогда описания просто нет.
    if not text or text.lower().startswith(title.lower()[:60].strip()):
        remainder = text[len(title):].strip(" -–—:.") if text else ""
        if len(remainder) < 40:
            return ""
        text = remainder

    sentences = SENTENCE_RE.split(text)
    out = ""
    for sentence in sentences[:2]:
        if len(out) + len(sentence) + 1 > limit:
            break
        out = f"{out} {sentence}".strip()
    if not out:
        out = text[:limit]
    if len(out) < len(text):
        out = out.rstrip(".") + "…"
    return out


def normalize(title, summary):
    """Единая точка входа: сырые поля фида -> поля карточки."""
    title, publisher = split_title_source(clean_text(title))
    summary_raw = summary
    summary_clean = clean_text(summary)
    # Выкидываем имя издания из текста, по которому ищем площадку.
    search_text = summary_clean.replace(publisher, " ") if publisher else summary_clean
    park = extract_park(title, search_text)
    country, flag = park_country(park, title, search_text)
    return {
        "title": title,
        "publisher": publisher,
        "park": park,
        "country": country,
        "flag": flag,
        "what": summarize(summary_raw, title),
    }


META_RE = re.compile(
    r"<meta[^>]+(?:name|property)=[\"']"
    r"(?:og:description|twitter:description|description)[\"'][^>]*>",
    re.IGNORECASE,
)
CONTENT_RE = re.compile(r"content=[\"']([^\"']*)[\"']", re.IGNORECASE)


def extract_meta_description(markup):
    """Достаёт og:description / meta description из HTML-страницы статьи."""
    if isinstance(markup, bytes):
        markup = markup.decode("utf-8", errors="replace")
    best = ""
    for tag in META_RE.findall(markup):
        found = CONTENT_RE.search(tag)
        if not found:
            continue
        value = clean_text(html.unescape(found.group(1)))
        if len(value) > len(best):
            best = value
    return best


# Подстроки, а не окончания: www.google-analytics.com не оканчивается на
# google.com и раньше проходил фильтр, подсовывая нам analytics.js.
GOOGLE_HOSTS = ("google", "gstatic", "doubleclick", "googletagmanager", "ggpht")
HREF_RE = re.compile(r"""(?:href|data-n-au)=["'](https?://[^"']+)["']""", re.IGNORECASE)


def resolve_google_news(markup):
    """Из промежуточной страницы Google News достаём ссылку на издателя."""
    if isinstance(markup, bytes):
        markup = markup.decode("utf-8", errors="replace")
    for candidate in HREF_RE.findall(markup):
        host = candidate.split("/")[2].lower() if "//" in candidate else ""
        if host and not any(g in host for g in GOOGLE_HOSTS):
            return candidate
    return ""


def fetch_description(url, timeout=8, depth=0, debug=False):
    """Сетевой поход за описанием. Любая ошибка -> пустая строка, дайджест не падает."""
    import sys
    import urllib.request

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; technopark-digest/1.0)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            ctype = response.headers.get("Content-Type", "")
            if "html" not in ctype.lower():
                return ""
            markup = response.read(400_000)
            final_host = urllib.parse.urlsplit(response.geturl()).netloc.lower()
    except Exception as exc:
        if debug:
            print(f"DEBUG описание не получено {url[:60]}... -> {exc!r}", file=sys.stderr)
        return ""

    description = extract_meta_description(markup)
    if description:
        return description

    # Застряли на промежуточной странице Google News — идём к издателю.
    if "news.google.com" in final_host and depth < 1:
        target = resolve_google_news(markup)
        if debug:
            print(f"DEBUG застряли на Google News, цель -> {target[:70] or 'не найдена'}",
                  file=sys.stderr)
        if target:
            return fetch_description(target, timeout=timeout, depth=depth + 1, debug=debug)
    if debug:
        print(f"DEBUG описания нет на странице {final_host}", file=sys.stderr)
    return ""
