import os
from py_huff.compile import compile


def compile_test(
    fp: str,
    expected_deploy: str,
    expected_runtime: str,
    constant_overrides=None
):
    if constant_overrides is None:
        constant_overrides = {}
    # Resolve relative path
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), fp)
    result = compile(path, constant_overrides, False)
    assert result.deploy.hex() == expected_deploy.strip(), 'Deploy code failed to match'
    assert result.runtime.hex() == expected_runtime.strip(), 'Runtime code failed to match'


def test_simple():
    compile_test(
        fp='../examples/single_main.huff',
        expected_deploy='6c600362017389015f5260205ff35f52600d6013f3',
        expected_runtime=' 600362017389015f5260205ff3'
    )


def test_single_macro():
    compile_test(
        fp='../examples/single_macro.huff',
        expected_deploy='6a5f35602035015952595ff35f52600b6015f3',
        expected_runtime=' 5f35602035015952595ff3'
    )


def test_simple_labels():
    compile_test(
        fp='../examples/simple_labels.huff',
        expected_deploy='60238060095f395ff35f35600181600c5760205ff35b5f915b91810190916001900380600f57915f52595ff3',
        expected_runtime='                 5f35600181600c5760205ff35b5f915b91810190916001900380600f57915f52595ff3'

    )


def test_macro_args():
    compile_test(
        fp='../examples/macro_args.huff',
        expected_deploy='60278060095f395ff36040355f35602035908101818110602357905090810381811160235790505952595ff35b5f5ffd',
        expected_runtime='                 6040355f35602035908101818110602357905090810381811160235790505952595ff35b5f5ffd'
    )


def test_const_ref():
    compile_test(
        fp='../examples/const_ref.huff',
        expected_deploy='63608260825f526004601cf3',
        expected_runtime='60826082'
    )


def test_deep_args():
    compile_test(
        fp='../examples/deep_arg.huff',
        expected_deploy='656005565b5b5b5f526006601af3',
        expected_runtime='6005565b5b5b'
    )


def test_simple_adjust():
    compile_test(
        fp='../examples/simple_adjust.huff', expected_deploy='61010480600a5f395ff36003565b00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000',
        expected_runtime='6003565b00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'

    )


def test_includes():
    compile_test(
        fp='../examples/including.huff',
        expected_deploy='66010103621234565f5260076019f3',
        expected_runtime=' 01010362123456'
    )


def test_functions():
    compile_test(
        fp='../examples/functions.huff',
        expected_deploy='77630dbe671f63cd580ff363ea11c61d63c593ffcf628a99f35f5260186008f3',
        expected_runtime=' 630dbe671f63cd580ff363ea11c61d63c593ffcf628a99f3'
    )


def test_events():
    compile_test(
        fp='../examples/events.huff', expected_deploy='60638060095f395ff37fddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef7f884edad9ce6fa2440d8a54cc123490eb96d2768479d49ff9c7366125a94243647f76fae7629f203ffe0facce0a6c4be1a3f7a1c29f37a5c3907738f3b5f9ab93bc',

        expected_runtime='7fddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef7f884edad9ce6fa2440d8a54cc123490eb96d2768479d49ff9c7366125a94243647f76fae7629f203ffe0facce0a6c4be1a3f7a1c29f37a5c3907738f3b5f9ab93bc'
    )


def test_return_runtime_built_in():
    compile_test(
        fp='../examples/small_constructor.huff',
        expected_deploy='600c8060095f395ff36020355f35015f5260205ff3',
        expected_runtime='                 6020355f35015f5260205ff3'
    )


def test_runtime_code_built_in():
    compile_test(
        fp='../examples/runtime_code_built_in.huff',
        expected_deploy='60018060095f395ff300',
        expected_runtime='00'
    )


def test_free_storage_pointer():
    compile_test(
        fp='../examples/free_storage_pointer.huff',
        expected_deploy='645f600160025f526005601bf3',
        expected_runtime=' 5f60016002'
    )
