from cyberbrain import InitialValue, Binding, Symbol


def test_mutation(tracer, mocked_responses):
    text = "AAAA"

    tracer.start()

    lower_text = text.lower()  # Test this line does not emit a mutation of `text`.

    tracer.stop()

    assert tracer.events == [
        InitialValue(
            lineno=-1,
            target=Symbol("text"),
            value='"AAAA"',
            repr='"AAAA"',
        ),
        Binding(
            lineno=9,
            target=Symbol("lower_text"),
            value='"aaaa"',
            repr='"aaaa"',
            sources={Symbol("text")},
        ),
    ]
