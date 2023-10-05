import os
from typing import Generator
from .lexer import lex_huff
from .node import ExNode
from .parser import get_includes


def resolve(fp: str, visited_paths: tuple[str, ...] = tuple()) -> Generator[ExNode, None, None]:
    fp = os.path.abspath(fp)
    assert fp not in visited_paths, f'Circular include in {fp}'
    visited_paths += (fp,)
    with open(fp, 'r') as f:
        file_root = lex_huff(f.read())

    includes, file_defs = get_includes(file_root)
    for include in includes:
        yield from resolve(os.path.join(os.path.dirname(fp), include))
    yield from file_defs
