from typing import NamedTuple
from enum import Enum
from .opcodes import Op, create_push
from .context import ObjectId
from .utils import build_unique_dict


class MarkPurpose(Enum):
    Start = 'Start'
    End = 'End'
    Label = 'Label'
    Other = 'Other'


class MarkId (NamedTuple(
    'MarkId',
    [
        ('obj_id', ObjectId),
        ('purpose', MarkPurpose)
    ]
)):
    def different_ctx(self, other: 'MarkId') -> bool:
        return self.obj_id.ctx_id != other.obj_id.ctx_id


Mark = NamedTuple('Mark', [('mid', MarkId)])
MarkRef = NamedTuple('MarkRef', [('mid', MarkId)])
MarkDeltaRef = NamedTuple('MarkDeltaRef', [('start', MarkId), ('end', MarkId)])
SizedRef = NamedTuple(
    'SizedRef',
    [('ref', MarkRef | MarkDeltaRef), ('offset_size', int)]
)


Asm = Op | Mark | MarkRef | MarkDeltaRef | bytes
SolidAsm = Op | Mark | SizedRef | bytes


def to_start_mark(obj_id: ObjectId) -> Mark:
    return Mark(MarkId(obj_id, MarkPurpose.Start))


def to_end_mark(obj_id: ObjectId) -> Mark:
    return Mark(MarkId(obj_id, MarkPurpose.End))


def to_start_mark_ref(obj_id: ObjectId) -> MarkRef:
    return MarkRef(MarkId(obj_id, MarkPurpose.Start))


def to_end_mark_ref(obj_id: ObjectId) -> MarkRef:
    return MarkRef(MarkId(obj_id, MarkPurpose.End))


def to_size_mark_ref(obj_id: ObjectId) -> MarkDeltaRef:
    start = MarkId(obj_id, MarkPurpose.Start)
    end = MarkId(obj_id, MarkPurpose.End)
    return MarkDeltaRef(start, end)


def set_size(ref: SizedRef, size: int) -> SizedRef:
    return SizedRef(ref.ref, size)


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


def get_size(step: SolidAsm) -> int:
    if isinstance(step, Op):
        return 1 + len(step.extra_data)
    elif isinstance(step, bytes):
        return len(step)
    elif isinstance(step, SizedRef):
        return 1 + step.offset_size
    elif isinstance(step, Mark):
        return 0
    else:
        raise TypeError(f'Unhandled step {step}')


def needed_bytes(x: int) -> int:
    return max((x.bit_length() + 7) // 8, 1)


def get_min_static_size_bytes(asm: list[Asm]) -> int:
    '''Compute the minimum size in bytes that'd capture any code offset'''
    ref_count = sum(isinstance(step, (MarkRef, MarkDeltaRef)) for step in asm)
    min_static_total_size = sum(map(min_static_size, asm))
    ref_bytes = 1
    while ((1 << (8 * ref_bytes)) - 1) < min_static_total_size + ref_bytes * ref_count:
        ref_bytes += 1
    return ref_bytes


def asm_to_solid(asm: list[Asm]) -> list[SolidAsm]:
    size_bytes = get_min_static_size_bytes(asm)
    assert size_bytes <= 6
    return [
        SizedRef(step, size_bytes)
        if isinstance(step, (MarkRef, MarkDeltaRef))
        else step
        for step in asm
    ]


def validate_asm(asm: list[Asm]) -> None:
    '''
    Checks that MarkDeltaRef steps have strictly different, correctly ordered references and that all
    marks have unique IDs
    '''
    # Checks that all MarkIDs are unique while build indices dict
    indices: dict[MarkId, int] = build_unique_dict([
        (step.mid, i)
        for i, step in enumerate(asm)
        if isinstance(step, Mark)
    ], lambda mid: f'Duplicate mid #{mid}')
    for i, step in enumerate(asm):
        if isinstance(step, MarkRef):
            assert step.mid in indices, f'Assembly step #{i} has invalid reference to {step.mid}'
        elif isinstance(step, MarkDeltaRef):
            assert step.start in indices, f'Assembly step #{i} has invalid reference to {step.start}'
            assert step.end in indices, f'Assembly step #{i} has invalid reference to {step.end}'
            assert indices[step.end] > indices[step.start], \
                f'Assembly step #{i} references negative delta'


def get_solid_offsets(asm: list[SolidAsm]) -> dict[MarkId, int]:
    mark_offsets: dict[MarkId, int] = {}
    offset = 0
    for step in asm:
        if isinstance(step, Mark):
            mark_offsets[step.mid] = offset
        offset += get_size(step)
    return mark_offsets


def shorten_asm_once(asm: list[SolidAsm]) -> tuple[bool, list[SolidAsm]]:
    mark_offsets: dict[MarkId, int] = get_solid_offsets(asm)

    changed_any = False
    shortened_steps: list[SolidAsm] = []
    for step in asm:
        if isinstance(step, SizedRef):
            ref = step.ref
            if isinstance(ref, MarkRef):
                req_size = needed_bytes(mark_offsets[ref.mid])
                if req_size != step.offset_size:
                    changed_any = True
                    step = set_size(step, req_size)
            elif isinstance(ref, MarkDeltaRef):
                req_size = needed_bytes(
                    mark_offsets[ref.end] - mark_offsets[ref.start]
                )
                if req_size != step.offset_size:
                    changed_any = True
                    step = set_size(step, req_size)
            else:
                assert False  # Sanity check
        shortened_steps.append(step)

    return changed_any, shortened_steps


def shorten_asm(asm: list[SolidAsm]) -> list[SolidAsm]:
    changed_any = True
    while changed_any:
        changed_any, asm = shorten_asm_once(asm)
    return asm


def solid_asm_to_bytecode(asm: list[SolidAsm]) -> bytes:
    mark_offsets: dict[MarkId, int] = get_solid_offsets(asm)
    final_bytes: bytes = bytes()

    # Create skeleton for final bytecode
    for step in asm:
        if isinstance(step, Op):
            final_bytes += bytes(step.get_bytes())
        elif isinstance(step, bytes):
            final_bytes += step
        elif isinstance(step, SizedRef):
            ref = step.ref
            if isinstance(ref, MarkRef):
                value = mark_offsets[ref.mid]
            elif isinstance(ref, MarkDeltaRef):
                value = mark_offsets[ref.end] - mark_offsets[ref.start]
            else:
                assert False
            push = create_push(value.to_bytes(step.offset_size, 'big'))
            final_bytes += bytes(push.get_bytes())
        elif isinstance(step, Mark):
            # Mark generates no bytes
            pass
        else:
            raise ValueError(f'Unrecognized assembly step {step}')

    return final_bytes


def asm_to_bytecode(asm: list[Asm]) -> bytes:
    validate_asm(asm)
    solid_asm = asm_to_solid(asm)
    solid_asm = shorten_asm(solid_asm)
    return solid_asm_to_bytecode(solid_asm)
