"""Built-in adjacency candidates extracted from the attachment maps.

The source Word file stores maps as VML drawing objects. These tables are
generated from those VML coordinates and are intended to make the project
runnable. Keep the extraction note visible in reports until a human has checked
the map boundaries against the original attachment.
"""

from __future__ import annotations

from typing import Dict, Iterable, Mapping, Tuple

from .models import sorted_adjacency


def _pairs_to_adjacency(pairs: Iterable[Tuple[int, int]]) -> Dict[int, Tuple[int, ...]]:
    return sorted_adjacency(pairs)


def _hex_grid_8x8() -> Dict[int, Tuple[int, ...]]:
    adjacency = {node: set() for node in range(1, 65)}
    for row in range(8):
        for col in range(8):
            node = row * 8 + col + 1
            if col > 0:
                adjacency[node].add(node - 1)
            if col < 7:
                adjacency[node].add(node + 1)
            if row < 7:
                if row % 2 == 0:
                    candidates = (col - 1, col)
                else:
                    candidates = (col, col + 1)
                for next_col in candidates:
                    if 0 <= next_col < 8:
                        adjacency[node].add((row + 1) * 8 + next_col + 1)
            if row > 0:
                if (row - 1) % 2 == 0:
                    candidates = (col, col + 1)
                else:
                    candidates = (col - 1, col)
                for prev_col in candidates:
                    if 0 <= prev_col < 8:
                        adjacency[node].add((row - 1) * 8 + prev_col + 1)
    return {node: tuple(sorted(neighbors)) for node, neighbors in adjacency.items()}


LEVEL1_ADJACENCY = _pairs_to_adjacency(
    [
        (1, 2),
        (1, 25),
        (2, 3),
        (2, 4),
        (3, 4),
        (3, 5),
        (3, 24),
        (4, 5),
        (4, 6),
        (4, 7),
        (4, 24),
        (4, 25),
        (5, 6),
        (5, 8),
        (5, 10),
        (6, 7),
        (6, 8),
        (7, 8),
        (7, 22),
        (7, 23),
        (8, 9),
        (8, 10),
        (8, 18),
        (9, 14),
        (9, 15),
        (9, 16),
        (9, 18),
        (10, 11),
        (10, 13),
        (10, 15),
        (11, 12),
        (11, 13),
        (12, 13),
        (12, 14),
        (13, 14),
        (13, 15),
        (14, 15),
        (14, 16),
        (15, 16),
        (16, 18),
        (16, 19),
        (17, 18),
        (17, 21),
        (18, 19),
        (19, 20),
        (19, 27),
        (20, 21),
        (20, 27),
        (21, 22),
        (21, 23),
        (21, 27),
        (22, 23),
        (22, 24),
        (23, 24),
        (23, 26),
        (24, 25),
        (25, 26),
        (26, 27),
    ]
)


LEVEL3_ADJACENCY = _pairs_to_adjacency(
    [
        (1, 2),
        (1, 8),
        (2, 3),
        (2, 11),
        (3, 4),
        (3, 8),
        (3, 11),
        (3, 12),
        (4, 5),
        (4, 7),
        (4, 12),
        (5, 6),
        (5, 12),
        (6, 7),
        (6, 13),
        (7, 8),
        (7, 10),
        (7, 11),
        (8, 9),
        (8, 10),
        (9, 10),
        (10, 13),
        (11, 12),
        (12, 13),
    ]
)


LEVEL4_ADJACENCY = _pairs_to_adjacency(
    [
        (1, 2),
        (1, 6),
        (2, 3),
        (2, 6),
        (2, 7),
        (3, 4),
        (3, 7),
        (3, 8),
        (4, 5),
        (4, 8),
        (4, 9),
        (5, 9),
        (5, 10),
        (6, 7),
        (6, 11),
        (7, 8),
        (7, 11),
        (7, 12),
        (8, 9),
        (8, 12),
        (8, 13),
        (9, 10),
        (9, 13),
        (9, 14),
        (10, 14),
        (10, 15),
        (11, 12),
        (11, 16),
        (12, 13),
        (12, 16),
        (12, 17),
        (13, 14),
        (13, 17),
        (13, 18),
        (14, 15),
        (14, 18),
        (14, 19),
        (15, 19),
        (15, 20),
        (16, 17),
        (16, 21),
        (17, 18),
        (17, 21),
        (17, 22),
        (18, 19),
        (18, 22),
        (18, 23),
        (19, 20),
        (19, 23),
        (19, 24),
        (20, 24),
        (20, 25),
        (21, 22),
        (22, 23),
        (23, 24),
        (24, 25),
    ]
)


BUILTIN_ADJACENCY: Mapping[int, Dict[int, Tuple[int, ...]]] = {
    1: LEVEL1_ADJACENCY,
    2: _hex_grid_8x8(),
    3: LEVEL3_ADJACENCY,
    4: LEVEL4_ADJACENCY,
    5: LEVEL3_ADJACENCY,
    6: LEVEL4_ADJACENCY,
}


BUILTIN_MAP_NOTE = (
    "Adjacency was generated from VML/visible map geometry and should be treated "
    "as an auto-extracted candidate until manually checked."
)


def builtin_adjacency(level_id: int) -> Dict[int, Tuple[int, ...]]:
    return dict(BUILTIN_ADJACENCY.get(level_id, {}))
