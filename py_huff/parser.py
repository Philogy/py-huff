from typing import NamedTuple, Generator
from .opcodes import Op, OP_MAP, create_plain_op, create_push
from .lexer import ExNode, Children

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


def identifier(s: Children) -> Identifier:
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
        return create_plain_op('push0')
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
            return create_plain_op(ident)
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
