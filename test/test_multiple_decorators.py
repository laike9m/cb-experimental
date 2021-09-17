from cyberbrain import Binding, Return, Symbol, InitialValue


def test_multiple_decorators(trace, mocked_responses):
    def my_decorator(f):
        def inner(*args):
            a = 1
            f(*args)
            b = a

        return inner

    @my_decorator
    @my_decorator
    @my_decorator
    @trace
    def original_function(number):
        a = [1, 2, 3]
        b = number

    original_function(1)

    assert trace.events == [
        Binding(
            lineno=18,
            target=Symbol("a"),
            value="[1,2,3]",
            repr="[1, 2, 3]",
            sources=set(),
        ),
        InitialValue(lineno=17, target=Symbol("number"), value="1", repr="1"),
        Binding(
            lineno=19,
            target=Symbol("b"),
            value="1",
            sources={Symbol("number")},
        ),
        Return(
            lineno=19,
            value="null",
            repr="None",
            sources=set(),
        ),
    ]
