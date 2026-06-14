"""Editable-field schema for each section type.

Drives the setup web UI's forms and save-time validation. Every section also has
the common fields `title` (text), `enabled` (bool), and `icon` (select) handled
by the editor itself; the per-type `fields` below are the type-specific options.
A `bare` spec (the greeting) draws its own centered header, so the editor hides
the Title/Icon fields for it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Header icon keys available in assets/icons/ ("" = no icon).
AVAILABLE_ICONS = [
    "", "cake", "calendar", "sun", "cloud", "hourglass", "book", "lightbulb",
    "smiley", "moon", "satellite", "planet", "art", "oncall",
]


@dataclass
class Field:
    key: str
    label: str
    kind: str = "text"  # text | secret | int | bool | select | textarea
    default: object = None
    help: str = ""
    choices: tuple = ()  # for kind == "select"


@dataclass
class SectionSpec:
    type: str
    label: str
    description: str = ""
    requires_claude: bool = False
    bare: bool = False  # renders its own header (greeting) — hide Title/Icon fields
    fields: list[Field] = field(default_factory=list)


SECTION_SPECS: dict[str, SectionSpec] = {
    "greeting": SectionSpec(
        "greeting", "Greeting header", "Big centered greeting + a date line.",
        bare=True,  # draws its own centered header; no section Title/Icon
        fields=[
            Field("use_claude", "Use AI (Claude)", "bool", True,
                  "Claude writes the greeting when AI is on; otherwise a rotating built-in."),
            Field("style", "AI style", "select", "morning",
                  "Ready-made prompt tone (ignored if a custom prompt is set).",
                  choices=("morning", "afternoon", "evening", "weekend")),
            Field("prompt", "Custom AI prompt", "textarea",
                  help="Overrides the style preset."),
            Field("date_format", "Date format", "text", "%A, %d %B %Y",
                  "strftime, e.g. %A, %d %B %Y · %H:%M"),
        ],
    ),
    "weather": SectionSpec(
        "weather", "Weather", "Today's high/low (°C) + a pictogram.",
        fields=[Field("api_key", "OpenWeatherMap API key", "secret",
                      help="Free key from openweathermap.org. Uses [location].")],
    ),
    "birthdays": SectionSpec(
        "birthdays", "Birthdays", "Birthdays from an iCal feed, with checkboxes.",
        fields=[
            Field("ical_url", "iCal URL", "text", help="A published .ics URL (webcal:// ok)."),
            Field("horizon_days", "Look-ahead days", "int", 0, "0 = today only."),
            Field("checkbox", "Show checkboxes", "bool", True),
        ],
    ),
    "events": SectionSpec(
        "events", "Upcoming events", "Events from an iCal feed.",
        fields=[
            Field("ical_url", "iCal URL", "text", help="A published .ics URL (webcal:// ok)."),
            Field("horizon_days", "Days ahead", "int", 3),
            Field("max_items", "Max events", "int", 6),
        ],
    ),
    "oncall": SectionSpec(
        "oncall", "On-call status", "Whether you're on call, from an iCal feed.",
        fields=[
            Field("ical_url", "iCal URL", "text"),
            Field("keyword", "Match keyword", "text", "primary",
                  "Only events whose title contains this (case-insensitive)."),
            Field("horizon_days", "Look-ahead days", "int", 14),
            Field("hide_when_off", "Hide when not on call", "bool", False),
        ],
    ),
    "onthisday": SectionSpec(
        "onthisday", "On this day", "A historical event for today's date.",
        fields=[
            Field("max_items", "How many", "int", 1),
            Field("min_age_years", "Minimum age (years)", "int", 50,
                  "Skip recent news; only events at least this old."),
        ],
    ),
    "word": SectionSpec(
        "word", "Word of the day", "A rare/SAT word with a definition.",
        fields=[Field("use_claude", "Use AI (Claude)", "bool", True,
                      "Define with Claude (adds an example) when AI is on; "
                      "otherwise use the free dictionary.")],
    ),
    "trivia": SectionSpec(
        "trivia", "Trivia", "A trivia fact.",
        fields=[Field("mode", "Mode", "select", "today", choices=("today", "random"))],
    ),
    "daylight": SectionSpec("daylight", "Daylight", "Sunrise, sunset, and day length."),
    "joke": SectionSpec("joke", "Dad joke", "A dad joke from icanhazdadjoke."),
    "iss": SectionSpec("iss", "ISS tracker", "Live ISS position on a world map."),
    "moon": SectionSpec("moon", "Moon phase", "Tonight's moon phase, drawn."),
    "planets": SectionSpec("planets", "Visible planets", "Planets above the horizon tonight."),
    "ascii": SectionSpec(
        "ascii", "ASCII art", "A daily ASCII-art doodle.",
        fields=[
            Field("use_claude", "Use AI (Claude)", "bool", False,
                  "Draw with Claude when AI is on; otherwise the bundled gallery."),
            Field("subject", "Subject", "text", help="Fixed subject; blank = Claude picks daily."),
        ],
    ),
    "ai": SectionSpec(
        "ai", "AI (custom prompt)", "Your prompt, answered by Claude, length-capped.",
        requires_claude=True,
        fields=[
            Field("prompt", "Prompt", "textarea", help="What Claude should write."),
            Field("max_chars", "Max characters", "int", 280),
        ],
    ),
}
