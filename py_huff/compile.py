from typing import NamedTuple, Iterable
import json
from collections import defaultdict
from .assembler import asm_to_bytecode, to_start_mark, to_end_mark
from .context import ContextTracker
from .utils import build_unique_dict
from .opcodes import Op, op
from .node import ExNode
from .lexer import lex_huff
from .parser import (
    Identifier, Macro, get_ident, parse_hex_literal, parse_macro, get_includes,
    parse_constant, parse_to_abi, Abi
)
from .resolver import resolve
from .codegen import (
    GlobalScope, Scope, expand_macro_to_asm, CodeTable, ConstructorData,
    gen_minimal_init, gen_constants
)

CompileResult = NamedTuple(
    'CompileResult',
    [
        ('runtime', bytes),
        ('deploy', bytes),
        ('abi', Abi)
    ]
)


def idefs_to_defs(idefs: Iterable[ExNode]) -> dict[str, list[ExNode]]:
    defs: dict[str, list[ExNode]] = defaultdict(list)
    for d in idefs:
        defs[d.name].append(d)
    return defs


def compile(entry_fp: str, constant_overrides: dict[Identifier, bytes]) -> CompileResult:
    return compile_from_defs(idefs_to_defs(resolve(entry_fp)), constant_overrides)


def compile_src(src: str, constant_overrides: dict[Identifier, bytes]) -> CompileResult:
    root = lex_huff(src)
    includes, idefs = get_includes(root)
    assert not includes, f'Cannot compile directly from source if it contains includes'
    return compile_from_defs(idefs_to_defs(idefs), constant_overrides)


def compile_from_defs(
        defs: dict[str, list[ExNode]],
        constant_overrides: dict[Identifier, bytes]
) -> CompileResult:

    # TODO: Make sure constants, macros and code tables are unique
    constants: dict[Identifier, Op] = gen_constants(
        (
            (get_ident(const), parse_constant(const))
            for const in defs['const']
        ),
        constant_overrides
    )

    macros: dict[Identifier, Macro] = build_unique_dict(
        (
            ((macro := parse_macro(node)).ident, macro)
            for node in defs['macro']
        ),
        on_dup='macro'
    )

    context = ContextTracker(tuple())

    # TODO: Warn when literal has odd digits
    code_tables: dict[Identifier, CodeTable] = build_unique_dict(
        (
            (
                get_ident(node),
                CodeTable(
                    parse_hex_literal(node.get('hex_literal')),
                    context.next_obj_id()
                )
            )
            for node in defs['code_table']
        ),
        on_dup='code table'
    )

    for ctable in code_tables:
        assert ctable not in macros, f'Already defined macro with name "{ctable}"'

    functions: dict[Identifier, ExNode] = build_unique_dict(
        (
            (get_ident(fn), fn)
            for fn in defs['function']
        ),
        on_dup='function'
    )

    events: dict[Identifier, ExNode] = build_unique_dict(
        (
            (get_ident(e), e)
            for e in defs['event']
        ),
        on_dup='event'
    )

    abi: Abi = parse_to_abi(functions, events)

    assert 'MAIN' in macros, 'Program must contain MAIN macro entry point'

    globals = GlobalScope(
        macros,
        constants,
        code_tables,
        functions,
        events
    )
    main_scope = Scope(globals, None)
    runtime_asm = expand_macro_to_asm(
        'MAIN',
        main_scope,
        [],
        {},
        context.next_sub_context(),
        tuple()
    )

    for table in main_scope.referenced_tables:
        code_table = globals.code_tables[table]
        runtime_asm.extend([
            to_start_mark(code_table.obj_id),
            code_table.data,
            to_end_mark(code_table.obj_id)
        ])

    runtime = asm_to_bytecode(runtime_asm)

    runtime_obj_id = context.next_obj_id()
    if 'CONSTRUCTOR' in macros:
        init_scope = Scope(globals, ConstructorData(runtime_obj_id))
        init_asm = expand_macro_to_asm(
            'CONSTRUCTOR',
            init_scope,
            [],
            {},
            context.next_sub_context(),
            tuple()
        )
        for table in main_scope.referenced_tables:
            code_table = globals.code_tables[table]
            init_asm.extend([
                to_start_mark(code_table.obj_id),
                code_table.data,
                to_end_mark(code_table.obj_id)
            ])
        init_asm.extend([
            to_start_mark(runtime_obj_id),
            runtime,
            to_end_mark(runtime_obj_id)
        ])
        deploy = asm_to_bytecode(init_asm)
    else:
        init_asm = [
            *gen_minimal_init(runtime_obj_id, op('push0')),
            to_start_mark(runtime_obj_id),
            runtime,
            to_end_mark(runtime_obj_id)
        ]
        deploy = asm_to_bytecode(init_asm)

    return CompileResult(
        runtime=runtime,
        deploy=deploy,
        abi=abi
    )
