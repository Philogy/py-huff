from typing import TypeVar, Iterable, Callable, Any
from Crypto.Hash import keccak

T = TypeVar('T')
K = TypeVar('K')
V = TypeVar('V')


def default_unique_error(ident: Any) -> str:
    return f'Duplicate key {ident}'


DupErrorGen = Callable[[K], str]


def set_unique(d: dict[K, V], k: K, v: V,  error: str) -> dict[K, V]:
    assert k not in d, f'{error} {k!r}'
    d[k] = v
    return d


def build_unique_dict(
    kvs: Iterable[tuple[K, V]],
    error: str = 'Duplicate key'
) -> dict[K, V]:
    new_dict: dict[K, V] = {}
    for key, value in kvs:
        new_dict = set_unique(new_dict, key, value, error=error)
    return new_dict


def keccak256(preimage: bytes) -> bytes:
    return keccak.new(data=preimage, digest_bits=256).digest()
