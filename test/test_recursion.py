from cyberbrain import Symbol, InitialValue, Return


def test_recursion_decorator(trace, mocked_responses):
    @trace
    def fib(n):
        if n <= 1:
            return n
        else:
            return fib(n - 1) + fib(n - 2)

    print(fib(3))

    assert trace.events == [
        InitialValue(
            lineno=6,
            target=Symbol("n"),
            value="3",
            repr="3",
        ),
        InitialValue(
            lineno=-1,
            target=Symbol("fib"),
            value='{"repr": "<function test_recursion_decorator.<locals>.fib>"}',
            repr="<function test_recursion_decorator.<locals>.fib>",
        ),
        Return(
            lineno=10,
            value="2",
            repr="2",
            sources={Symbol("fib"), Symbol("n")},
        ),
    ]


def test_recursion_tracer(tracer, mocked_responses):
    def fib(n):
        return n if n <= 1 else fib(n - 1) + fib(n - 2)

    # tracer.stop can't be placed inside fib, because it will be called first by inner
    # calls. And tracer.start() has to be called in the same frame as tracer.stop().
    tracer.start()
    print(fib(3))
    tracer.stop()

    assert tracer.events == [
        InitialValue(
            lineno=-1,
            target=Symbol("fib"),
            value='{"repr": "<function test_recursion_tracer.<locals>.fib>"}',
            repr="<function test_recursion_tracer.<locals>.fib>",
        )
    ]
