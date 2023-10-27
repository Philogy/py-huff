from typing import NamedTuple

ContextId = tuple[int, ...]
ObjectId = NamedTuple('ObjectId', [('ctx_id', ContextId), ('sub_id', int)])


class ContextTracker:
    def __init__(self, ctx: ContextId):
        self.ctx = ctx
        self.next_sub_id = 0
        self.sub_context_offset = 0

    def next_obj_id(self) -> ObjectId:
        sub_id = self.next_sub_id
        self.next_sub_id += 1
        return ObjectId(self.ctx, sub_id)

    def next_sub_context(self):
        sub_ctx = self.ctx + (self.sub_context_offset,)
        self.sub_context_offset += 1
        return ContextTracker(sub_ctx)
