from typing import NamedTuple, Generator, Optional, Sequence
from .node import ExNode, Content, ContentType
from .opcodes import Op, OP_MAP, op, create_push

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


def identifier(s: Content) -> Identifier:
    assert isinstance(s, str), f'Cannot create identifier from {s}'
    assert s not in OP_MAP, f'Valid opcode {s} cannot be identifier'
    return s


def function_to_sig(fn: ExNode) -> str:
    assert fn.name == 'function'
    args, _ = fn.get_all('tuple')
    return f'{get_ident(fn)}{tuple_to_compact_sig(args)}'


def error_to_sig(fn: ExNode) -> str:
    assert fn.name == 'error'
    args,  = fn.get_all('tuple')
    return f'{get_ident(fn)}{tuple_to_compact_sig(args)}'


def event_to_sig(fn: ExNode) -> str:
    name = get_ident(fn)
    args = fn.get_all_deep('event_arg')
    parsed_args = [
        parse_type_to_sig(a.get("type"))
        for a in args
    ]
    return f'{name}({",".join(parsed_args)})'


def parse_type_to_sig(t: ExNode, expand_tuple=True) -> str:
    if isinstance(t.content, str):
        return 'uint256' if t.content == 'uint' else t.content
    if t.name == 'tuple':
        if expand_tuple:
            return tuple_to_compact_sig(t, expand_tuple=expand_tuple)
        else:
            return 'tuple'
    assert len(t.content) == 2, f'{t} not len 2'
    prim, snd = t.content
    if snd.name == 'num':
        base_type = prim.text()
        if base_type == 'uint':
            assert snd.text() in [*map(str, range(8, 256+1, 8))], \
                f'Invalid uintN size {int(snd.text())}'
        elif base_type == 'bytes':
            assert snd.text() in [*map(str, range(1, 32+1))], \
                f'Invalid bytesN size {int(snd.text())}'
        else:
            raise ValueError(f'Unrecognized type with num {t.name}')
        return prim.text() + snd.text()
    else:
        children = snd.children()
        assert children[0].text() == '[' and children[-1].text() == ']' and len(children) in (2, 3), \
            'Dual node not bracket'
        if len(children) == 3:
            assert children[1].text() != '0', f'Array quantifier cannot be 0'
        return f'{parse_type_to_sig(prim, expand_tuple=expand_tuple)}{"".join(c.text() for c in children)}'


def tuple_to_compact_sig(node: ExNode, expand_tuple=True) -> str:
    types = node.get_all_deep('type')
    return f'({",".join(parse_type_to_sig(t, expand_tuple=expand_tuple) for t in types)})'


def get_ident(node: ExNode, default: Optional[Identifier] = None) -> Identifier:
    if default is None:
        return identifier(node.get('identifier').text())
    if (ident_node := node.maybe_get('identifier')) is None:
        return default
    return ident_node.text()


def literal_to_bytes(lit: str) -> bytes:
    return bytes.fromhex('0' * (len(lit) % 2) + lit)


def bytes_to_push(data: bytes) -> Op:
    if len(data) == 1 and data[0] == 0:
        return op('push0')
    return create_push(data)


def parse_hex_literal(el: ExNode) -> bytes:
    assert el.name == 'hex_literal'
    lit = el.get_idx(1).text()
    return literal_to_bytes(lit)


def parse_call_arg(arg: ExNode):
    el = parse_el(arg)
    assert isinstance(el, (GeneralRef, Op, MacroParam)), \
        f'Invalid call argument {el}'
    return el


def parse_el(el: ExNode) -> MacroElement:
    el = el.get_idx(0)
    name = el.name
    if name == 'hex_literal':
        return bytes_to_push(parse_hex_literal(el))
    elif name == 'macro_arg':
        return MacroParam(get_ident(el))
    elif name == 'invocation':
        return Invocation(
            get_ident(el),
            list(map(parse_call_arg, el.get_all_deep('call_arg')))
        )
    elif name == 'identifier':
        ident = el.text()
        if ident in OP_MAP:
            return op(ident)
        else:
            return GeneralRef(identifier(ident))
    elif name == 'dest_definition':
        return LabelDef(get_ident(el))
    elif name == 'const_ref':
        return ConstRef(get_ident(el))
    elif name == 'push_op':
        num = int(el.get('num').text())
        data = parse_hex_literal(el.get('hex_literal'))
        return create_push(data, num)

    raise ValueError(f'Unrecognized el name "{name}"')


def parse_macro(node: ExNode) -> Macro:
    assert node.name == 'macro', 'Not macro'

    macro_type = node.get('macro_type').text()
    assert macro_type == 'macro', f'Macro type {macro_type} not yet supported'
    ident = get_ident(node)

    if (param_list := node.get('params').maybe_get('param_list')) is not None:
        args = [
            identifier(ident_node.text())
            for ident_node in param_list.get_all_deep('identifier')
        ]
    else:
        args = []

    if (macro_body := node.maybe_get('macro_body')) is not None:
        els = [
            parse_el(raw_el)
            for raw_el in macro_body.get_all('macro_body_el')
        ]
    else:
        els = []

    # Validate macro argument references
    for el in els:
        if not isinstance(el, MacroParam):
            continue
        assert el.ident in args, f'Invalid macro arg {el.ident} for {ident} ({args})'

    return Macro(ident, args, els)


def get_defs(root: ExNode, name: None | str = None) -> Generator[ExNode, None, None]:
    for d in root.get_all('definition'):
        inner = d.get_idx(0)
        if name is None or inner.name == name:
            yield inner


def get_includes(root: ExNode) -> tuple[list[str], list[ExNode]]:
    includes: list[str] = []
    other_nodes: list[ExNode] = []
    for d in get_defs(root):
        if d.name == 'include':
            includes.append(d.get_idx(1).text())
        else:
            other_nodes.append(d)

    return includes, other_nodes


Json = list['Json'] | dict[str, 'Json'] | str | int | None | bool
Abi = list[Json]


def get_paren_nodes(paren_outer_nodes: list[ExNode]) -> list[ExNode]:
    if len(paren_outer_nodes) == 0:
        return []
    elif len(paren_outer_nodes) == 1:
        return paren_outer_nodes
    elif len(paren_outer_nodes) == 2:
        flattened_input_nodes: list[ExNode] = []
        last_first_nodes = paren_outer_nodes[0].children()[-1]
        if isinstance(last_first_nodes.content, str) and last_first_nodes.content == ',':
            flattened_input_nodes.append(paren_outer_nodes[0])
        else:
            flattened_input_nodes.extend(paren_outer_nodes[0].children())
        flattened_input_nodes.append(paren_outer_nodes[1])

        return flattened_input_nodes
    else:
        raise ValueError(
            f'Expect 0-2 outer paren nodes got {len(paren_outer_nodes)}'
        )


def parse_single_value_to_abi(node: ExNode) -> dict[str, Json]:
    if node.name == 'type':
        input_type_node = node
    else:
        input_type_node = node.get('type')
    input_type = parse_type_to_sig(input_type_node, expand_tuple=False)
    if input_type_node.ctype() == ContentType.SubNodes and\
            (tuple_node := input_type_node.maybe_get('tuple')) is not None:
        components = parse_tuple_to_values(tuple_node)
    else:
        components = []

    d: dict[str, Json] = {
        'name': get_ident(node, ''),
        'type': input_type
    }
    if components:
        d['components'] = components
    return d


def parse_tuple_to_values(tuple_node: ExNode) -> Json:
    inner_nodes = tuple_node.children()
    assert inner_nodes[0].text() == '(' and inner_nodes[-1].text() == ')', \
        'Expected to only exclude brackets'
    outer_input_nodes = inner_nodes[1:-1]
    input_nodes = get_paren_nodes(outer_input_nodes)

    return [
        parse_single_value_to_abi(child)
        for child in input_nodes
    ]


def func_to_abi(item: tuple[Identifier, ExNode]) -> Json:
    ident, func = item
    top_level_input_node, output_nodes = func.get_all('tuple')
    return {
        'type': 'function',
        'name': ident,
        'inputs': parse_tuple_to_values(top_level_input_node),
        'outputs': parse_tuple_to_values(output_nodes),
        'stateMutability': func.get('mutability').text()
    }


def funcs_to_abi(functions: dict[Identifier, ExNode]) -> Abi:
    return list(map(func_to_abi, functions.items()))


def parse_event_arg(event_arg: ExNode) -> Json:
    return {
        'indexed': any(c.content == 'indexed' for c in event_arg.children()),
        ** parse_single_value_to_abi(event_arg)
    }


def events_to_abi(events: dict[Identifier, ExNode]) -> Abi:
    return [
        {
            'type': 'event',
            'name': ident,
            'inputs': list(map(parse_event_arg, event.get_all_deep('event_arg'))),
            'anonymous': False
        }
        for ident, event in events.items()
    ]


def parse_to_abi(functions: dict[Identifier, ExNode], events: dict[Identifier, ExNode]) -> Abi:
    return funcs_to_abi(functions) + events_to_abi(events)


def parse_constant(node: ExNode) -> Optional[bytes]:
    assert node.name == 'const'
    value_node = node.get_idx(4)
    if value_node.name == 'hex_literal':
        return parse_hex_literal(value_node)
    assert value_node.text() == 'FREE_STORAGE_POINTER()', \
        f'Constant node {node} neither hex literal or FREE_STORAGE_POINTER()'
    return None
