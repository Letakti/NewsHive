import html
from typing import Iterable


def _extract_title_and_link(news_text: str) -> tuple[str, str]:
    """Пытается вытащить title/link из строк вида `📰 ...\n🔗 ...`."""
    lines = [line.strip() for line in news_text.splitlines() if line.strip()]
    title = lines[0] if lines else "Без названия"
    link = ""

    for line in lines:
        if line.startswith("📰"):
            title = line.replace("📰", "", 1).strip() or title
        if line.startswith("🔗"):
            link = line.replace("🔗", "", 1).strip()

    if not link and len(lines) > 1:
        link = lines[-1]

    return title, link


def format_news_batch(news_items: Iterable[str], start_index: int = 1, title: str = "🗞 Новости") -> str:
    """Форматирует батч из 3-5 новостей в единый HTML-блок."""
    rows: list[str] = [f"<b>{html.escape(title)}</b>"]

    for idx, news_text in enumerate(news_items, start=start_index):
        item_title, item_link = _extract_title_and_link(news_text)
        safe_title = html.escape(item_title)
        safe_link = html.escape(item_link, quote=True)

        if safe_link:
            rows.append(f'{idx}. <a href="{safe_link}">{safe_title}</a>')
        else:
            rows.append(f"{idx}. {safe_title}")

    return "\n".join(rows)

