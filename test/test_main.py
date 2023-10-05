import os
from py_huff.compile import compile


def compile_test(fp: str, expected_deploy: str, expected_runtime: str):
    # Resolve relative path
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), fp)
    result = compile(path)
    assert result.deploy.hex() == expected_deploy, 'Deploy code failed to match'
    assert result.runtime.hex() == expected_runtime, 'Runtime code failed to match'


def test_simple():
    compile_test(
        fp='../examples/single_main.huff',
        expected_deploy='600d8060095f395ff3600362017389015f5260205ff3',
        expected_runtime='600362017389015f5260205ff3'
    )


def test_single_macro():
    compile_test(
        fp='../examples/single_macro.huff',
        expected_deploy='600b8060095f395ff35f35602035015952595ff3',
        expected_runtime='5f35602035015952595ff3'
    )


def test_simple_labels():
    compile_test(
        fp='../examples/simple_labels.huff',
        expected_deploy='60238060095f395ff35f35600180600c5760205ff35b5f915b91810190916001900380600f57915f52595ff3',
        expected_runtime='5f35600180600c5760205ff35b5f915b91810190916001900380600f57915f52595ff3'

    )


def test_macro_args():
    compile_test(
        fp='../examples/macro_args.huff',
        expected_deploy='60278060095f395ff36040355f35602035908101818110602357905090810381811160235790505952595ff35b5f5ffd',
        expected_runtime='6040355f35602035908101818110602357905090810381811160235790505952595ff35b5f5ffd'
    )


def test_const_ref():
    compile_test(
        fp='../examples/const_ref.huff',
        expected_deploy='60048060095f395ff360826082',
        expected_runtime='60826082'
    )
