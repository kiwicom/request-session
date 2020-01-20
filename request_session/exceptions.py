"""Module contains exceptions from requests and request_session."""
from typing import Any  # pylint: disable=unused-import

from requests.exceptions import ConnectionError  # pylint: disable=redefined-builtin
from requests.exceptions import HTTPError, ReadTimeout, RequestException
from requests.exceptions import Timeout as RequestTimeout


class InvalidUserAgentString(Exception):
    """Provided user agent string is not in correct format."""


class RequestSessionException(Exception):
    """Client error, server responded with 4xx code."""

    def __init__(self, *args, **kwargs):
        # type: (*Any, **Any) -> None
        self.original_exc = kwargs.get("original_exc")
        Exception.__init__(self, *args)
