import functools
import os
import re
from collections import UserDict

import boto3

__version__ = "1.4.0"


class SSMEnv(UserDict):
    def __init__(self, include, prefixes=None, ssm_client=None, no_aws_default=None):
        self._include = (include,) if type(include) == str else include
        self._prefixes = prefixes
        self._ssm_client = ssm_client
        self._no_aws_default = no_aws_default

        super().__init__(self._load())

    def _load(self):
        if self._no_aws_default and not any(
            (
                os.environ.get("AWS_ACCESS_KEY_ID"),
                os.environ.get("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"),
            )
        ):
            return self._no_aws_default

        ssm = self._ssm_client or boto3.client("ssm")

        parameters = {}
        for namespace in self._include:
            params = []
            next_token = -1
            while next_token != 0:
                search_params = {
                    "Path": namespace,
                    "WithDecryption": True,
                    "Recursive": True,
                }

                if next_token != -1:
                    search_params["NextToken"] = next_token

                current_set = ssm.get_parameters_by_path(**search_params)
                params += current_set.get("Parameters")
                next_token = current_set.get("NextToken", 0)

            for param in params:
                name = self._normalize_name(self._remove_prefixes(param.get("Name")))
                parameters[name] = param.get("Value")

        return parameters

    def _remove_prefixes(self, name):
        if not self._prefixes:
            return name

        for prefix in self._prefixes:
            if name.startswith(prefix):
                name = name.replace(prefix, "")

        return name

    def _normalize_name(self, name):
        return re.sub(r"\W", "_", name).upper().strip("_")


_lambda_ssmenv = None


def ssmenv(*args, **kwargs):
    def wrapper_wrapper(handler):
        @functools.wraps(handler)
        def wrapper(event, context):
            if not hasattr(context, "params"):
                context.params = {}

            global _lambda_ssmenv
            if not _lambda_ssmenv:
                _lambda_ssmenv = SSMEnv(*args, **kwargs)
            context.params = (
                _lambda_ssmenv if _lambda_ssmenv else SSMEnv(*args, **kwargs)
            )

            return handler(event, context)

        return wrapper

    return wrapper_wrapper
