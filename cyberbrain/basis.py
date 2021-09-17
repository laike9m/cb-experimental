"""Some basic data structures used throughout the project."""

from __future__ import annotations

import dataclasses
from collections import defaultdict

import attr
import os
import shortuuid
from types import TracebackType
from typing import Any, TYPE_CHECKING, Optional, Type, Tuple

from . import utils

if TYPE_CHECKING:
    from .frame import Snapshot

_dummy = object()

ExcInfoType = Tuple[Type[BaseException], Exception, TracebackType]


@dataclasses.dataclass
class ExceptionInfo:
    """The concrete type of ExcInfoType."""

    type: Type[BaseException]
    value: Exception
    traceback: any


class UUIDGenerator:

    counter = defaultdict(int)

    @classmethod
    def generate_uuid(cls) -> str:
        """Generates a 8-char uuid."""
        if utils.run_in_test():
            # When run in test, generates predictable uids so we can assert on them.
            test_name = (
                # When executed in global scope, $PYTEST_CURRENT_TEST is not set.
                os.environ.get("PYTEST_CURRENT_TEST", "global")
                .split(":")[-1]
                .split(" ")[0]
            )
            count = cls.counter[test_name]
            cls.counter[test_name] += 1
            return f"{test_name}:{count}"
        else:
            return shortuuid.uuid()[:8]


@attr.s(auto_attribs=True)
class Event:
    lineno: int
    # offset and filename are always set, but we don't want to set them in tests, thus
    # giving them a default value.
    index: int = attr.ib(eq=False, default=0)
    offset: int = attr.ib(eq=False, default=0)
    filename: str = attr.ib(eq=False, default="")
    id: string = attr.ib(factory=UUIDGenerator.generate_uuid, eq=False, repr=False)

    @staticmethod
    def value_serializer(inst: type, field: attr.Attribute, value: Any):
        if field is None:
            return value
        if field.name == "sources":
            return sorted(source.name for source in value)
        if field.name == "target":
            return value.name
        return value


@attr.s(auto_attribs=True, eq=False)
class InitialValue(Event):
    """Identifiers already exist before tracking starts.

    e.g. Global variables, passed in arguments.

    This also counts:

    a = 1
    tracer.start()
    a = 2  --> emit two events: first InitialValue, then Binding.
    tracer.stop()

    Compared to this one, which only emits a Binding event.

    tracer.start()
    a = 2  # 'a' doesn't exist before.
    tracer.stop()
    '"""

    target: Symbol = attr.ib(kw_only=True)

    # kw_only is required to make inheritance work
    # see https://github.com/python-attrs/attrs/issues/38
    value: Any = attr.ib(kw_only=True)
    repr: str = ""

    def __eq__(self, other: InitialValue):
        return (
            isinstance(other, InitialValue)
            and (
                self.target,
                self.value,
                self.lineno,
            )
            == (other.target, other.value, other.lineno)
        )


@attr.s(auto_attribs=True, eq=False)
class Binding(Event):
    """An identifier is bound to an value.

    A brief explanation of Python's data model:
    http://foobarnbaz.com/2012/07/08/understanding-python-variables/

    Roughly speaking, Binding happens when:
        - A new identifier is used for the first time
        - An identifier is re-assigned
    """

    target: Symbol = attr.ib(kw_only=True)
    value: Any = attr.ib(kw_only=True)
    repr: str = ""
    sources: set[Symbol] = set()  # Source can be empty, like a = 1

    def __eq__(self, other: Binding):
        return (
            isinstance(other, Binding)
            and (
                self.target,
                self.value,
                self.sources,
                self.lineno,
            )
            == (other.target, other.value, other.sources, other.lineno)
        )


@attr.s(auto_attribs=True, eq=False)
class Mutation(Event):
    """An identifier is mutated.

    Note the difference between Mutation and Binding.

        a = 0       # Binding
        a = 1       # Binding, not Mutation!!
        b = []      # Binding
        b.append(1) # Mutation
        inst.foo()  # Mutation, though we should check whether it actually happened.
    """

    target: Symbol = attr.ib(kw_only=True)
    sources: set[Symbol] = set()  # Source can be empty, like a = 1
    value: Any = _dummy
    repr: str = ""

    def __eq__(self, other: Mutation):
        return (
            isinstance(other, Mutation)
            and (
                self.target,
                self.value,
                self.sources,
                self.lineno,
            )
            == (other.target, other.value, other.sources, other.lineno)
        )


@attr.s(auto_attribs=True, eq=False)
class Deletion(Event):
    """An identifier is deleted by `del`."""

    target: Symbol = attr.ib(kw_only=True)

    def __eq__(self, other: Deletion):
        return isinstance(other, Deletion) and (self.target, self.lineno) == (
            other.target,
            other.lineno,
        )


@attr.s(auto_attribs=True, eq=False)
class Return(Event):
    """Return from a callable.

    The return event, if exist, is always the last event of a frame.

    The return event does not have a "target" attr because there isn't always one, e.g.
    return 1 + 2, return a if b else c
    """

    value: Any = attr.ib(kw_only=True)
    repr: str = ""
    sources: set[Symbol] = set()

    def __eq__(self, other: Return):
        return isinstance(other, Return) and (self.value, self.sources) == (
            other.value,
            self.sources,
        )


@attr.s
class JumpBackToLoopStart(Event):
    """
    As the name suggests, this type of events represent a jump to loop start. Here,
    "jump back" means the offset of next instruction is smaller than the current one.
    In fact, in Python, the destination of a jump back is always a loop start.

    Not like other types of events, JumpBackToLoopStart is irrelevant to any identifier,
    nor is it showed on the trace graph. We need it to help track iterations of loops.
    See trace_graph.js for more information.
    """

    # The jump target's offset, which is guaranteed to be a loop start.
    jump_target: int = attr.ib(kw_only=True)


@attr.s
class Loop:
    start_offset: int = attr.ib(kw_only=True)
    end_offset: int = attr.ib(kw_only=True)
    start_lineno: int = attr.ib(kw_only=True)


"""
An edge case that is not handled:
x = a.b
x.foo = bar

a is also changed, but right now we won't be able to know it.
We need a Symbol class to handle this case, like: Symbol('x', references={'a'})

H: 其实我更多想的时，Symbol 可以引用别的 symbol
L: 引用别的 symbol 虽然或许可以让 backtracking 更简单，如果是引用所有相关 symbol 感觉有点滥用，引
   用一些局部（比如同一个 statement）的 symbol 应该是可以的
"""


class Symbol:
    """An identifier at a certain point of program execution.

    Symbols are specific to a frame. For symbols stored in value stack or representing a
    source, snapshot must be provided. For symbols only used for representing a target,
    snapshot can be omitted.
    """

    def __init__(self, name: str, snapshot: Optional[Snapshot] = None):
        self.name = name
        self.snapshot = snapshot

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        """Test only"""
        return self.name == other.name

    def __repr__(self):
        return f"Symbol('{self.name}')"
