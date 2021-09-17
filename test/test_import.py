from hamcrest import *

from cyberbrain import Binding, Symbol


def test_import(tracer, mocked_responses):
    tracer.start()

    import os  # IMPORT_NAME
    from os import path  # IMPORT_FROM, loads module
    from sys import settrace  # IMPORT_FROM, loads function

    tracer.stop()

    print(os, path, settrace)  # Prevent PyCharm from removing unused imports.

    assert_that(
        tracer.events,
        contains_exactly(
            all_of(
                instance_of(Binding),
                has_properties(
                    {
                        "target": Symbol("os"),
                        "value": contains_string("<module 'os'"),
                        "sources": set(),
                        "lineno": 9,
                    }
                ),
            ),
            all_of(
                instance_of(Binding),
                has_properties(
                    {
                        "target": Symbol("path"),
                        "value": all_of(
                            contains_string("<module"), contains_string("path")
                        ),
                        "sources": set(),
                        "lineno": 10,
                    }
                ),
            ),
            all_of(
                instance_of(Binding),
                has_properties(
                    {
                        "target": Symbol("settrace"),
                        "value": '{"repr": "<built-in function settrace>"}',
                        "sources": set(),
                        "lineno": 11,
                    }
                ),
            ),
        ),
    )

    # We don't test GetFrame here, because event contains file path like
    # "\"<module \'os\' from \'/Users/laike9m/3.8.0/lib/python3.8/os.py\'>\""
    # Which doesn't work across different Python versions & test machines.
