import os
from typing import Generator
from .lexer import lex_huff
from .node import ExNode
from .parser import get_includes


def resolve(fp: str, visited_paths: tuple[str, ...] = tuple(), already_resolved: set[str] | None = None) -> Generator[ExNode, None, None]:
    if already_resolved is None:
        already_resolved = set()
    fp = os.path.abspath(fp)
    if fp in already_resolved:
        return
    already_resolved.add(fp)
    assert fp not in visited_paths, f'Circular include in {fp}'
    visited_paths += (fp,)
    with open(fp, 'r') as f:
        file_root = lex_huff(f.read())

    includes, file_defs = get_includes(file_root)
    for include in includes:
        yield from resolve(os.path.join(os.path.dirname(fp), include), visited_paths, already_resolved)
    yield from file_defs
