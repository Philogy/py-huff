from argparse import ArgumentParser
from .compile import compile


def parse_args():
    parser = ArgumentParser(
        description='A CLI for compiling Huff source code files to bytecode'
    )
    parser.add_argument('path', type=str)
    parser.add_argument('--runtime', '-r', action='store_true')
    parser.add_argument('--deploy', '-b', action='store_true')
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    compiled = compile(args.path)

    if args.runtime and args.deploy:
        print(f'bytecode: {compiled.deploy.hex()}')
        print(f'\nruntime: {compiled.runtime.hex()}')
    elif args.runtime:
        print(compiled.runtime.hex())
    elif args.deploy:
        print(compiled.deploy.hex())
    else:
        print('WARNING: Neither runtime or deploy bytecode output')


if __name__ == '__main__':
    main()
