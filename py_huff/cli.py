import re
from argparse import ArgumentParser
import json
from .parser import Identifier, literal_to_bytes
from .compile import compile


def parse_args():
    parser = ArgumentParser(
        description='A CLI for compiling Huff source code files to bytecode'
    )
    parser.add_argument('path', type=str)
    parser.add_argument('--runtime', '-r', action='store_true')
    parser.add_argument('--deploy', '-b', action='store_true')
    parser.add_argument('--constant', '-c', action='append', default=[])
    parser.add_argument('--artifacts', '-a', nargs='?',
                        const='artifacts.json', default=None)
    parser.add_argument('--avoid-push0', action='store_true')
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    constant_overrides: dict[Identifier, bytes] = {}
    for override in args.constant:
        assert (m := re.match(r'(\w+)=0x([0-9A-Fa-f]{1,64})', override)) is not None, \
            f'Invalid constant override {override}, must be of format CONSTANT_NAME=0x123 (hex value up to 64 bytes long)'
        name = m.group(1).upper()
        value = m.group(2)
        assert name not in constant_overrides, f'Duplicate override for constant "{name}"'
        constant_overrides[name] = literal_to_bytes(value)

    compiled = compile(args.path, constant_overrides, args.avoid_push0)

    if args.runtime and args.deploy:
        print(f'bytecode: {compiled.deploy.hex()}')
        print(f'\nruntime: {compiled.runtime.hex()}')
    elif args.runtime:
        print(compiled.runtime.hex())
    elif args.deploy:
        print(compiled.deploy.hex())
    else:
        print('WARNING: Neither runtime or deploy bytecode output')

    if args.artifacts is not None:
        with open(args.artifacts, 'w') as f:
            json.dump({
                'abi': compiled.abi,
                'deployedBytecode': {
                    'object': f'0x{compiled.runtime.hex()}'
                },
                'bytecode': {
                    'object': f'0x{compiled.deploy.hex()}'
                }
            }, f, indent=2)


if __name__ == '__main__':
    main()
