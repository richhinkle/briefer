"""Daily sudoku puzzle from the Dosuku API.

Fetches a random puzzle and renders the grid as a monospace block suitable for
a thermal receipt printer. Optionally prints the solution after a separator.
The API is free and requires no authentication.
"""

from __future__ import annotations

from ..brief import Mono, Section, Text
from ._http import get_json

API_URL = "https://sudoku-api.vercel.app/api/dosuku"


def _format_grid(grid: list[list[int]]) -> str:
    """Format a 9x9 grid with box-drawing borders. Empty cells (0) shown as dots."""
    lines = []
    lines.append("+-------+-------+-------+")
    for i, row in enumerate(grid):
        cells = []
        for j, val in enumerate(row):
            if j % 3 == 0:
                cells.append("| ")
            cells.append(str(val) if val != 0 else ".")
            cells.append(" ")
        cells.append("|")
        lines.append("".join(cells))
        if (i + 1) % 3 == 0:
            lines.append("+-------+-------+-------+")
    return "\n".join(lines)


def _format_solution_compact(solution: list[list[int]]) -> str:
    """Format solution as compact space-separated rows."""
    return "\n".join(" ".join(str(v) for v in row) for row in solution)


def build(section_cfg, ctx) -> Section | None:
    title = section_cfg.title or "DAILY SUDOKU"
    show_solution = section_cfg.get("show_solution", True)

    # Short TTL so repeated prints in a day get the same puzzle (API is random),
    # but the cache refreshes daily.
    data = get_json(API_URL, ttl=43_200)
    if not data:
        return Section(title, [Text("(unavailable)")])

    try:
        grid_data = data["newboard"]["grids"][0]
        puzzle = grid_data["value"]
        solution = grid_data["solution"]
        difficulty = grid_data["difficulty"]
    except (KeyError, IndexError, TypeError):
        return Section(title, [Text("(unavailable)")])

    items = []
    items.append(Text(f"Difficulty: {difficulty}"))
    items.append(Mono(_format_grid(puzzle)))

    if show_solution:
        items.append(Text(""))  # spacing
        items.append(Text("Solution:"))
        items.append(Mono(_format_solution_compact(solution)))

    return Section(title, items)
