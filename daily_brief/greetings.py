"""Funny header greetings, cycled by the day so each day gets a different one.

Kept short so they fit the title line on a 58mm receipt. `greeting_for(date)`
is deterministic for a given date.
"""

from __future__ import annotations

from datetime import date

GREETINGS = [
    "Rise & grind",
    "Good morning, legend",
    "Beep boop, it's news",
    "Another day, another roll",
    "You're awake! Bold move",
    "Hot off the press",
    "Fresh paper, fresh start",
    "Carpe that diem",
    "Today's the day",
    "Stay caffeinated",
    "Wakey wakey",
    "Seize the receipt",
    "Mornin', sunshine",
    "Brace for the day",
    "Let's do this thing",
    "Coffee first, then chaos",
    "New day, who dis",
    "The brief has landed",
    "Greetings, human",
    "Up and at 'em",
    "It's a brand new you",
    "Onwards & upwards",
    "Today, with feeling",
    "Make it a good one",
    "You got this",
    "Plot twist: it's morning",
    "Hello, gorgeous",
    "Time to be awesome",
    "Crush it today",
    "Eyes open, world ready",
    "Another fine morning",
    "Here we go again",
    "Deploy the day",
    "Reporting for duty",
    "Loading your day...",
    "Good news incoming",
    "Snooze you lose",
    "Best day ever (maybe)",
    "Smells like morning",
    "The paper hath spoken",
    "Stretch, yawn, conquer",
    "Today is undefeated",
    "Hustle mode: on",
    "Be the good news",
    "Morning, champ",
    "Fortune favors the awake",
    "A wild day appears",
    "Let's get briefing",
]


def greeting_for(day: date) -> str:
    """Pick a built-in greeting deterministically for the given date."""
    return GREETINGS[day.toordinal() % len(GREETINGS)]


# System prompt + ready-made AI prompts for the `greeting` section.
GREETING_SYSTEM = (
    "You write a single playful one-line greeting for the top of a daily "
    "briefing printed on a paper receipt. Keep it under 30 characters, upbeat "
    "and a little witty. No quotes, no emoji, no punctuation at the end."
)

GREETING_PRESETS = {
    "morning": "Write an upbeat good-morning greeting.",
    "afternoon": "Write a cheerful good-afternoon greeting.",
    "evening": "Write a calm, warm good-evening greeting.",
    "weekend": "Write a relaxed, fun weekend greeting.",
}
