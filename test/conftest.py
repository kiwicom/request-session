"""Just a conftest."""
from typing import Any, Callable

import httpbin as Httpbin
import pytest

from request_session import RequestSession


@pytest.fixture(scope="function")
def request_session(httpbin):
    # type: (Httpbin) -> Callable
    def inner(*args, **kwargs):
        # type: (*Any, **Any) -> RequestSession
        return RequestSession(  # type: ignore
            *args, host=httpbin.url, request_category="test", **kwargs
        )

    return inner
