from typing import NamedTuple
from .opcodes import Op
from .lexer import lex_huff
from .node import ExNode
from .parser import (
    Identifier, CodeTable, Macro, get_ident, parse_hex_literal,
    get_defs, bytes_to_push, parse_macro
)
from .codegen import GlobalScope, expand_macro_to_asm, START_SUB_ID, END_SUB_ID
from .assembler import asm_to_bytecode, Mark, minimal_deploy

CompileResult = NamedTuple(
    'CompileResult',
    [
        ('runtime', bytes),
        ('deploy', bytes)
    ]
)


def compile(fp: str) -> CompileResult:
    with open(fp, 'r') as f:
        root = lex_huff(f.read())

    # TODO: Recursively resolve and flatten includes

    # TODO: Make sure constants, macros and code tables are unique
    constants: dict[Identifier, Op] = {
        get_ident(const): bytes_to_push(parse_hex_literal(const.get('hex_literal')))
        for const in get_defs(root, 'const')
    }
    macros: dict[Identifier, Macro] = {
        (macro := parse_macro(node)).ident: macro
        for node in get_defs(root, 'macro')
    }

    assert 'CONSTRUCTOR' not in macros, 'Custom constructors not yet supported'

    # TODO: Warn when literal has odd digits
    code_tables: dict[Identifier, CodeTable] = {
        get_ident(node): CodeTable(parse_hex_literal(node.get('hex_literal')), i)
        for i, node in enumerate(get_defs(root, 'code_table'), start=1)
    }

    functions: dict[Identifier, ExNode] = {
        get_ident(fn): fn
        for fn in get_defs(root, 'function')
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
