"""
utils/sql.py — Small shared SQL helpers.
"""


def escape_like(term: str) -> str:
    """Escapa comodines de LIKE para que el usuario busque literales."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
