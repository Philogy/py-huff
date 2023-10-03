# `py-huff`
`py-huff` is a Huff compiler written in Python.

## Installation

1. `git clone https://github.com/philogy/py-huff`
2. `cd py-huff`
3. `pip install types-parsimonious parsimonious`

Ready to use (yes this is very barebones, maybe available as PyPi package soon™️)

## Usage

```
python3 main.py <huff_file_path>
```

## Motivation

- Create a simpler huff compiler (`huff-rs` always felt overly complicated to me)
- Improve some semantics around jump destinations
- Have a second implementation that can be used to differentially test the original `huff-rs`
- Make it potentially feasible for a Huff compiler to be included in the audit scope for
  [METH](https://github.com/philogy/meth-weth)

## Differences vs. [`huff-rs`](https://github.com/huff-language/huff-rs/)
Besides the missing features as listed under _Features_ this implementation has a few differences to
`huff-rs` (as of [`813b6b6`](https://github.com/huff-language/huff-rs/commit/813b6b683dd214dfca71d49284afd885dd9eef09)).

### Jump destinations
Unlike `huff-rs`, `py-huff` supports jump destinations larger or smaller than 2-bytes. The size of
the push opcode will automatically be adjusted to a smaller size. Note that like `huff-rs`, `py-huff`
keeps the size of all push jump dests the same, meaning if your contract is more than 255 bytes long
all jump dest pushes will be `PUSH2`s, even if earlier destinations would fit in 1 byte.

### Jump Labels
`huff-rs` currently has some unclear jump label semantics (see [#295](https://github.com/huff-language/huff-rs/issues/295)), `py-huff` attempts to introduce clear jump label scoping and semantics:

- each label has a scope tied to the macro it's present within
- duplicate label declarations in the same macro throws an error
- invoked macros can only access labels defined in their own context or their parent's
- a reference to a label will select the deepest one e.g.
    ```
    #define macro A() = takes(0) returns(0) {
        label:         <-------------\ <----------\
        B()                          |            |
        label jump     references ---/            |
    }                                             |
                                                  |
    #define macro B() = takes(0) returns(0) {     |
        label:                                    |
        C()                                       |
    }                                             |
                                                  |
    #define macro C() = takes(0) returns(0) {     |
        D()                                       |
    }                                             |
                                                  |
    #define macro D() = takes(0) returns(0) {     |
        label jump     references ----------------/
    }

    #define macro E() = takes(0) returns(0) {
        label jump
    }

    #define macro MAIN() = takes(0) returns(0) {
        A()
        E()            <throws>
    }
    ```

## Features
### Core Huff Features
- ✅ Opcodes
- ✅ Hex literals (e.g. `0x238a`)
- ✅ Jump labels
- ✅ Macros
    - ✅ Macro arguments (✅ literals, ✅ jump labels, ✅ macro parameters)
    - ✅ Nested macros (e.g. `A() -> B() -> C()`)
- ✅ Runtime bytecode
- ❌ Deploy bytecode
### Added Features
- ❌ Built-ins
    - ❌ `__EVENT_HASH`
    - ❌ `__FUNC_SIG`
    - ❌ `__codesize`
    - ❌ `__tablestart`
    - ❌ `__tablesize`

### Niche/Advanced Features
- ✅ Push literals (e.g. `push4 0x010`)
- ❌ Fns (non-inlined macros)
    - ❌ Recursion

