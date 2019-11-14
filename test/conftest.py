"""Just a conftest."""
import pytest

from kw.request_session import RequestSession


@pytest.fixture(scope="function")
def request_session(httpbin):
    def inner(*args, **kwargs):
        return RequestSession(
            *args, host=httpbin.url, request_category="test", **kwargs
        )

    return inner
