from typing import NamedTuple
from collections import defaultdict
from .opcodes import Op
from .node import ExNode
from .parser import (
    Identifier, CodeTable, Macro, get_ident, parse_hex_literal,
    bytes_to_push, parse_macro
)
from .resolver import resolve
from .codegen import GlobalScope, expand_macro_to_asm, START_SUB_ID, END_SUB_ID
from .assembler import asm_to_bytecode, Mark, minimal_deploy

CompileResult = NamedTuple(
    'CompileResult',
    [
        ('runtime', bytes),
        ('deploy', bytes)
    ]
)


def compile(entry_fp: str) -> CompileResult:
    defs: dict[str, list[ExNode]] = defaultdict(list)
    for d in resolve(entry_fp):
        defs[d.name].append(d)

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

    asm = expand_macro_to_asm(
        'MAIN',
        GlobalScope(macros, constants, code_tables, functions),
        [],
        {},
        (0,),
        tuple()
    )

    for table in code_tables.values():
        asm.extend([
            Mark(((table.top_level_id,), START_SUB_ID)),
            table.data,
            Mark(((table.top_level_id,), END_SUB_ID)),
        ])

    runtime = asm_to_bytecode(asm)
    deploy = minimal_deploy(runtime)

    return CompileResult(
        runtime=runtime,
        deploy=deploy
    )
