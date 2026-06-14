"""Greeting header section.

Renders the big centered greeting + a date/time line, as a normal (reorderable,
configurable) section. The greeting is either the rotating built-in one or, when
this section opts into AI, a Claude-written line from a ready-made `style`
preset (morning/afternoon/evening/weekend) or a custom `prompt`.

Options:
    use_claude    use Claude when AI is active (default true)
    style         preset prompt: morning | afternoon | evening | weekend
    prompt        custom AI prompt (overrides `style`)
    date_format   strftime for the line under the greeting (default "%A, %d %B %Y")
"""

from __future__ import annotations

from ..brief import Section, Title
from ..greetings import GREETING_PRESETS, GREETING_SYSTEM, greeting_for
from ..llm import generate

DEFAULT_DATE_FORMAT = "%A, %d %B %Y"


def _greeting_text(section_cfg, ctx) -> str:
    if not (section_cfg.get("use_claude", True) and ctx.config.claude.active):
        return greeting_for(ctx.now.date())

    prompt = (section_cfg.get("prompt") or "").strip()
    if not prompt:
        style = section_cfg.get("style", "morning")
        prompt = GREETING_PRESETS.get(style, GREETING_PRESETS["morning"])

    text = generate(
        ctx.config.claude,
        system=GREETING_SYSTEM,
        prompt=f"{prompt} Today is {ctx.now:%A, %B %d}.",
        max_tokens=32,
        cache_key=f"greeting:{ctx.now:%Y-%m-%d}:{prompt}",
    )
    if text:
        line = text.strip().splitlines()[0].strip().strip('"').strip()
        if line:
            return line[:40]
    return "(AI greeting failed)"


def build(section_cfg, ctx) -> Section | None:
    fmt = section_cfg.get("date_format", DEFAULT_DATE_FORMAT)
    try:
        subtitle = ctx.now.strftime(fmt)
    except (ValueError, TypeError):
        subtitle = ctx.now.strftime(DEFAULT_DATE_FORMAT)
    return Section("", [Title(_greeting_text(section_cfg, ctx), subtitle)], bare=True)
