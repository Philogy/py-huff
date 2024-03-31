from typing import NamedTuple, Callable, Optional, Any, Iterable
import inspect
from .lexer import ExNode
from .assembler import *
from .parser import *
from .opcodes import OP_MAP, Op, op
from .context import ContextTracker
from .utils import s, keccak256, set_unique, byte_size


MacroArg = Op | MarkRef

ConstructorData = NamedTuple(
    'ConstructorData',
    [
        ('runtime', ObjectId)
    ]
)

CodeTable = NamedTuple(
    'CodeTable',
    [
        ('data', bytes),
        ('obj_id', ObjectId)
    ]
)


GlobalScope = NamedTuple(
    'GlobalScope',
    [
        ('macros', dict[Identifier, Macro]),
        ('constants', dict[Identifier, Op]),
        ('code_tables', dict[Identifier, CodeTable]),
        ('functions', dict[Identifier, ExNode]),
        ('events', dict[Identifier, ExNode]),
        ('errors', dict[Identifier, ExNode])
    ]
)

CompileOptions = NamedTuple(
    'CompileOptions',
    [
        ('avoid_push0', bool)
    ]
)

InvokeValue = MacroArg | GeneralRef | MacroParam


class Scope:
    g: GlobalScope
    referenced_tables: set[Identifier]
    for_constructor: Optional[ConstructorData]

    def __init__(self, g: GlobalScope, for_constructor: Optional[ConstructorData]) -> None:
        self.__g = g
        self.referenced_tables = set()
        self.for_constructor = for_constructor

    def reference_table(self, ident: Identifier) -> CodeTable:
        code_table = self.get_code_table(ident)
        self.referenced_tables.add(ident)
        return code_table

    def get_macro(self, ident: Identifier) -> Macro:
        assert ident in self.__g.macros, f'Undefined macro "{ident}"'
        return self.__g.macros[ident]

    def get_constant(self, ident: Identifier) -> Op:
        assert ident in self.__g.constants, f'Undefined constant "{ident}"'
        return self.__g.constants[ident]

    def get_code_table(self, ident: Identifier) -> CodeTable:
        assert ident in self.__g.code_tables, f'Undefined code table "{ident}"'
        return self.__g.code_tables[ident]

    def get_function(self, ident: Identifier) -> ExNode:
        assert ident in self.__g.functions, f'Undefined function "{ident}"'
        return self.__g.functions[ident]

    def get_event(self, ident: Identifier) -> ExNode:
        assert ident in self.__g.events, f'Undefined event "{ident}"'
        return self.__g.events[ident]

    def get_error(self, ident: Identifier) -> ExNode:
        assert ident in self.__g.errors, f'Undefined function "{ident}"'
        return self.__g.errors[ident]


def not_implemented(fn_name, *_) -> list[Asm]:
    raise ValueError(f'Built-in {fn_name} not implemented yet')


def validate_params(name: str, args: list[InvokeValue], params: list[inspect.Parameter]):
    for i, (arg, param) in enumerate(zip(args, params), start=1):
        assert isinstance(arg, param.annotation) or param.annotation is inspect._empty, \
            f'{name}: Invalid type {type(arg).__name__} found for arg {i} "{param.name}", expected {param.annotation.__name__}'

    amount_delta = len(args) - len(params)
    assert amount_delta <= 0, f'{name}: Supplied {amount_delta} arg{s(amount_delta)} too many ({args[-amount_delta:]})'
    assert amount_delta == 0, f'{name}: Supplied {-amount_delta} arg{s(-amount_delta)} too few (missing {params})'


def builtin(f: Callable[..., list[Asm]]):
    params = list(inspect.signature(f).parameters.values())

    def inner_builtin(name: str, scope: Scope, args: list[InvokeValue]) -> list[Asm]:
        validate_params(
            name,
            args,
            params[1:]
        )
        return f(scope, *args)
    return inner_builtin


def valid_annotation(param: inspect.Parameter, expected: Any) -> bool:
    return param.annotation == expected or (
        param.name == '_' and param.annotation is inspect._empty
    )


def constructor_builtin(f: Callable[..., list[Asm]]):
    params = list(inspect.signature(f).parameters.values())

    assert valid_annotation(params[0], Scope), \
        f'Constructor built-in must accept `Scope` as first input (found {params[0].annotation})'
    assert valid_annotation(params[1], ConstructorData), \
        f'Constructor built-in must accept `ConstructorData` as second input (found {params[1].annotation})'

    def inner_builtin(name: str, scope: Scope, args: list[InvokeValue]) -> list[Asm]:
        print(f'args: {args}')
        validate_params(
            name,
            args,
            params[2:]
        )
        constructor_data = scope.for_constructor
        assert constructor_data is not None, f'{name} can only be used in constructor'
        return f(scope, constructor_data, *args)
    return inner_builtin


def gen_minimal_init(runtime: ObjectId, offset_op: Op) -> list[Asm]:
    return [
        to_size_mark_ref(runtime),   # [rsize]
        op('dup1'),                  # [rsize, rsize]
        to_start_mark_ref(runtime),  # [rsize, rsize, rstart]
        offset_op,                   # [rsize, rsize, rstart, offset]
        op('codecopy'),              # [rsize]
        offset_op,                   # [rsize, offset]
        op('return')
    ]


def bytes_to_push(data: bytes, size: int | None = None, avoid_push0: bool = False) -> Op:
    if len(data) == 1 and data[0] == 0 and not avoid_push0:
        return op('push0')
    return create_push(data, size)


def compile_literal(coptions: CompileOptions, literal: Literal) -> Op:
    return bytes_to_push(literal.data, literal.size, coptions.avoid_push0)


def num_to_push(num: int, alt: dict[int, Op] | None = None) -> Op:
    alt_op = None if alt is None else alt.get(num)
    if alt_op is not None:
        return alt_op
    return create_push(num.to_bytes(32, 'big'))


def gen_tiny_init(runtime: bytes, zero_op: Op) -> list[Asm]:
    assert len(runtime) <= 32, \
        f'Runtime of size {len(runtime)} too large for "tiny" initializer'

    if len(runtime) == 0:
        return [op('stop')]

    alts = {0: zero_op, 0x20: op('msize')}

    return [
        bytes_to_push(runtime),
        zero_op,
        op('mstore'),
        num_to_push(len(runtime), alts),
        num_to_push(0x20 - len(runtime), alts),
        op('return')
    ]


@builtin
def table_start(scope: Scope, table_ref: GeneralRef) -> list[Asm]:
    table = scope.reference_table(table_ref.ident)
    return [to_start_mark_ref(table.obj_id)]


@builtin
def table_size(scope: Scope, table_ref: GeneralRef) -> list[Asm]:
    table = scope.reference_table(table_ref.ident)
    return [to_size_mark_ref(table.obj_id)]


@builtin
def function_sig(scope: Scope, ref: GeneralRef) -> list[Asm]:
    try:
        f = scope.get_function(ref.ident)
        sig = function_to_sig(f)
    except AssertionError:
        try:
            err = scope.get_error(ref.ident)
            sig = error_to_sig(err)
        except AssertionError:
            raise AssertionError(
                f'No error / function of name "{ref.ident}" found'
            )
    return [
        create_push(keccak256(sig.encode())[:4])
    ]


@builtin
def event_hash(scope: Scope, event_ref: GeneralRef) -> list[Asm]:
    event = scope.get_event(event_ref.ident)
    sig = event_to_sig(event)
    return [
        create_push(keccak256(sig.encode()))
    ]


@constructor_builtin
def runtime_start(_, cdata: ConstructorData) -> list[Asm]:
    return [to_start_mark_ref(cdata.runtime)]


@constructor_builtin
def runtime_size(_, cdata: ConstructorData) -> list[Asm]:
    return [to_size_mark_ref(cdata.runtime)]


@constructor_builtin
def return_runtime(_, cdata: ConstructorData, offset_op: Op) -> list[Asm]:
    return gen_minimal_init(cdata.runtime, offset_op)


BUILT_INS: dict[str, Callable[[str, Scope, list[InvokeValue]], list[Asm]]] = {
    '__codesize': not_implemented,

    '__EVENT_HASH': event_hash,
    '__FUNC_SIG': function_sig,
    '__tablestart': table_start,
    '__tablesize': table_size,
    '__RUNTIME_START': runtime_start,
    '__RUNTIME_SIZE': runtime_size,
    '__RETURN_RUNTIME': return_runtime
}


def invoke_built_in(fn_name: str, scope: Scope, args: list[InvokeValue]) -> list[Asm]:
    assert fn_name in BUILT_INS, f'Unrecognized built-in "{fn_name}"'
    return BUILT_INS[fn_name](fn_name, scope, args)


def gen_constants(
    raw_constants: Iterable[tuple[Identifier, Optional[bytes]]],
    constant_overrides: dict[Identifier, bytes]
) -> dict[Identifier, Op]:
    constants: dict[Identifier, Op] = {}
    free_ptr: int = 0
    for ident, value in raw_constants:
        if value is None:
            value = free_ptr.to_bytes(
                byte_size(free_ptr),
                'big'
            )
            free_ptr += 1
        set_unique(
            constants,
            ident,
            bytes_to_push(value),
            on_dup=lambda ident: f'Duplicate constant "{ident}"'
        )
    for ident, value in constant_overrides.items():
        assert ident in constants, f'Override for nonexistent constant "{ident}"'
        constants[ident] = bytes_to_push(value)
    return constants


def expand_macro_to_asm(
    coptions: CompileOptions,
    macro_ident: Identifier,
    scope: Scope,
    args: list[MacroArg],
    labels: dict[Identifier, MarkId],
    ctx: ContextTracker,
    visited_macros: tuple[Identifier, ...]
) -> list[Asm]:
    macro = scope.get_macro(macro_ident)
    assert macro_ident not in visited_macros, f'Circular macro refrence in {macro_ident}'
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

    macro_trace_repr = ' -> '.join(visited_macros)

    for el in macro.body:
        if not isinstance(el, LabelDef):
            continue
        label = el.ident
        dest_id: MarkId = MarkId(ctx.next_obj_id(), MarkPurpose.Label)
        # TODO: Add warning when invoked macro has label shadowing parent
        assert label not in labels or labels[label].different_ctx(dest_id), \
            f'Duplicate label "{label}" in macro "{macro_trace_repr}"'
        labels[label] = dest_id

    def lookup_label(ident: Identifier) -> MarkRef:
        assert ident in labels, f'Label "{ident}" not found in {macro_trace_repr}'
        return MarkRef(labels[ident])

    def lookup_arg(ident: Identifier) -> MacroArg:
        assert ident in ident_to_arg, f'Invalid macro argument "{ident}" in {macro_trace_repr}'
        return ident_to_arg[ident]

    for el in macro.body:
        if isinstance(el, Literal):
            asm.append(compile_literal(coptions, el))
        elif isinstance(el, LabelDef):
            asm.extend([Mark(labels[el.ident]), Op(OP_MAP['jumpdest'], b'')])
        elif isinstance(el, GeneralRef):
            if el.ident in OP_MAP:
                asm.append(op(el.ident))
            else:
                asm.append(lookup_label(el.ident))
        elif isinstance(el, MacroParam):
            asm.append(lookup_arg(el.ident))
        elif isinstance(el, ConstRef):
            asm.append(scope.get_constant(el.ident))
        elif isinstance(el, Invocation):
            if el.ident in BUILT_INS:
                invoke_values: list[InvokeValue] = []
                for arg in el.args:
                    if isinstance(arg, GeneralRef):
                        if arg.ident in OP_MAP:
                            invoke_values.append(op(arg.ident))
                        else:
                            invoke_values.append(arg)
                    elif isinstance(arg, MacroParam):
                        invoke_values.append(lookup_arg(arg.ident))
                    elif isinstance(arg, Literal):
                        invoke_values.append(compile_literal(coptions, arg))
                    else:
                        raise TypeError(
                            f'Unrecognized built-in invocation argument {arg}'
                        )
                asm.extend(
                    invoke_built_in(el.ident, scope, invoke_values)
                )
            else:
                invoke_args: list[MacroArg] = []
                for arg in el.args:
                    if isinstance(arg, GeneralRef):
                        if arg.ident in OP_MAP:
                            invoke_args.append(op(arg.ident))
                        else:
                            invoke_args.append(lookup_label(arg.ident))
                    elif isinstance(arg, MacroParam):
                        invoke_args.append(lookup_arg(arg.ident))
                    elif isinstance(arg, Literal):
                        invoke_args.append(compile_literal(coptions, arg))
                    else:
                        raise TypeError(
                            f'Unrecognized macro invocation argument {arg}'
                        )
                asm.extend(
                    expand_macro_to_asm(
                        coptions,
                        el.ident,
                        scope,
                        invoke_args,
                        {
                            label: mid
                            for label, mid in labels.items()
                            if label.startswith('global_')
                        },
                        ctx.next_sub_context(),
                        visited_macros
                    )
                )
        else:
            raise TypeError(f'Unrecognized macro element {el}')

    return asm
