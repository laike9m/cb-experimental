from cyberbrain import Binding, InitialValue, Symbol  # noqa


def test_assertion(tracer, mocked_responses):
    tracer.start()
    try:
        assert False  # LOAD_ASSERTION_ERROR
    except AssertionError:
        pass
    tracer.stop()

    assert tracer.events == []
