# Jeopardy Section — Design & Implementation Plan

## Data Source

**Site:** https://jeopardytonight.com/  
**No API** — scrape the homepage HTML daily.

### Page Structure

The homepage contains three `<table>` elements with predictable IDs:

| Table ID | Contents |
|---|---|
| `tablepress-19` | Category + clue (combined in one `<td>`) |
| `tablepress-19-no-2` | Answer (e.g. "Who is James Gadsden?") |
| `tablepress-19-no-3` | Contestant scores (not needed for this section) |

**Category + clue** are in a single `<td>` formatted as:
```
{Category} - {Clue text}
```
Split on ` - ` (first occurrence) to separate them.

### Scraper sketch

```python
import requests
from bs4 import BeautifulSoup

def fetch_final_jeopardy():
    html = requests.get("https://jeopardytonight.com/", timeout=10).text
    soup = BeautifulSoup(html, "html.parser")

    clue_td = soup.select_one("#tablepress-19 td")
    answer_td = soup.select_one("#tablepress-19-no-2 td")

    if not clue_td or not answer_td:
        return None

    raw = clue_td.get_text(" ", strip=True)
    category, _, clue = raw.partition(" - ")

    return {
        "category": category.strip(),
        "clue": clue.strip(),
        "answer": answer_td.get_text(" ", strip=True).strip(),
    }
```

Add `beautifulsoup4` to `requirements.txt`.

Use `_http.get_text` (briefer's caching wrapper) instead of raw `requests`
so the result is cached and has a stale fallback on network failure.

---

## Section Design

### Print layout

```
┌─────────────────────────────┐
│  FINAL JEOPARDY             │  ← section heading (existing rule/heading style)
│                             │
│  NOTABLE AMERICANS          │  ← category, bold/large
│                             │
│  Known in Mexican history   │  ← clue text, normal body size, word-wrapped
│  as the sale of the         │
│  Mesilla Valley, the        │
│  30,000-square-mile deal    │
│  was negotiated by this     │
│  U.S. diplomat              │
│  ─────────────────────────  │  ← thin rule separating clue from answer
│  ʇspɐpsɐɾ sǝɯɐɾ sı oɥM    │  ← answer, printed UPSIDE DOWN
└─────────────────────────────┘
```

The upside-down answer means you read the clue first, then flip the paper
to reveal the answer — classic trivia card UX.

### New item types needed

Add to `daily_brief/brief.py`:

```python
@dataclass
class UpsideDown:
    """A text item rendered rotated 180°."""
    text: str
```

### Rendering upside-down text

Since briefer renders everything to a PIL bitmap, rotating is easy:

1. Render the answer text onto a **temporary canvas** (same width, enough height).
2. Call `.rotate(180)` on that sub-image.
3. Paste it back onto the main canvas.

In `render.py`, add a `Canvas._draw_upside_down(item)` method:

```python
def _draw_upside_down(self, item: UpsideDown) -> None:
    # Measure how tall the text will be
    lines = self._wrap(item.text, self.f_body, self.W - 2 * self.margin)
    h = len(lines) * (self.f_body.size + 4) + self.margin
    # Render to a temp image
    tmp = Image.new("L", (self.W, h), 255)
    draw = ImageDraw.Draw(tmp)
    y = self.margin // 2
    for line in lines:
        draw.text((self.margin, y), line, font=self.f_body, fill=0)
        y += self.f_body.size + 4
    # Rotate and paste
    rotated = tmp.rotate(180)
    self.img.paste(rotated, (0, self.y))
    self.y += h
```

### New source file

`daily_brief/sources/jeopardy.py`:

```python
from ..brief import Section, Text, Banner, UpsideDown
from .._http import get_text

TITLE = "FINAL JEOPARDY"

def build(cfg, ctx):
    html = get_text("https://jeopardytonight.com/", ttl=3600 * 6)
    data = _parse(html)
    if not data:
        return Section(title=TITLE, items=[Text("(unavailable)")])

    items = [
        Banner(data["category"]),      # bold category header
        Text(data["clue"]),            # the clue
        UpsideDown(data["answer"]),    # answer, upside down
    ]
    return Section(title=TITLE, items=items)

def _parse(html):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    clue_td  = soup.select_one("#tablepress-19 td")
    ans_td   = soup.select_one("#tablepress-19-no-2 td")
    if not clue_td or not ans_td:
        return None
    raw = clue_td.get_text(" ", strip=True)
    category, _, clue = raw.partition(" - ")
    return {
        "category": category.strip(),
        "clue":     clue.strip(),
        "answer":   ans_td.get_text(" ", strip=True).strip(),
    }
```

Register in `sources/__init__.py`:
```python
from .jeopardy import build as jeopardy_build
BUILDERS["jeopardy"] = jeopardy_build
```

Add a `SectionSpec` in `sources/specs.py` so the web UI can configure it:
```python
"jeopardy": SectionSpec(
    label="Final Jeopardy",
    fields=[],   # no user-configurable fields needed
),
```

### config.toml usage

```toml
[[briefs.sections]]
type = "jeopardy"
title = "FINAL JEOPARDY"
enabled = true
```

---

## Dependencies

Add to `requirements.txt`:
```
beautifulsoup4>=4.12
```

---

## Implementation order

1. Add `beautifulsoup4` to `requirements.txt`
2. Add `UpsideDown` item type to `brief.py`
3. Add `Canvas._draw_upside_down()` to `render.py`
4. Wire `UpsideDown` into `Canvas._draw_item()` dispatch
5. Create `sources/jeopardy.py`
6. Register in `sources/__init__.py` and `sources/specs.py`
7. Test with `python -m daily_brief --dry-run --brief <brief-with-jeopardy>`
8. Add to a brief in `config.toml` on the Pi and do a real print test

## Open questions

- Should the thin rule between clue and answer be part of the `UpsideDown` item
  or drawn separately by the jeopardy source?
- Cache TTL: 6 hours feels right (the answer goes up after the show airs ~7pm ET).
  Could make it configurable as `cache_hours` in the section config.
- Should `UpsideDown` be a general-purpose item type reusable by other sources,
  or a jeopardy-specific rendering path?
