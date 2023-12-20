from typing import TypeVar, Iterable, Callable, Any
from Crypto.Hash import keccak

T = TypeVar('T')
K = TypeVar('K')
V = TypeVar('V')


DupErrorGen = Callable[[K], str]


def default_unique_error(ident):
    return f'Duplicate unique_dict key {ident}'


def set_unique(d: dict[K, V], k: K, v: V,  on_dup: DupErrorGen | str = default_unique_error) -> dict[K, V]:
    assert k not in d, on_dup(k) if callable(on_dup) else on_dup
    d[k] = v
    return d


def build_unique_dict(
    kvs: Iterable[tuple[K, V]],
    on_dup: DupErrorGen | str = 'unique_dict key'
) -> dict[K, V]:
    new_dict: dict[K, V] = {}
    for key, value in kvs:
        new_dict = set_unique(
            new_dict,
            key,
            value,
            on_dup=on_dup
        )
    return new_dict


def s(x: int) -> str:
    if x == 1:
        return ''
    return 's'


def keccak256(preimage: bytes) -> bytes:
    return keccak.new(data=preimage, digest_bits=256).digest()


def byte_size(x: int) -> int:
    return max((x.bit_length() + 7) // 8, 1)
