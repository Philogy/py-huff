# `py-huff`

`py-huff` is a compiler for Huff, an EVM assembly language written in Python.

> [!WARNING]
> This repo is experimental, for a more tested Huff compiler see [huff-rs](https://github.com/huff-language/huff-rs)

## Installation

Important: Python 3.10 or higher is required

1. `git clone https://github.com/philogy/py-huff`
2. `cd py-huff`
3. `pip install -e .`

Ready to use either `py_huff` itself as a Python API for Huff as a CLI via `huffy`.

## Usage

**Compile code (Compiles constructor or adds default)**
```
huffy -b my_huff_contract.huff
```

**Compile code (no deploy)**
```
huffy -r my_huff_contract.huff
```

## Motivation

- Create a simpler huff compiler (`huff-rs` always felt overly complicated to me)
- Improve some semantics around jump destinations
- Have a second implementation that can be used to differentially test the original `huff-rs`
- Make it potentially feasible for a Huff compiler to be included in the audit scope for
  [METH](https://github.com/philogy/meth-weth)

## Differences vs. [`huff-rs`](https://github.com/huff-language/huff-rs/)

### New Features
**Constructor Helpers (Only usable from constructor)**
- `__RUNTIME_START()`: Generates a `PUSH` with the code offset of where the runtime bytecode begins.
- `__RUNTIME_SIZE()`: Generates a `PUSH` with the length in bytes of the runtime code. Can be used
  together with `__RUNTIME_START` to create a custom constructor:

```
#define macro CONSTRUCTOR() = takes(0) returns(0) {
    // owner = msg.sender
    caller
    0x0
    sstore
    // return runtime
    __RUNTIME_SIZE()
    dup1
    __RUNTIME_START()
    0x0
    codecopy
    0x0
    return
}
```
- `__RETURN_RUNTIME(offset: Op)`: Generates the default constructor, copying the runtime code to the
  offset pushed by `offset`, equivalent to:
```
__RUNTIME_SIZE()
dup1
__RUNTIME_START()
<offset>
codecopy
<offset
return
```

### Missing Features
- ❌ Jump Tables (❌ normal, ❌ packed, ✅ code (already present))
- ❌ `__codesize`
- ❌ Fns (non-inlined macros)
    - ❌ Recursion


### Jump destinations
Unlike `huff-rs`, `py-huff` supports jump destinations larger or smaller than 2-bytes. The size of
the push opcode will automatically be adjusted to a smaller size. Furthermore `py-huff` has an
optimization step that will shorten earlier labels if they can fit into smaller push opcodes.

### Jump Labels
`huff-rs` currently has some unclear jump label semantics (see [#295](https://github.com/huff-language/huff-rs/issues/295)), `py-huff` attempts to introduce clear jump label scoping and semantics:

- each label has a scope tied to the macro it's present within
- duplicate label declarations in the same macro throws an error
- invoked macros can only access labels defined in their own context or their parent's
- a reference to a label will select the deepest one e.g.
    ```
    #define macro A() = takes(0) returns(0) {
        label:         <-------------\
        B()                          |
        label jump     references ---/
    }

    #define macro B() = takes(0) returns(0) {
        label:         <--------------------------\
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
