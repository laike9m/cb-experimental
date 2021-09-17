from __future__ import annotations

import json
import msgpack
import os
import pytest
import responses
import attr

from cyberbrain import _TracerFSM, trace, Symbol
from utils import python_version, get_os_type


def pytest_addoption(parser):
    parser.addoption("--debug_mode", action="store_true", default=False)


@pytest.fixture(scope="function", name="tracer")
def fixture_tracer(request):
    trace.debug_mode = request.config.getoption("--debug_mode")

    yield trace

    # Do cleanup because the trace decorator is reused across tests.
    trace.raw_frame = None
    trace.decorated_function_code_id = None
    trace.frame_logger = None
    trace.tracer_state = _TracerFSM.INITIAL


@pytest.fixture(scope="function", name="trace")
def fixture_trace(request):
    trace.debug_mode = request.config.getoption("--debug_mode")

    yield trace

    # Do cleanup because the trace decorator is reused across tests.
    trace.raw_frame = None
    trace.decorated_function_code_id = None
    trace.frame_logger = None
    trace.tracer_state = _TracerFSM.INITIAL


@pytest.fixture(scope="function")
def check_tracer_events():
    def serialize_symbol(symbol):
        if symbol.snapshot is None:
            return {"name": symbol.name, "snapshot": symbol.snapshot}
        snapshot = {"location": symbol.snapshot.location, "events_pointer": symbol.snapshot.events_pointer}
        return {"name": symbol.name, "snapshot": snapshot}

    yield

    tracer_events = []
    for event in trace.events:
        # event_dict = attr.asdict(
        #     event,
        #     value_serializer=event.value_serializer,
        # )
        event_dict = attr.asdict(event)
        for key, val in event_dict.items():
            if type(val) == Symbol:
                event_dict[key] = serialize_symbol(val)
            elif type(val) == list and type(val[0]) == Symbol:
                event_dict[key] = sorted([serialize_symbol(sym) for sym in val], key=lambda x:x["name"])
        event_dict["__class__"] = event.__class__.__name__
        tracer_events.append(event_dict)

    # Generates golden data.
    golden_filepath = f"test/data/{python_version}/{trace.frame.frame_name}.json"
    directory = os.path.dirname(golden_filepath)
    if not os.path.exists(directory):
        os.makedirs(directory)

    if not os.path.exists(golden_filepath):
        with open(golden_filepath, "wt") as f:
            json.dump({"tracer.events": tracer_events}, f, ensure_ascii=False, indent=4)
        return

    # Assuming run in root directory.
    with open(golden_filepath, "rt") as f:
        golden_frame_data = json.loads(f.read())
    
    if golden_frame_data.get("tracer.events", None) is None:
        with open(golden_filepath, "wt") as f:
            golden_frame_data["tracer.events"] = tracer_events
            json.dump(golden_frame_data, f, ensure_ascii=False, indent=4)

    assert tracer_events == golden_frame_data["tracer.events"], json.dumps(tracer_events, indent=4)
    


@pytest.fixture
def mocked_responses(request):
    with responses.RequestsMock() as resp:
        resp.add(
            responses.POST,
            f"http://localhost:{trace.rpc_client.port}/frame",
            status=200,
            content_type="application/octet-stream",
        )
        yield resp

        frame_data = msgpack.unpackb(resp.calls[0].request.body)
        frame_name = frame_data["metadata"]["frame_name"]

        # Generates golden data.
        golden_filepath = f"test/data/{python_version}/{frame_name}.json"
        directory = os.path.dirname(golden_filepath)
        if not os.path.exists(directory):
            os.makedirs(directory)

        if not os.path.exists(golden_filepath):
            with open(golden_filepath, "wt") as f:
                json.dump({"response": frame_data}, f, ensure_ascii=False, indent=4)
            return

        # Assuming run in root directory.
        with open(golden_filepath, "rt") as f:
            golden_frame_data = json.loads(f.read())

        # Don't check request body on Windows because it has a different format.
        if get_os_type() == "windows" and frame_name in {"test_numpy", "test_pandas"}:
            return
    
        if golden_frame_data.get("response", None) is None:
            with open(golden_filepath, "wt") as f:
                golden_frame_data["response"] = frame_data
                json.dump(golden_frame_data, f, ensure_ascii=False, indent=4)

        assert frame_data == golden_frame_data["response"], json.dumps(frame_data, indent=4)
