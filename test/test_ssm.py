import inspect
import os

import boto3
import pytest
from moto import mock_ssm

from ssmenv import SSMEnv, ssmenv


@mock_ssm
@pytest.mark.parametrize(
    "ssm_name_prefix,ssm_value,parameter_type",
    [
        ("/service/org.example.microservice", "1", "String"),
        ("/service/ORG.EXAMPLE.MICROSERVICE", "1", "String"),
        ("/service/ORG-EXAMPLE-MICROSERVICE", "1", "String"),
        ("/service/org-EXAMPLE.microservice", "1", "String"),
        ("/service/org.example.microservice", "1", "SecureString"),
        ("/service/ORG.EXAMPLE.MICROSERVICE", "1", "SecureString"),
        ("/service/ORG-EXAMPLE-MICROSERVICE", "1", "SecureString"),
        ("/service/org-EXAMPLE.microservice", "1", "SecureString"),
    ],
)
def test_it_returns_single_parameter(ssm_name_prefix, ssm_value, parameter_type):
    ssm = boto3.client("ssm")
    ssm.put_parameter(
        Name=ssm_name_prefix + "/debug", Value=ssm_value, Type=parameter_type
    )

    ssm_env = SSMEnv((ssm_name_prefix,))
    assert ssm_env["SERVICE_ORG_EXAMPLE_MICROSERVICE_DEBUG"] == "1"

    param = ssm.get_parameter(Name=ssm_name_prefix + "/debug")
    assert param["Parameter"]["Version"] == 1

    ssm.delete_parameter(Name=ssm_name_prefix)


@mock_ssm
def test_it_returns_multiple_parameters_from_different_namespaces():
    ssm = boto3.client("ssm")
    ssm.put_parameter(Name="/service/my-service/debug", Value="1", Type="String")
    ssm.put_parameter(
        Name="/resource/dynamodb/host", Value="https://example.org", Type="String"
    )

    ssm_env = SSMEnv(("/service/my-service", "/resource/dynamodb"))

    assert ssm_env["SERVICE_MY_SERVICE_DEBUG"] == "1"
    assert ssm_env["RESOURCE_DYNAMODB_HOST"] == "https://example.org"


@mock_ssm
def test_it_allows_to_pass_include_argument_as_string():
    ssm = boto3.client("ssm")
    ssm.put_parameter(Name="/service/my-service/debug", Value="1", Type="String")

    ssm_env = SSMEnv("/service/my-service")

    assert ssm_env["SERVICE_MY_SERVICE_DEBUG"] == "1"


@mock_ssm
def test_it_allows_to_iterate_over_all_parameters():
    ssm = boto3.client("ssm")
    ssm.put_parameter(
        Name="/service/my-service-first/first", Value="first-value", Type="String"
    )
    ssm.put_parameter(
        Name="/service/my-service-first/second", Value="second-value", Type="String"
    )
    ssm.put_parameter(
        Name="/service/my-service-second/first", Value="first-value", Type="String"
    )

    ssm_env = SSMEnv(("/service/my-service-first", "/service/my-service-second"))

    assert list(ssm_env.keys()) == [
        "SERVICE_MY_SERVICE_FIRST_FIRST",
        "SERVICE_MY_SERVICE_FIRST_SECOND",
        "SERVICE_MY_SERVICE_SECOND_FIRST",
    ]
    assert list(ssm_env.values()) == ["first-value", "second-value", "first-value"]


@mock_ssm
def test_it_allows_to_populate_os_environ():
    ssm = boto3.client("ssm")
    ssm.put_parameter(
        Name="/service/my-service/first", Value="first-value", Type="String"
    )

    os.environ = {**os.environ, **SSMEnv(("/service/my-service",))}

    assert os.environ["SERVICE_MY_SERVICE_FIRST"] == "first-value"


@mock_ssm
def test_it_removes_prefixes():
    ssm = boto3.client("ssm")
    ssm.put_parameter(
        Name="/service/my-service/first", Value="first-value", Type="String"
    )

    ssm_env = SSMEnv(("/service/my-service",), prefixes=("/service/my-service",))

    assert ssm_env["FIRST"] == "first-value"


def test_it_returns_default_dict_if_no_aws():
    ssm_env = SSMEnv(
        ("/service/my-service",), no_aws_default={"SERVICE_MY_SERVICE_DEBUG": "1"}
    )

    assert ssm_env["SERVICE_MY_SERVICE_DEBUG"] == "1"


@mock_ssm
def test_it_works_as_decorator_for_lambda_function():
    class MockContext:
        pass

    ssm = boto3.client("ssm")
    ssm.put_parameter(
        Name="/service/my-service/first", Value="first-value", Type="String"
    )

    _ssmenv = ssmenv("/service/my-service")

    @_ssmenv
    def handler(event, context):
        assert "SERVICE_MY_SERVICE_FIRST" in context.params
        assert context.params["SERVICE_MY_SERVICE_FIRST"] == "first-value"

    # Make sure that SSMEnv is initialised only once, which means that until lambda function is warm
    # data from AWS is fetch only once
    handler({}, MockContext())
    info = inspect.getclosurevars(_ssmenv)
    first_call = info.nonlocals["lambda_ssmenv"]

    handler({}, MockContext())
    info = inspect.getclosurevars(_ssmenv)
    second_call = info.nonlocals["lambda_ssmenv"]

    assert first_call is second_call
