from parsimonious.grammar import Grammar
from parsimonious.nodes import Node
from typing import NamedTuple, Any

Children = list['ExNode'] | str
ExNode = NamedTuple(
    'ExNode',
    [
        ('name', str),
        ('children', Children),
        ('start', int),
        ('end', int)
    ]
)

HUFF_GRAMMAR = Grammar(
    fr'''
    program = gap (definition gap)*
    definition = macro / include / const / code_table / function_def / event_def / error_def / jump_table

    comment = line_comment / multi_line_comment
    line_comment = "//" ~"[^\n]*"
    multi_line_comment = "/*" (("*" !"/") / ~"[^*]")* "*/"

    include = "#include \"" (~"[a-zA-Z0-9_-]" / "/" / ".")* "\""

    const = "#define" ws "constant" ws identifier ws "=" ws (hex_literal / "FREE_STORAGE_POINTER()")

    code_table = "#define" ws "table" ws identifier ws "{{" gap hex_literal gap "}}"

    function_def = "#define" ws "function" ws identifier ws tuple ws ("view" / "nonpayable" / "payable") ws "returns" ws tuple

    event_def = "#define" ws "event" ws identifier ws "(" ws (event_arg ws "," ws )* event_arg? ws ")"
    event_arg = type ws "indexed"?

    error_def = "#define" ws "error" ws identifier ws tuple

    jump_table = "#define" ws "jumptable" "__packed"? ws identifier ws "{{" gap (identifier gap)+ "}}"

    macro = "#define" ws macro_type ws identifier ws params ws "=" ws macro_returns_takes ws "{{" macro_body "}}"
    macro_type = "macro" / "fn"
    macro_returns_takes = "takes" ws "(" num ")" ws "returns" ws "(" num ")"
    macro_body = ws (macro_body_el ws) *
    macro_body_el = dest_definition / hex_literal / push_op / macro_arg / const_ref / invocation / identifier / comment
    push_op = "push" num ws hex_literal
    dest_definition = identifier ":"
    invocation = identifier ws "(" ws (call_arg ws "," ws)* call_arg? ws ")"
    call_arg = macro_arg / identifier / hex_literal / push_op
    macro_arg = "<" ws identifier ws ">"
    const_ref = "[" ws identifier ws "]"

    type = (("uint" num?) / ("bytes" num?) / "string" / "address" / tuple) ("[" ws num? ws "]") ?
    tuple = "(" ws (type ws identifier? ws "," ws )* (type ws identifier?)? ws ")"

    params = "(" ws param_list ws ")"
    param_list = ws (identifier ws "," ws)* identifier?

    identifier = ~"[a-zA-Z_][a-zA-Z0-9_]*"
    num = ~"[1-9][0-9]*" / "0"
    hex_literal = "0x" ~"[a-fA-F0-9]+"
    gap = ws (comment ws)*
    ws = ~"\s*"
    '''
)


def to_ex_node(node: Node, prune: frozenset[str] = frozenset()) -> ExNode:
    '''Converts parsimonious node to as simpler, nested tuple "ExNode"'''
    name = node.expr_name
    final_children: Children = node.text
    if node.children:
        children: list[ExNode] = []
        for child in node.children:
            if child.expr_name in prune:
                continue
            ex_child = to_ex_node(child, prune)
            if ex_child.children:
                children.append(ex_child)
        if len(children) == 1:
            if name == '':
                return children[0]

            if children[0].name == '':
                final_children = children[0].children
            else:
                final_children = children
        else:
            final_children = children

    return ExNode(name, final_children or '', node.start, node.end)


def disp_node(node: ExNode, rem_depth=-1, depth=0):
    if isinstance(node.children, str):
        print(f'{"  " * depth}[{node.name}] {node.children!r}')
    else:
        print(f'{"  " * depth}[{node.name}]')
        if rem_depth:
            for child in node.children:
                disp_node(child, rem_depth-1, depth+1)


def parse_huff(s: str) -> ExNode:
    node = HUFF_GRAMMAR.parse(s)
    return to_ex_node(node, prune=frozenset({'ws', 'gap', 'comment'}))
