import pytest

from cyberbrain import Binding, InitialValue, Symbol, Mutation  # noqa


def test_call_method_type_error(trace, mocked_responses):
    @trace
    def call_method_type_error():
        s = "hello world"
        assert s.split() == ["hello", "world"]
        with pytest.raises(TypeError):
            s.split(2)

    call_method_type_error()


def test_binary_op_zero_division(trace, mocked_responses):
    @trace
    def binary_op_zero_division():
        with pytest.raises(ZeroDivisionError):
            a = 1 / 0

    binary_op_zero_division()


def test_store_subscr_type_error(trace, mocked_responses):
    @trace
    def store_subscr_type_error():
        with pytest.raises(TypeError):
            a = ()
            a[0] = 1

    store_subscr_type_error()


def test_delete_subscr_type_error(trace, mocked_responses):
    @trace
    def delete_subscr_type_error():
        with pytest.raises(TypeError):
            a = (0,)
            del a[0]

    delete_subscr_type_error()


def test_import_error(trace, mocked_responses):
    @trace
    def import_error():
        with pytest.raises(ImportError):
            import xxx  # noqa, IMPORT_NAME

        with pytest.raises(ImportError):
            from os import xxx  # noqa, IMPORT_FROM

    import_error()


def test_name_error(trace, mocked_responses):
    @trace
    def name_error():
        with pytest.raises(NameError):
            del a  # DELETE_FAST

        with pytest.raises(NameError):
            print(a)  # LOAD_FAST

    name_error()


def test_attribute_error(trace, mocked_responses):
    @trace
    def attribute_error():
        with pytest.raises(AttributeError):
            a = 1
            a.x = 1  # STORE_ATTR

        with pytest.raises(AttributeError):
            del a.x  # DELETE_ATTR

        with pytest.raises(AttributeError):
            print(a.x)  # LOAD_ATTR

        with pytest.raises(AttributeError):
            print(a.x())  # LOAD_METHOD

    attribute_error()


def test_build_set_type_error(trace, mocked_responses):
    @trace
    def build_set_type_error():
        with pytest.raises(TypeError):
            a = {{}}

    build_set_type_error()


def test_build_map_type_error(trace, mocked_responses):
    @trace
    def build_map_type_error():
        with pytest.raises(TypeError):
            a = {[1]: 1}

    build_map_type_error()


def test_unpack_type_error(trace, mocked_responses):
    """
    For <3.9 it's
        BUILD_TUPLE_UNPACK[_WITH_CALL],
        BUILD_LIST_UNPACK,
        BUILD_SET_UNPACK,
        BUILD_MAP_UNPACK[_WITH_CALL]

    for >=3.9 it's LIST_EXTEND, SET_UPDATE, DICT_UPDATE, DICT_MERGE
    See test_unpack.py
    """

    def f(*args, **kwargs):
        pass

    @trace
    def unpack_type_error():
        with pytest.raises(ValueError):
            a, b, c = "hi"  # UNPACK_SEQUENCE

        with pytest.raises(TypeError):
            a, *c = 1  # UNPACK_EX

        with pytest.raises(TypeError):
            a = *1, *2

        with pytest.raises(TypeError):
            f(*1, *2)

        with pytest.raises(TypeError):
            a = [*1, *2]

        with pytest.raises(TypeError):
            a = {*1, *2}

        with pytest.raises(TypeError):
            a = {**1, **2}

        with pytest.raises(TypeError):
            f(**1, **2)

    unpack_type_error()


def test_format_value_error(trace, mocked_responses):
    class A:
        def __str__(self):
            raise RuntimeError("ooo")

    @trace
    def format_value_error():
        with pytest.raises(RuntimeError):
            a = A()
            print(f"{a}")  # FORMAT_VALUE

    format_value_error()


def test_get_iter_type_error(trace, mocked_responses):
    @trace
    def get_iter_type_error():
        with pytest.raises(TypeError):
            for _ in 1:
                pass  # GET_ITER

    get_iter_type_error()


def test_for_iter_error(trace, mocked_responses):
    class A:
        def __iter__(self):
            return self

        def __next__(self):
            raise RuntimeError

    @trace
    def for_iter_error():
        with pytest.raises(RuntimeError):
            for _ in A():  # FOR_ITER
                pass

        for _ in range(3):
            pass

    for_iter_error()


def test_setup_with_error(trace, mocked_responses):
    @trace
    def setup_with_error():
        with pytest.raises(AttributeError):
            with 1:  # SETUP_WITH
                pass

    setup_with_error()


def test_with_cleanup_start_error(trace, mocked_responses):
    class A:
        def __enter__(self):
            pass

        def __exit__(self, exc_type, exc_val, exc_tb):
            raise RuntimeError

    @trace
    def with_cleanup_start_error():
        with pytest.raises(RuntimeError):
            with A():  # <=3.9: WITH_CLEANUP_START, >3.9: CALL_FUNCTION
                pass

    with_cleanup_start_error()


def test_unbound_local_error(trace, mocked_responses):
    @trace
    def unbound_local_error():
        with pytest.raises(UnboundLocalError):
            print(a)
            a = 1

    unbound_local_error()
