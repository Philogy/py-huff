from typing import NamedTuple, Generator, Optional
from enum import Enum

Content = list['ExNode'] | str


class ContentType(Enum):
    Text = 'Text'
    SubNodes = 'SubNodes'


class ExNode (NamedTuple(
    'ExNode',
    [
        ('name', str),
        ('content', Content),
        ('start', int),
        ('end', int)
    ]
)):
    def ctype(self) -> ContentType:
        if isinstance(self.content, list):
            return ContentType.SubNodes
        else:
            return ContentType.Text

    def children(self) -> list['ExNode']:
        if not isinstance(self.content, list):
            raise TypeError(f'Content of node is str not sub nodes')
        return self.content

    def text(self) -> str:
        if not isinstance(self.content, str):
            raise TypeError(f'Node has sub nodes, no direct string content')
        return self.content

    def get_all_deep(self, name, depth: int = -1) -> Generator['ExNode', None, None]:
        if self.name == name:
            yield self
            return
        if isinstance(self.content, str):
            return
        if depth == 0:
            return
        assert isinstance(self.content, list)
        for child in self.content:
            if child.name == name:
                yield child
            else:
                yield from child.get_all_deep(name, depth=depth - 1)

    def get_all(self, name: str) -> Generator['ExNode', None, None]:
        if isinstance(self.content, str):
            return
        yield from (
            child
            for child in self.content
            if child.name == name
        )

    def maybe_get(self, name: str) -> Optional['ExNode']:
        matches = list(self.get_all(name))
        if len(matches) > 1:
            raise ValueError(
                f'{len(matches)} instances of "{name}" found, expectd 1'
            )
        if matches:
            return matches[0]
        else:
            return None

    def get(self, name: str) -> 'ExNode':
        gotten = self.maybe_get(name)
        if gotten is None:
            raise ValueError(f'"{name}" not found')
        return gotten

    def get_idx(self, i: int) -> 'ExNode':
        return self.children()[i]

    def _disp(self, rem_depth=-1, depth=0):
        if isinstance(self.content, list):
            print(f'{"  " * depth}[{self.name}]')
            if not rem_depth:
                return
            for child in self.content:
                child._disp(rem_depth-1, depth+1)
        else:
            print(f'{"  " * depth}[{self.name}] {self.content!r}')
