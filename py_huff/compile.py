from typing import NamedTuple, Iterable
from collections import defaultdict
from .opcodes import Op
from .node import ExNode
from .lexer import lex_huff
from .parser import (
    Identifier, CodeTable, Macro, get_ident, parse_hex_literal,
    bytes_to_push, parse_macro, get_includes
)
from .resolver import resolve
from .codegen import GlobalScope, expand_macro_to_asm
from .assembler import asm_to_bytecode, Mark, minimal_deploy, MarkPurpose, MarkId

CompileResult = NamedTuple(
    'CompileResult',
    [
        ('runtime', bytes),
        ('deploy', bytes)
    ]
)

TOP_LEVEL_ENTRY_CONTEXT = (0,)


def idefs_to_defs(idefs: Iterable[ExNode]) -> dict[str, list[ExNode]]:
    defs: dict[str, list[ExNode]] = defaultdict(list)
    for d in idefs:
        defs[d.name].append(d)
    return defs


def compile(entry_fp: str) -> CompileResult:
    return compile_from_defs(idefs_to_defs(resolve(entry_fp)))


def compile_src(src: str) -> CompileResult:
    root = lex_huff(src)
    includes, idefs = get_includes(root)
    assert not includes, f'Cannot compile directly from source if it contains includes'
    return compile_from_defs(idefs_to_defs(idefs))


def compile_from_defs(defs: dict[str, list[ExNode]]) -> CompileResult:

    # TODO: Make sure constants, macros and code tables are unique
    constants: dict[Identifier, Op] = {
        get_ident(const): bytes_to_push(parse_hex_literal(const.get('hex_literal')))
        for const in defs['const']
    }
    macros: dict[Identifier, Macro] = {
        (macro := parse_macro(node)).ident: macro
        for node in defs['macro']
    }

    assert 'CONSTRUCTOR' not in macros, 'Custom constructors not yet supported'

    # TODO: Warn when literal has odd digits
    code_tables: dict[Identifier, CodeTable] = {
        get_ident(node): CodeTable(parse_hex_literal(node.get('hex_literal')), i)
        for i, node in enumerate(defs['code_table'], start=1)
    }

    functions: dict[Identifier, ExNode] = {
        get_ident(fn): fn
        for fn in defs['function']
    }

    events: dict[Identifier, ExNode] = {
        get_ident(e): e
        for e in defs['event']
    }

    assert 'MAIN' in macros, 'Program must contain MAIN macro entry point'

    asm = expand_macro_to_asm(
        'MAIN',
        GlobalScope(macros, constants, code_tables, functions, events),
        [],
        {},
        TOP_LEVEL_ENTRY_CONTEXT,
        tuple()
    )

    for table in code_tables.values():
        asm.extend([
            Mark(MarkId(tuple(), table.top_level_id, MarkPurpose.Start)),
            table.data,
            Mark(MarkId(tuple(), table.top_level_id, MarkPurpose.End)),
        ])

    runtime = asm_to_bytecode(asm)
    deploy = minimal_deploy(runtime)

    return CompileResult(
        runtime=runtime,
        deploy=deploy
    )
