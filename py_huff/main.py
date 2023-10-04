from opcodes import OP_MAP, Op, create_push
from Crypto.Hash import keccak
import sys
from typing import NamedTuple, Any, Generator, Callable
from parser import parse_huff, ExNode, disp_node


def keccak256(d: bytes) -> bytes:
    return keccak.new(d, digest_bits=256).digest()


Identifier = str
MacroParam = NamedTuple('MacroParam', [('ident', Identifier)])
GeneralRef = NamedTuple('GeneralRef', [('ident', Identifier)])
ConstRef = NamedTuple('ConstRef', [('ident', Identifier)])
LabelDef = NamedTuple('LabelDef', [('ident', Identifier)])
InvokeArg = Op | GeneralRef | MacroParam
Invocation = NamedTuple(
    'Invocation',
    [('ident', Identifier), ('args', list[InvokeArg])]
)

MacroElement = Invocation | Op | MacroParam | GeneralRef | LabelDef | ConstRef

Macro = NamedTuple('Macro', [
    ('ident', Identifier),
    ('params', list[Identifier]),
    ('body', list[MacroElement])
])

CodeTable = NamedTuple(
    'CodeTable',
    [
        ('data', bytes),
        ('top_level_id', int)
    ]
)


def child_get_all(name: str, node: ExNode) -> Generator[ExNode, None, None]:
    children = node.children
    if not isinstance(children, list):
        raise TypeError(f'Cannot get child on {node}')
    return (
        child
        for child in node.children
        if isinstance(child, ExNode) and child.name == name
    )


def child_maybe_get(name: str, node: ExNode) -> ExNode | None:
    gotten = list(child_get_all(name, node))
    assert len(gotten) <= 1, \
        f'{len(gotten)} instances of "{name}" found in {node}, expectd 1'
    if gotten:
        return gotten[0]
    else:
        return None


def child_get(name: str, node: ExNode) -> ExNode:
    gotten = child_maybe_get(name, node)
    assert gotten is not None, f'"{name}" not found in {node}'
    return gotten


def identifier(s: Any) -> Identifier:
    assert isinstance(s, str), f'Cannot create identifier from {s}'
    assert s not in OP_MAP, f'Valid opcode {s} cannot be identifier'
    return s


def get_ident(node: ExNode) -> Identifier:
    return identifier(child_get('identifier', node).children)


def get_deep(name, node: ExNode) -> Generator[ExNode, None, None]:
    if isinstance(node.children, list):
        for child in node.children:
            if child.name == name:
                yield child
            else:
                yield from get_deep(name, child)


def get_idx(node: ExNode, i: int) -> ExNode:
    assert isinstance(node.children, list)
    return node.children[i]


def literal_to_bytes(lit: str) -> bytes:
    return bytes.fromhex('0' * (len(lit) % 2) + lit)


def bytes_to_push(data: bytes) -> Op:
    if len(data) == 1 and data[0] == 0:
        return Op(OP_MAP['push0'], b'')
    return create_push(data)


def parse_hex_literal(el: ExNode) -> bytes:
    assert el.name == 'hex_literal'
    lit = get_idx(el, 1).children
    assert isinstance(lit, str)
    return literal_to_bytes(lit)


def parse_call_arg(arg: ExNode):
    el = parse_el(arg)
    assert isinstance(el, (GeneralRef, Op, MacroParam)), \
        f'Invalid call argument {el}'
    return el


def parse_el(el: ExNode) -> MacroElement:
    el = get_idx(el, 0)
    name = el.name
    if name == 'hex_literal':
        return bytes_to_push(parse_hex_literal(el))
    elif name == 'macro_arg':
        return MacroParam(get_ident(el))
    elif name == 'invocation':
        return Invocation(
            get_ident(el),
            list(map(parse_call_arg, get_deep('call_arg', el)))
        )
    elif name == 'identifier':
        ident = el.children
        assert isinstance(ident, str)
        if ident in OP_MAP:
            assert not ident.startswith('push') or ident == 'push0', \
                f'Standalone {ident} not supported'
            return Op(OP_MAP[ident], b'')
        else:
            return GeneralRef(identifier(ident))
    elif name == 'dest_definition':
        return LabelDef(get_ident(el))
    elif name == 'const_ref':
        return ConstRef(get_ident(el))
    elif name == 'push_op':
        num_node = child_get('num', el)
        assert isinstance(num_node.children, str)
        num = int(num_node.children)
        data = parse_hex_literal(child_get('hex_literal', el))
        return create_push(data, num)

    raise ValueError(f'Unrecognized el name "{name}"')


def parse_macro_el(el: ExNode) -> MacroElement:
    assert el.name == 'macro_body_el'
    assert len(el.children) == 1 and isinstance(el.children, list)
    return parse_el(el)


def parse_macro(node: ExNode) -> Macro:
    assert node.name == 'macro', 'Not macro'

    macro_type = child_get('macro_type', node).children
    assert macro_type == 'macro', f'Macro type {macro_type} not yet supported'
    ident = get_ident(node)

    if (param_list := child_maybe_get('param_list', child_get('params', node))) is not None:
        args = [
            identifier(ident_node.children)
            for ident_node in get_deep('identifier', param_list)
        ]
    else:
        args = []

    if (macro_body := child_maybe_get('macro_body', node)) is not None:
        els = [
            parse_macro_el(raw_el)
            for raw_el in child_get_all('macro_body_el', macro_body)
        ]
    else:
        els = []

    # Validate macro argument references
    for el in els:
        if not isinstance(el, MacroParam):
            continue
        assert el.ident in args, f'Invalid macro arg {el.ident} for {ident} ({args})'

    return Macro(ident, args, els)


def get_defs(name: str, root: ExNode) -> Generator[ExNode, None, None]:
    return (
        inner
        for d in child_get_all('definition', root)
        if (inner := get_idx(d, 0)).name == name
    )


ContextId = tuple[int, ...]
MarkId = tuple[ContextId, int]
Mark = NamedTuple('Mark', [('mid', MarkId)])
MarkRef = NamedTuple('MarkRef', [('ref', MarkId)])
MarkDeltaRef = NamedTuple('MarkDeltaRef', [('start', MarkId), ('end', MarkId)])
Asm = Op | Mark | MarkRef | MarkDeltaRef | bytes
MacroArg = Op | MarkRef
GlobalScope = NamedTuple(
    'GlobalScope',
    [
        ('macros', dict[Identifier, Macro]),
        ('constants', dict[Identifier, Op]),
        ('code_tables', dict[Identifier, CodeTable]),
        ('functions', dict[Identifier, ExNode])
    ]
)

START_SUB_ID = 0
END_SUB_ID = 1


def not_implemented(fn_name, *_) -> list[Asm]:
    return []
    raise ValueError(f'Built-in {fn_name} not implemented yet')


def table_start(name, g: GlobalScope, args: list[InvokeArg]) -> list[Asm]:
    assert len(args) == 1, f'{name} expects 1 argument, received {len(args)}'
    arg, = args
    assert isinstance(arg, GeneralRef), \
        f'{name} does not support argument {arg}'
    assert arg.ident in g.code_tables, f'Undefined table "{arg.ident}"'
    # TODO: Support more tables
    table = g.code_tables[arg.ident]
    mid: MarkId = (table.top_level_id,), START_SUB_ID

    return [MarkRef(mid)]


def table_size(name, g: GlobalScope, args: list[InvokeArg]) -> list[Asm]:
    assert len(args) == 1, f'{name} expects 1 argument, received {len(args)}'
    arg, = args
    assert isinstance(arg, GeneralRef), \
        f'{name} does not support argument {arg}'
    assert arg.ident in g.code_tables, f'Undefined table "{arg.ident}"'
    # TODO: Support more tables
    table = g.code_tables[arg.ident]
    start_mid: MarkId = (table.top_level_id,), START_SUB_ID
    end_mid: MarkId = (table.top_level_id,), END_SUB_ID

    return [MarkDeltaRef(start_mid, end_mid)]


def function_sig(name, g: GlobalScope, args: list[InvokeArg]) -> list[Asm]:
    assert len(args) == 1, f'{name} expects 1 argument, received {len(args)}'
    arg, = args
    assert isinstance(arg, GeneralRef), \
        f'{name} does not support argument {arg}'
    assert arg.ident in g.functions, f'Undefined function "{arg.ident}"'


BUILT_INS: dict[str, Callable[[str, GlobalScope, list[InvokeArg]], list[Asm]]] = {
    '__EVENT_HASH': not_implemented,
    '__FUNC_SIG': not_implemented,
    '__codesize': not_implemented,
    '__tablestart': table_start,
    '__tablesize': table_size
}


def invoke_built_in(fn_name: str, g: GlobalScope, args: list[InvokeArg]) -> list[Asm]:
    return BUILT_INS[fn_name](fn_name, g, args)


def gen_asm(
    macro_ident: Identifier,
    g: GlobalScope,
    args: list[MacroArg],
    labels: dict[Identifier, MarkId],
    ctx_id: ContextId,
    visited_macros: tuple[Identifier, ...]
) -> list[Asm]:
    assert macro_ident not in visited_macros, f'Circular macro refrence in {macro_ident}'
    assert macro_ident in g.macros, f'Unrecognized macro "{macro_ident}"'
    macro = g.macros[macro_ident]
    assert len(args) == len(macro.params), \
        f'macro "{macro_ident}" received {len(args)} args, expected {len(macro.params)}'
    visited_macros += (macro_ident,)

    ident_to_arg = {
        ident: arg
        for ident, arg in zip(macro.params, args)
    }
    if args is None:
        args = []

    asm: list[Asm] = []

    for i, label_def in enumerate(el for el in macro.body if isinstance(el, LabelDef)):
        label = label_def.ident
        dest_id: MarkId = ctx_id, i
        # TODO: Add warning when invoked macro has label shadowing parent
        assert label not in labels or labels[label] != dest_id, \
            f'Duplicate label "{label}" in macro "{macro.ident}"'
        labels[label] = dest_id

    def lookup_label(ident: Identifier) -> MarkRef:
        assert ident in labels, f'Label "{ident}" not found in scope ({ctx_id})'
        return MarkRef(labels[ident])

    def lookup_arg(ident: Identifier) -> MacroArg:
        assert ident in ident_to_arg, f'Invalid macro argument "{ident}"'
        return ident_to_arg[ident]

    idx = 0
    for el in macro.body:
        if isinstance(el, Op):
            asm.append(el)
        elif isinstance(el, LabelDef):
            asm.extend([Mark(labels[el.ident]), Op(OP_MAP['jumpdest'], b'')])
        elif isinstance(el, GeneralRef):
            asm.append(lookup_label(el.ident))
        elif isinstance(el, MacroParam):
            asm.append(lookup_arg(el.ident))
        elif isinstance(el, ConstRef):
            assert el.ident in g.constants, f'Constant "{el.ident}" not found'
            asm.append(g.constants[el.ident])
        elif isinstance(el, Invocation):
            if el.ident in BUILT_INS:
                asm.extend(
                    invoke_built_in(el.ident, g, el.args)
                )
            else:
                invoke_args: list[MacroArg] = []
                for arg in el.args:
                    if isinstance(arg, GeneralRef):
                        invoke_args.append(lookup_label(arg.ident))
                    elif isinstance(arg, MacroParam):
                        invoke_args.append(lookup_arg(arg.ident))
                    elif isinstance(arg, Op):
                        invoke_args.append(arg)
                    else:
                        raise TypeError(
                            f'Unrecognized macro invocation argument {arg}')

                asm.extend(
                    gen_asm(
                        el.ident,
                        g,
                        invoke_args,
                        labels.copy(),
                        ctx_id + (idx, ),
                        visited_macros
                    )
                )
                idx += 1
        else:
            raise TypeError(f'Unrecognized macro element {el}')

    return asm


def get_min_dest_bytes(asm: list[Asm]) -> int:
    '''Compute the minimum size in bytes that'd work for any jump destination'''
    ref_count = sum(isinstance(step, (MarkRef, MarkDeltaRef)) for step in asm)
    pure_len = sum(
        1 + len(step.extra_data)
        for step in asm
        if isinstance(step, Op)
    )
    dest_bytes = 1
    while ((1 << (8 * dest_bytes)) - 1) < pure_len + (1 + dest_bytes) * ref_count:
        dest_bytes += 1
    return dest_bytes


def asm_to_bytecode(asm: list[Asm]) -> bytes:
    dest_bytes = get_min_dest_bytes(asm)
    assert dest_bytes <= 6
    marks: dict[MarkId, int] = {}
    final_bytes: list[int] = []
    refs: list[tuple[int, MarkId]] = []
    delta_refs: list[tuple[int, MarkId, MarkId]] = []
    for step in asm:
        if isinstance(step, Op):
            final_bytes.extend(step.get_bytes())
        elif isinstance(step, Mark):
            assert step.mid not in marks, f'Duplicate destination {step.mid}'
            marks[step.mid] = len(final_bytes)
        elif isinstance(step, MarkRef):
            refs.append((len(final_bytes) + 1, step.ref))
            final_bytes.extend(create_push(b'', dest_bytes).get_bytes())
        elif isinstance(step, MarkDeltaRef):
            delta_refs.append((len(final_bytes) + 1, step.start, step.end))
            final_bytes.extend(create_push(b'', dest_bytes).get_bytes())
        elif isinstance(step, bytes):
            final_bytes.extend(step)
        else:
            raise ValueError(f'Unrecognized assembly step {step}')

    for offset, dest_id in refs:
        for i, b in enumerate(marks[dest_id].to_bytes(dest_bytes, 'big'), start=offset):
            final_bytes[i] = b

    for offset, start_id, end_id in delta_refs:
        start_offset = marks[start_id]
        end_offset = marks[end_id]
        assert end_offset >= start_offset, 'Inverted offsets'
        size = end_offset - start_offset
        for i, b in enumerate(size.to_bytes(dest_bytes, 'big'), start=offset):
            final_bytes[i] = b

    return bytes(final_bytes)


def main() -> None:
    with open(sys.argv[1], 'r') as f:
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

    asm = gen_asm(
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

    code = asm_to_bytecode(asm)

    print(code.hex())


if __name__ == '__main__':
    main()
