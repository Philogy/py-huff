from typing import NamedTuple, Callable
from Crypto.Hash import keccak
from .lexer import ExNode
from .assembler import *
from .parser import *
from .opcodes import OP_MAP, Op


def keccak256(preimage: bytes) -> bytes:
    return keccak.new(data=preimage, digest_bits=256).digest()


MacroArg = Op | MarkRef
GlobalScope = NamedTuple(
    'GlobalScope',
    [
        ('macros', dict[Identifier, Macro]),
        ('constants', dict[Identifier, Op]),
        ('code_tables', dict[Identifier, CodeTable]),
        ('functions', dict[Identifier, ExNode]),
        ('events', dict[Identifier, ExNode])
    ]
)


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
    mid = MarkId(tuple(), table.top_level_id, MarkPurpose.Start)

    return [MarkRef(mid)]


def table_size(name, g: GlobalScope, args: list[InvokeArg]) -> list[Asm]:
    assert len(args) == 1, f'{name} expects 1 argument, received {len(args)}'
    arg, = args
    assert isinstance(arg, GeneralRef), \
        f'{name} does not support argument {arg}'
    assert arg.ident in g.code_tables, f'Undefined table "{arg.ident}"'
    # TODO: Support more tables
    table = g.code_tables[arg.ident]
    start_mid = MarkId(tuple(), table.top_level_id, MarkPurpose.Start)
    end_mid = MarkId(tuple(), table.top_level_id, MarkPurpose.End)

    return [MarkDeltaRef(start_mid, end_mid)]


def function_sig(name, g: GlobalScope, args: list[InvokeArg]) -> list[Asm]:
    assert len(args) == 1, f'{name} expects 1 argument, received {len(args)}'
    arg, = args
    assert isinstance(arg, GeneralRef), \
        f'{name} does not support argument {arg}'
    assert arg.ident in g.functions, f'Undefined function "{arg.ident}"'
    sig = function_to_sig(g.functions[arg.ident])
    return [
        create_push(keccak256(sig.encode())[:4])
    ]


def event_hash(name, g: GlobalScope, args: list[InvokeArg]) -> list[Asm]:
    assert len(args) == 1, f'{name} expects 1 argument, received {len(args)}'
    arg, = args
    assert isinstance(arg, GeneralRef), \
        f'{name} does not support argument {arg}'
    assert arg.ident in g.events, f'Undefined event "{arg.ident}"'
    sig = event_to_sig(g.events[arg.ident])
    return [
        create_push(keccak256(sig.encode()))
    ]


BUILT_INS: dict[str, Callable[[str, GlobalScope, list[InvokeArg]], list[Asm]]] = {
    '__EVENT_HASH': event_hash,
    '__FUNC_SIG': function_sig,
    '__codesize': not_implemented,
    '__tablestart': table_start,
    '__tablesize': table_size
}


def invoke_built_in(fn_name: str, g: GlobalScope, args: list[InvokeArg]) -> list[Asm]:
    return BUILT_INS[fn_name](fn_name, g, args)


def expand_macro_to_asm(
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
        dest_id: MarkId = MarkId(ctx_id, i, MarkPurpose.Label)
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
                    expand_macro_to_asm(
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
