from .opcodes import Op, create_push, create_plain_op
from typing import NamedTuple


ContextId = tuple[int, ...]
MarkId = tuple[ContextId, int]
Mark = NamedTuple('Mark', [('mid', MarkId)])
MarkRef = NamedTuple('MarkRef', [('ref', MarkId)])
MarkDeltaRef = NamedTuple('MarkDeltaRef', [('start', MarkId), ('end', MarkId)])
Asm = Op | Mark | MarkRef | MarkDeltaRef | bytes

START_SUB_ID = 0
END_SUB_ID = 1


def min_static_size(step: Asm) -> int:
    if isinstance(step, Op):
        return 1 + len(step.extra_data)
    elif isinstance(step, bytes):
        return len(step)
    elif isinstance(step, (MarkRef, MarkDeltaRef)):
        return 1
    elif isinstance(step, Mark):
        return 0
    else:
        raise TypeError(f'Unhandled step {step}')


def get_min_dest_bytes(asm: list[Asm]) -> int:
    '''Compute the minimum size in bytes that'd work for any jump destination'''
    ref_count = sum(isinstance(step, (MarkRef, MarkDeltaRef)) for step in asm)
    min_static_len = sum(map(min_static_size, asm))
    dest_bytes = 1
    while ((1 << (8 * dest_bytes)) - 1) < min_static_len + dest_bytes * ref_count:
        dest_bytes += 1
    return dest_bytes


def asm_to_bytecode(asm: list[Asm]) -> bytes:
    dest_bytes = get_min_dest_bytes(asm)
    assert dest_bytes <= 6
    marks: dict[MarkId, int] = {}
    final_bytes: list[int] = []
    refs: list[tuple[int, MarkId]] = []
    delta_refs: list[tuple[int, MarkId, MarkId]] = []

    # Create skeleton for final bytecode
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

    # Insert destinations for marker references (MarkRef)
    for offset, dest_id in refs:
        for i, b in enumerate(marks[dest_id].to_bytes(dest_bytes, 'big'), start=offset):
            final_bytes[i] = b

    # Calculate and insert distances between marker references (MarkDeltaRef)
    for offset, start_id, end_id in delta_refs:
        start_offset = marks[start_id]
        end_offset = marks[end_id]
        assert end_offset >= start_offset, 'Inverted offsets'
        size = end_offset - start_offset
        for i, b in enumerate(size.to_bytes(dest_bytes, 'big'), start=offset):
            final_bytes[i] = b

    return bytes(final_bytes)


def minimal_deploy(runtime: bytes) -> bytes:
    start: MarkId = tuple(), START_SUB_ID
    end: MarkId = tuple(), END_SUB_ID
    return asm_to_bytecode([
        MarkDeltaRef(start, end),
        create_plain_op('dup1'),
        MarkRef(start),
        create_plain_op('push0'),
        create_plain_op('codecopy'),
        create_plain_op('push0'),
        create_plain_op('return'),
        Mark(start),
        runtime,
        Mark(end)
    ])
