"""Final Jeopardy -- tonight's category, clue, and answer.

Scraped from jeopardytonight.com (no API). The homepage has three TablePress
tables with stable IDs:
  #tablepress-19        category + clue, combined in one <td> as "Category - Clue"
  #tablepress-19-no-2   the answer (e.g. "Who is James Gadsden?")
  #tablepress-19-no-3   contestant scores (unused)

The answer is emitted as an ``UpsideDown`` item so it prints rotated 180 degrees:
read the clue, then flip the paper to reveal the answer (classic trivia-card UX).

Network failures degrade to "(unavailable)" via ``safe_build``, and ``get_text``
keeps a stale-cache fallback so a brief still prints yesterday's clue if the
site is briefly unreachable.
"""

from __future__ import annotations

from ..brief import Banner, Section, Text, UpsideDown
from ._http import get_text

URL = "https://jeopardytonight.com/"


def build(section_cfg, ctx) -> Section | None:
    title = section_cfg.title or "FINAL JEOPARDY"
    cache_hours = section_cfg.get("cache_hours", 6) or 6
    html = get_text(URL, ttl=cache_hours * 3600)
    if not html:
        return Section(title, [Text("(unavailable)")])
    data = _parse(html)
    if not data:
        return Section(title, [Text("(unavailable)")])
    return Section(title, [
        Banner(data["category"]),    # bold category header
        Text(data["clue"]),          # the clue
        UpsideDown(data["answer"]),  # answer, printed upside down
    ])


def _parse(html: str) -> dict | None:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    clue_td = soup.select_one("#tablepress-19 td")
    ans_td = soup.select_one("#tablepress-19-no-2 td")
    if not clue_td or not ans_td:
        return None
    # Collapse any internal whitespace/newlines so the clue prints as one
    # clean, wrap-at-render-time paragraph.
    raw = _clean(clue_td.get_text(" ", strip=True))
    category, _, clue = raw.partition(" - ")
    answer = _clean(ans_td.get_text(" ", strip=True))
    if not answer:
        return None
    return {
        "category": category.strip(),
        "clue": clue.strip(),
        "answer": answer,
    }


def _clean(text: str) -> str:
    """Collapse runs of whitespace (incl. newlines) to single spaces."""
    return " ".join(text.split())
