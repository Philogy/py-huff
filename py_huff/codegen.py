from typing import NamedTuple, Callable
from enum import Enum
from .lexer import ExNode
from .assembler import *
from .parser import *
from .opcodes import OP_MAP, Op
from .utils import keccak256


RUNTIME_ENTRY_MACRO = 'MAIN'
DEPLOY_ENTRY_MACRO = 'CONSTRUCTOR'


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

Preparation = NamedTuple(
    'Preparation',
    [
        ('contents', list[Asm]),
        ('dep_refs', tuple[tuple[MarkId, Identifier], ...]),
        ('deps', dict[Identifier, list[Asm]])
    ]
)


def not_implemented(fn_name, *_) -> list[Asm]:
    raise ValueError(f'Built-in {fn_name} not implemented yet')


def table_start(name, g: GlobalScope, args: list[InvokeArg], _) -> list[Asm]:
    assert len(args) == 1, f'{name} expects 1 argument, received {len(args)}'
    arg, = args
    assert isinstance(arg, GeneralRef), \
        f'{name} does not support argument {arg}'
    assert arg.ident in g.code_tables, f'Undefined table "{arg.ident}"'
    # TODO: Support more tables
    table = g.code_tables[arg.ident]
    mid = (table.top_level_id,), START_SUB_ID

    return [MarkRef(mid)]


def table_size(name, g: GlobalScope, args: list[InvokeArg], _) -> list[Asm]:
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


def function_sig(name, g: GlobalScope, args: list[InvokeArg], _) -> list[Asm]:
    assert len(args) == 1, f'{name} expects 1 argument, received {len(args)}'
    arg, = args
    assert isinstance(arg, GeneralRef), \
        f'{name} does not support argument {arg}'
    assert arg.ident in g.functions, f'Undefined function "{arg.ident}"'
    sig = function_to_sig(g.functions[arg.ident])
    return [
        create_push(keccak256(sig.encode())[:4])
    ]


def event_hash(name, g: GlobalScope, args: list[InvokeArg], _) -> list[Asm]:
    assert len(args) == 1, f'{name} expects 1 argument, received {len(args)}'
    arg, = args
    assert isinstance(arg, GeneralRef), \
        f'{name} does not support argument {arg}'
    assert arg.ident in g.events, f'Undefined event "{arg.ident}"'
    sig = event_to_sig(g.events[arg.ident])
    return [
        create_push(keccak256(sig.encode()))
    ]


def runtime_size(name: str, _: GlobalScope, args: list[InvokeArg], entry_macro: Identifier) -> list[Asm]:
    assert len(args) == 0, f'{name} takes no arguments'
    assert entry_macro == DEPLOY_ENTRY_MACRO, f'{name} only useable from within {DEPLOY_ENTRY_MACRO}'
    return [
        MarkDeltaRef()
    ]


BUILT_INS: dict[str, Callable[[str, GlobalScope, list[InvokeArg], Identifier], list[Asm]]] = {
    '__EVENT_HASH': event_hash,
    '__FUNC_SIG': function_sig,
    '__tablestart': table_start,
    '__tablesize': table_size,
    '__codesize': None,
    '__codestart': None
}


def invoke_built_in(fn_name: str, g: GlobalScope, args: list[InvokeArg], entry_macro: Identifier) -> list[Asm]:
    return BUILT_INS[fn_name](fn_name, g, args, entry_macro)


'''
What a prepared macro needs to return
1. The runtime assembly of the macro
2. ID => object name map of dependencies
3. object name => object map

'''

Trace = tuple[Identifier, ...]


def add_step(trace: Trace, step: Identifier) -> Trace:
    assert step not in trace, f'Recursive references not supported'
    return trace + (step,)


def only_label_defs(macro_els: list[MacroElement]) -> Generator[LabelDef, None, None]:
    for el in macro_els:
        if isinstance(el, LabelDef):
            yield el


def prepare_macro(
    g: GlobalScope,
    macro_ident: Identifier,
    args: list[MacroArg],
    labels: dict[Identifier, MarkId],
    ctx_id: ContextId,
    trace: Trace
) -> Preparation:
    assert macro_ident not in trace, f'Circular macro refrence in {macro_ident}'
    assert macro_ident in g.macros, f'Unrecognized macro "{macro_ident}"'
    macro = g.macros[macro_ident]
    assert len(args) == len(macro.params), \
        f'macro "{macro_ident}" received {len(args)} args, expected {len(macro.params)}'
    trace = add_step(trace, macro_ident)
    ident_to_arg = {
        ident: arg
        for ident, arg in zip(macro.params, args)
    }

    body_asm: list[Asm] = []

    for i, label_def in enumerate(only_label_defs(macro.body)):
        label = label_def.ident
        if label in labels:
            assert len(labels[label].ctx_id) < len(ctx_id),\
                f'Unexpected label origin {labels[label]}'
            assert labels[label].ctx_id != ctx_id, f'Duplicate label {label} in macro {macro_ident}'
        labels[label] = MarkId(ctx_id, i, None)

    def lookup_label(ident: Identifier) -> MarkRef:
        assert ident in labels, f'Label "{ident}" not found in scope ({ctx_id})'
        return MarkRef(labels[ident])

    def lookup_arg(ident: Identifier) -> MacroArg:
        assert ident in ident_to_arg, f'Invalid macro argument "{ident}"'
        return ident_to_arg[ident]

    idx = 0
    for el in macro.body:
        if isinstance(el, Op):
            body_asm.append(el)
        elif isinstance(el, LabelDef):
            body_asm.extend([
                Mark(labels[el.ident]),
                Op(OP_MAP['jumpdest'], b'')
            ])
        elif isinstance(el, GeneralRef):
            body_asm.append(lookup_label(el.ident))
        elif isinstance(el, MacroParam):
            body_asm.append(lookup_arg(el.ident))
        elif isinstance(el, ConstRef):
            assert el.ident in g.constants, f'Constant "{el.ident}" not found'
            body_asm.append(g.constants[el.ident])
        elif isinstance(el, Invocation):
            if el.ident in BUILT_INS:
                asm.extend(
                    invoke_built_in(el.ident, g, el.args, visited_macros[0])
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
                            f'Unrecognized macro invocation argument {arg}'
                        )

                assert el.ident not in (RUNTIME_ENTRY_MACRO, DEPLOY_ENTRY_MACRO), \
                    f'Macro {el.ident} only invocable at top-level'

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
