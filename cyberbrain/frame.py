from __future__ import annotations

import dis
from collections import defaultdict
from dis import Instruction

import os
from types import FrameType
from typing import Any

from . import value_stack, utils
from .basis import (
    Event,
    InitialValue,
    Binding,
    Mutation,
    Deletion,
    Return,
    Symbol,
    Loop,
    ExceptionInfo,
    JumpBackToLoopStart,
)

_INITIAL_STATE = -1

Identifier = str  # Just a type alias to make annotations more expressive.


class _EventsDict(defaultdict):
    def __contains__(self, name):
        events = self[name]
        if not events:
            return False

        if isinstance(events[-1], Deletion):
            # If last event is a deletion, the name should be considered non-existent.
            return False

        return True


class Frame:
    """Stores frame state events and checkpoints.

    Two major functionalities this class provide:
    1. Tells the value of an identifier given a code location.
    2. Easier back tracing.

    TODO: corner cases to be handled:
        - delete, then create again

    Whether we still need identifier_to_events is yet to be decided.
    """

    def __init__(self, raw_frame: FrameType):
        # ################### Read-only attributes ####################
        # Only stores the basename so it's consistent on all operating systems.
        # This is mainly for the ease of testing.
        self.filename: str = utils.shorten_path(
            raw_frame.f_code.co_filename, 1 if utils.run_in_test() else 3
        )
        self.frame_name: str = (
            # Use filename as frame name if code is run at module level.
            os.path.basename(raw_frame.f_code.co_filename).rstrip(".py")
            if raw_frame.f_code.co_name == "<module>"
            else raw_frame.f_code.co_name
        )
        # For now, use frame name as frame id. Eventually this should be a unique uuid.
        self.frame_id: str = self.frame_name
        self.defined_lineno: int = raw_frame.f_code.co_firstlineno
        self.instructions: dict[int, Instruction] = {
            instr.offset: instr for instr in dis.get_instructions(raw_frame.f_code)
        }
        self.offset_to_lineno: dict[int, int] = utils.map_bytecode_offset_to_lineno(
            raw_frame
        )
        self.parameters: Set[str] = utils.get_parameters(raw_frame)

        # ################### Mutable state ####################
        self.value_stack: value_stack.BaseValueStack = value_stack.create_value_stack()
        self.events: list[Event] = []
        self.identifier_to_events: dict[Identifier, list[Event]] = _EventsDict(list)
        self.snapshots: list[Snapshot] = [
            # The initial state, where pointer points to zero for every identifier.
            Snapshot(events_pointer=defaultdict(lambda: _INITIAL_STATE))
        ]
        self._latest_snapshot = self.snapshots[0]
        self.loops: dict[int, Loop] = {}  # Maps loop start to loop.

        # ################### Relevant frames ####################
        # Frame that generated this frame. Could be empty if this frame is the outermost
        # frame.
        self.parent: Optional[Frame] = None
        # Frames derived from this frame.
        self.children: list[Frame] = []

    @property
    def metadata(self):
        """Frame metadata sent to rpc server

        More fields to add:
        - int64 start_lineno  // Start line of the frame in filename.
        - int64 end_lineno  // End line of the frame in filename.
        - string callsite_filename  // The file from which the frame is entered.
        - int64 callsite_lineno  // The line where the callable that generates the frame
                                 // is called.
        - string arguments  // Arguments stringified. f(1, b=2) -> "1, b=2"
        """
        return {
            "frame_id": self.frame_id,
            # Ideally the qualified name, at least use callable's name.
            "frame_name": self.frame_name,
            "filename": self.filename,
            "defined_lineno": self.defined_lineno,
        }

    @property
    def latest_snapshot(self):
        return self._latest_snapshot

    def log_return_event(self, frame: FrameType, value: Any):
        instr = self.instructions[frame.f_lasti]

        # Generator related instructions (e.g. YIELD_VALUE) can also trigger a return
        # event. Ignore them for now.
        if instr.opname != "RETURN_VALUE":
            return

        # There should be one and only one item left on the stack before return.
        assert self.value_stack.stack_level == 1

        self.events.append(
            Return(
                value=utils.to_json(value),
                repr=utils.get_repr(value),
                lineno=self.offset_to_lineno[frame.f_lasti],
                filename=self.filename,
                offset=frame.f_lasti,
                sources=set(utils.flatten(self.value_stack._pop())),
                index=len(self.events),
            )
        )

    def log_initial_value_events(self, frame: FrameType, instr: Instruction):
        # We must use instr.argrepr instead of instr.argval. Example:
        # x = "hello"
        # Instruction(opname='LOAD_CONST', argval='hello', argrepr="'hello'")
        # Note argval is 'hello', which can collide with identifier names in frame.
        target: str = instr.argrepr
        try:
            value = utils.get_value_from_frame(target, frame)
        except AssertionError:
            # The target name may not yet exist in the frame.
            value = None

        if utils.should_ignore_event(target=target, value=value, frame=frame):
            return

        # TODO(#124): Use more accurate function definition lineno. Besides that,
        #   it would be better if we can find the lineno of each parameter,
        #   since they may exist on different lines.

        # Set the lineno to -1 for global or enclosing vars, because we don't know
        # their exact lineno. This will disable highlighting when users hovering on
        # nodes of these variables.
        lineno = self.defined_lineno if target in self.parameters else -1

        # Logs InitialValue event if it hasn't been recorded yet.
        if utils.name_exist_in_frame(target, frame) and not self._knows(target):
            value = utils.get_value_from_frame(target, frame)
            self._add_new_event(
                InitialValue(
                    target=Symbol(target),
                    value=utils.to_json(value),
                    repr=utils.get_repr(value),
                    lineno=lineno,
                    filename=self.filename,
                    offset=instr.offset,
                )
            )

    def log_events(
        self,
        frame: FrameType,
        instr: Instruction,
        jumped: bool,
        exc_info: ExceptionInfo,
    ):
        """Logs changed values by the given instruction, if any."""
        event_info = self.value_stack.emit_event_and_update_stack(
            instr=instr,
            frame=frame,
            jumped=jumped,
            exc_info=exc_info,
            snapshot=self.latest_snapshot,
        )
        if not event_info:
            return

        target: Symbol = event_info.target

        if target and target == Symbol("random"):
            print(event_info)

        if event_info.type is Mutation:
            value = utils.get_value_from_frame(target.name, frame)
            json = utils.to_json(value)
            if self._latest_value_of(target.name) == json:
                return

            self._add_new_event(
                Mutation(
                    target=target,
                    value=json,
                    repr=utils.get_repr(value),
                    filename=self.filename,
                    lineno=self.offset_to_lineno[instr.offset],
                    sources=event_info.sources,
                    offset=instr.offset,
                )
            )
        elif event_info.type is Binding:
            value = utils.get_value_from_frame(target.name, frame)
            self._add_new_event(
                Binding(
                    target=target,
                    value=utils.to_json(value),
                    repr=utils.get_repr(value),
                    sources=event_info.sources,
                    filename=self.filename,
                    lineno=event_info.lineno,
                    offset=instr.offset,
                )
            )
        elif event_info.type is Deletion:
            self._add_new_event(
                Deletion(
                    target=target,
                    filename=self.filename,
                    lineno=self.offset_to_lineno[instr.offset],
                    offset=instr.offset,
                )
            )
        elif event_info.type is JumpBackToLoopStart:
            loop_start = event_info.jump_target
            self.events.append(
                JumpBackToLoopStart(
                    filename=self.filename,
                    lineno=self.offset_to_lineno[instr.offset],
                    offset=instr.offset,
                    index=len(self.events),
                    jump_target=loop_start,
                )
            )
            if loop_start in self.loops:
                self.loops[loop_start].end_offset = max(
                    self.loops[loop_start].end_offset, instr.offset
                )
            else:
                self.loops[loop_start] = Loop(
                    start_offset=loop_start,
                    end_offset=instr.offset,
                    start_lineno=self.offset_to_lineno[loop_start],
                )

    def _add_new_event(self, event: Event):
        target = event.target.name
        assert not (
            self.identifier_to_events[target] and isinstance(event, InitialValue)
        ), "InitialValue shouldn't be added twice"
        self.identifier_to_events[target].append(event)
        event.index = len(self.events)
        self.events.append(event)

        # Creates a new snapshot by incrementing the target index.
        new_events_pointer = self.snapshots[-1].events_pointer.copy()
        new_events_pointer[target] += 1
        new_snapshot = Snapshot(events_pointer=new_events_pointer)
        self._latest_snapshot = new_snapshot
        self.snapshots.append(new_snapshot)

        # If event is a mutation, updates relevant snapshots in value stack.
        if isinstance(event, Mutation):
            self.value_stack.update_snapshot(event.target.name, self.latest_snapshot)

    def _knows(self, name: str) -> bool:
        return name in self.identifier_to_events

    def _latest_value_of(self, name: str) -> Any:
        """Returns the latest value of an identifier.

        This method is *only* used during the logging process.
        TODO: What if the last event is a Deletion?
        """
        if not self._knows(name):
            raise AttributeError(f"'{name}' does not exist in frame.")

        return self.identifier_to_events[name][-1].value


class Snapshot:
    """Represents a frame's state at a certain moment.

    Given an event, Snapshot can help you find other variable's value at the same
    point of program execution.
    e.g. What's `b`'s value when `a` is set to 1
    """

    # TODO: Snapshot should contain, but not keyed by code location, because code
    #  location can duplicate.

    __slots__ = ["events_pointer", "location"]

    def __init__(self, events_pointer, location=None):
        self.location = location
        self.events_pointer: dict[str, int] = events_pointer

    def __repr__(self):
        return repr(self.events_pointer)
