from typing import NamedTuple, Generator

OP_MAP = {
    'stop': 0x00,
    'add': 0x01,
    'mul': 0x02,
    'sub': 0x03,
    'div': 0x04,
    'sdiv': 0x05,
    'mod': 0x06,
    'smod': 0x07,
    'addmod': 0x08,
    'mulmod': 0x09,
    'exp': 0x0a,
    'signextend': 0x0b,
    'lt': 0x10,
    'gt': 0x11,
    'slt': 0x12,
    'sgt': 0x13,
    'eq': 0x14,
    'iszero': 0x15,
    'and': 0x16,
    'or': 0x17,
    'xor': 0x18,
    'not': 0x19,
    'byte': 0x1a,
    'shl': 0x1b,
    'shr': 0x1c,
    'sar': 0x1d,
    'sha3': 0x20,
    'address': 0x30,
    'balance': 0x31,
    'origin': 0x32,
    'caller': 0x33,
    'callvalue': 0x34,
    'calldataload': 0x35,
    'calldatasize': 0x36,
    'calldatacopy': 0x37,
    'codesize': 0x38,
    'codecopy': 0x39,
    'gasprice': 0x3a,
    'extcodesize': 0x3b,
    'extcodecopy': 0x3c,
    'returndatasize': 0x3d,
    'returndatacopy': 0x3e,
    'extcodehash': 0x3f,
    'blockhash': 0x40,
    'coinbase': 0x41,
    'timestamp': 0x42,
    'number': 0x43,
    'difficulty': 0x44,
    'prevrandao': 0x44,
    'gaslimit': 0x45,
    'chainid': 0x46,
    'selfbalance': 0x47,
    'basefee': 0x48,
    'pop': 0x50,
    'mload': 0x51,
    'mstore': 0x52,
    'mstore8': 0x53,
    'sload': 0x54,
    'sstore': 0x55,
    'jump': 0x56,
    'jumpi': 0x57,
    'pc': 0x58,
    'msize': 0x59,
    'gas': 0x5a,
    'jumpdest': 0x5b,
    'tload': 0x5c,
    'tstore': 0x5d,
    'push0': 0x5f,
    'push1': 0x60,
    'push2': 0x61,
    'push3': 0x62,
    'push4': 0x63,
    'push5': 0x64,
    'push6': 0x65,
    'push7': 0x66,
    'push8': 0x67,
    'push9': 0x68,
    'push10': 0x69,
    'push11': 0x6a,
    'push12': 0x6b,
    'push13': 0x6c,
    'push14': 0x6d,
    'push15': 0x6e,
    'push16': 0x6f,
    'push17': 0x70,
    'push18': 0x71,
    'push19': 0x72,
    'push20': 0x73,
    'push21': 0x74,
    'push22': 0x75,
    'push23': 0x76,
    'push24': 0x77,
    'push25': 0x78,
    'push26': 0x79,
    'push27': 0x7a,
    'push28': 0x7b,
    'push29': 0x7c,
    'push30': 0x7d,
    'push31': 0x7e,
    'push32': 0x7f,
    'dup1': 0x80,
    'dup2': 0x81,
    'dup3': 0x82,
    'dup4': 0x83,
    'dup5': 0x84,
    'dup6': 0x85,
    'dup7': 0x86,
    'dup8': 0x87,
    'dup9': 0x88,
    'dup10': 0x89,
    'dup11': 0x8a,
    'dup12': 0x8b,
    'dup13': 0x8c,
    'dup14': 0x8d,
    'dup15': 0x8e,
    'dup16': 0x8f,
    'swap1': 0x90,
    'swap2': 0x91,
    'swap3': 0x92,
    'swap4': 0x93,
    'swap5': 0x94,
    'swap6': 0x95,
    'swap7': 0x96,
    'swap8': 0x97,
    'swap9': 0x98,
    'swap10': 0x99,
    'swap11': 0x9a,
    'swap12': 0x9b,
    'swap13': 0x9c,
    'swap14': 0x9d,
    'swap15': 0x9e,
    'swap16': 0x9f,
    'log0': 0xa0,
    'log1': 0xa1,
    'log2': 0xa2,
    'log3': 0xa3,
    'log4': 0xa4,
    'create': 0xf0,
    'call': 0xf1,
    'callcode': 0xf2,
    'return': 0xf3,
    'delegatecall': 0xf4,
    'create2': 0xf5,
    'staticcall': 0xfa,
    'revert': 0xfd,
    'invalid': 0xfe,
    'selfdestruct': 0xff,
}


class Op(NamedTuple('Op', [('op', int), ('extra_data', bytes)])):
    def get_bytes(self) -> Generator[int, None, None]:
        yield self.op
        yield from self.extra_data

    def __repr__(self) -> str:
        extra_data_repr = f' 0x{self.extra_data.hex()}' if self.extra_data else ''
        for name, op in OP_MAP.items():
            if op == self.op:
                return f'{name.upper()}{extra_data_repr}'

        return f'UNKNOWN \'0x{self.op:02x}\' {extra_data_repr}'


def op(op_name: str) -> Op:
    assert not op_name.startswith('push') or op_name == 'push0', \
        f'Standalone {op_name} not supported'
    return Op(OP_MAP[op_name], b'')


def create_push(data: bytes, size: int | None = None) -> Op:
    if size is None:
        while len(data) > 1 and data[0] == 0:
            data = data[1:]
        size = len(data)
    else:
        assert len(data) <= size, \
            f'Expected data to be no more than {size} bytes long, got {len(data)}'
        padding = b'\x00'*(size - len(data))
        data = padding + data
    assert size in range(1, 32 + 1), f'No push of size {size}'
    return Op(0x5f + size, data)
