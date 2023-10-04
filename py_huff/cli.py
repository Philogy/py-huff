from .opcodes import Op
from argparse import ArgumentParser
from .lexer import parse_huff, ExNode
from .parser import (
    Identifier, CodeTable, Macro, get_ident, parse_hex_literal, child_get,
    get_defs, bytes_to_push, parse_macro
)
from .codegen import GlobalScope, expand_macro_to_asm, START_SUB_ID, END_SUB_ID
from .assembler import asm_to_bytecode, Mark, minimal_deploy


def parse_args():
    parser = ArgumentParser(
        description='A CLI for compiling Huff source code files to bytecode'
    )
    parser.add_argument('path', type=str)
    parser.add_argument('--runtime', '-r', action='store_true')
    parser.add_argument('--deploy', '-b', action='store_true')
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    with open(args.path, 'r') as f:
        root = parse_huff(f.read())

    # TODO: Make sure constants, macros and code tables are unique
    constants: dict[Identifier, Op] = {
        get_ident(const): bytes_to_push(parse_hex_literal(child_get('hex_literal', const)))
        for const in get_defs('const', root)
    }
    macros: dict[Identifier, Macro] = {
        (macro := parse_macro(node)).ident: macro
        for node in get_defs('macro', root)
    }

    # TODO: Warn when literal has odd digits
    code_tables: dict[Identifier, CodeTable] = {
        get_ident(node): CodeTable(parse_hex_literal(child_get('hex_literal', node)), i)
        for i, node in enumerate(get_defs('code_table', root), start=1)
    }

    functions: dict[Identifier, ExNode] = {
        get_ident(fn): fn
        for fn in get_defs('function', root)
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

    runtime_code = asm_to_bytecode(asm)
    deploy_code = minimal_deploy(runtime_code)

    assert 'CONSTRUCTOR' not in macros, 'Custom constructors not yet supported'

    if args.runtime and args.deploy:
        print(f'bytecode: {deploy_code.hex()}')
        print(f'\nruntime: {runtime_code.hex()}')
    elif args.runtime:
        print(runtime_code.hex())
    elif args.deploy:
        print(deploy_code.hex())
    else:
        print('WARNING: Neither runtime or deploy bytecode output')


if __name__ == '__main__':
    main()
