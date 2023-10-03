from parsimonious.grammar import Grammar
from parsimonious.nodes import NodeVisitor, Node
import sys
from typing import NamedTuple, Any
from toolz import curry

ExNode = NamedTuple(
    'ExNode',
    [
        ('name', str),
        ('children', str | list['ExNode'])
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

    macro = "#define" ws "macro" ws identifier ws params ws "=" ws macro_returns_takes ws "{{" macro_body "}}"
    macro_returns_takes = "takes" ws "(" num ")" ws "returns" ws "(" num ")"
    macro_body = ws (macro_body_el ws) *
    macro_body_el = dest_definition / hex_literal / push_op / macro_arg / const_ref / invocation / identifier / comment
    push_op = "push" num ws hex_literal
    dest_definition = identifier ":"
    invocation = identifier ws "(" ws (call_arg ws "," ws)* call_arg? ws ")"
    call_arg = macro_arg / identifier / hex_literal
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

Macro = NamedTuple('Macro', [
    ('name', str),
    ('params', tuple[str, ...]),
    ('takes', int),
    ('returns', int),
    ('body', Any)
])


Invocation = NamedTuple('Invocation', [
    ('fn_name', str),
    ('inputs', list[Any])
])

Identifier = NamedTuple('Identifier', [('text', str)])


def not_none(x) -> bool:
    return x is not None


def text(x) -> str:
    return x.text


def fc(children):
    return filter(not_none, children)


# Picks up children
def school_run(name, node):
    le_macro = name == 'macro_body_el'
    if isinstance(node, list):
        for child in fc(node):
            if le_macro:
                print(f'child: {child}')
            yield from school_run(name, child)
    elif isinstance(node, Node):
        if node.expr_name == name:
            if le_macro:
                print(node.prettily())
            yield node
        else:
            yield from school_run(name, node.children)
    else:
        yield node


def lmap(f, t):
    return list(map(f, t))


def map_nodes(node, n=0):
    if isinstance(node, list):
        print(' ' * (n * 2) + '-')
        for c in node:
            map_nodes(c, n+1)
    elif isinstance(node, Node):
        print(' ' * (n * 2) + f'- {node.expr_name}')
        map_nodes(node.children, n+1)
    else:
        print(' ' * (n * 2) + f'- {node}')


class CodeGen(NodeVisitor):
    def __init__(self) -> None:
        pass

    # def visit_program(self, node, vc):
    #     defs,  = fc(vc)
    #     for d, in map(fc, defs):
    #         print(f'd: {d}')

    # def visit_macro(self, node: Node, visited_children):
    #     _, _, name, params, _, (takes, returns), _, body, _ =\
    #         fc(visited_children)
    #     return Macro(name.text, lmap(text, params), takes, returns, body)

    # def visit_macro_body(self, _, vc):
    #     for c in vc:
    #         print('\n\n\n')
    #         print(c)
    #     map_nodes(vc)
    #     elements = list(school_run('macro_body_el', vc))
    #     print(f'elements: {elements}')
    #     return elements

    # def visit_macro_returns_takes(self, node: Node, visited_children):
    #     _, _, takes, _, _, _, returns, _ = fc(visited_children)
    #     return takes, returns

    # def visit_params(self, node, visited_children):
    #     return list(school_run('identifier', visited_children))

    # def visit_invocation(self, _, vc):
    #     return Invocation(vc[0].text, list(school_run('call_arg', vc[1:])))

    # def visit_num(self, node, _):
    #     return int(node.text)

    # def visit_identifier(self, node, _):
    #     return Identifier(node.text)

    # def visit_ws(self, *_):
    #     return None

    # def visit_gap(self, *_):
    #     return None

    # def visit_comment(self, *_):
    #     return None

    def generic_visit(self, node, visited_children):
        """ The generic visit method. """
        return visited_children or node


def to_ex_node(node: Node, prune: frozenset[str] = frozenset()):
    if node.children:
        children = []
        for child in node.children:
            if child.expr_name in prune:
                continue
            ex_child = to_ex_node(child, prune)
            if ex_child.children:
                children.append(ex_child)
        if node.expr_name == '' and len(children) == 1:
            return children[0]
    else:
        children = node.text

    return ExNode(
        node.expr_name,
        children or ''
    )


def disp_node(node: ExNode, rem_depth=-1, depth=0):
    if isinstance(node.children, str):
        print(f'{"  " * depth}[{node.name}] {node.children!r}')
    else:
        print(f'{"  " * depth}[{node.name}]')
        if rem_depth:
            for child in node.children:
                disp_node(child, rem_depth-1, depth+1)


def main():
    with open(sys.argv[1], 'r') as f:
        node = HUFF_GRAMMAR.parse(f.read())
    ex = to_ex_node(node, prune=frozenset({'ws', 'gap', 'comment'}))
    disp_node(ex)


if __name__ == '__main__':
    main()
