"""Test the main module."""
import itertools
import sys
from typing import Any, Callable, Dict, Iterator, List, Union

import httpbin as Httpbin
import pytest
import requests
import simplejson as json

from request_session import RequestSession, UserAgentComponents
from request_session.exceptions import (
    HTTPError,
    InvalidUserAgentString,
    RequestException,
    RequestSessionException,
)
from request_session.protocols import Ddtrace, SentryClient, Statsd

from ._compat import Mock

REQUEST_CATEGORY = "test"  # this request category must match the one in conftest
INTERNAL_ERROR_MSG = (
    "500 Server Error: INTERNAL SERVER ERROR for url: "
    "http://127.0.0.1:8080/status/500"
)
TIMEOUT_ERROR_MSG = (
    "408 Client Error: REQUEST TIMEOUT for url: http://127.0.0.1:8080/status/408"
)
DDTRACE_ERROR_MSG = "Ddtrace must be provided in order to report to datadog service."
USER_AGENT_ERROR_MSG = "Provided User-Agent string is not valid."


def test_init(mocker, httpbin):
    # type: (Mock, Httpbin) -> None
    """Test initialization of RequestSession."""
    mock_ddtrace = mocker.Mock(spec_set=Ddtrace)
    mock_tracing_config = dict()  # type: Dict[Any, Any]
    mock_ddtrace.config.get_from.return_value = mock_tracing_config

    session = RequestSession(
        host=httpbin.url,
        request_category=REQUEST_CATEGORY,
        max_retries=3,
        user_agent="UserAgent",
        ddtrace=mock_ddtrace,
        headers={},
        auth=("user", "passwd"),
    )
    assert session.host == httpbin.url
    assert session.request_category == REQUEST_CATEGORY
    assert session.max_retries == 3
    assert session.user_agent == "UserAgent"
    assert session.headers == {}
    assert session.auth == ("user", "passwd")


def test_correct_user_agent(request_session):
    # type: (Callable) -> None
    client = request_session(
        user_agent_components=UserAgentComponents(
            service_name="service_name",
            version="1.1",
            organization="Kiwi.com",
            environment="testing",
            sys_info="python 3.7",
        )
    )
    assert client.user_agent == "service_name/1.1 (Kiwi.com testing) python 3.7"


def test_user_agent_precedence(request_session):
    # type: (Callable) -> None
    client = request_session(
        user_agent="hardcoded_user_agent",
        user_agent_components=UserAgentComponents(
            service_name="service_name",
            version="1.1",
            organization="Kiwi.com",
            environment="testing",
            sys_info="python 3.7",
        ),
    )

    assert client.user_agent == "hardcoded_user_agent"


@pytest.mark.parametrize(
    "user_agent_components",
    [
        {
            "service_name": "",
            "version": "1.1",
            "org": "Kiwi.com",
            "env": "testing",
            "sys_info": "python 3.7",
        },
        {
            "service_name": "service_name",
            "version": "",
            "org": "Kiwi.com",
            "env": "testing",
            "sys_info": "python 3.7",
        },
        {
            "service_name": "service_name",
            "version": "1.1",
            "org": "",
            "env": "testing",
            "sys_info": "python 3.7",
        },
        {
            "service_name": "service_name",
            "version": "1.1",
            "org": "Kiwi.com",
            "env": "",
            "sys_info": "python 3.7",
        },
    ],
)
def test_incorrect_user_agent_components(request_session, user_agent_components):
    # type: (Callable, Dict) -> None
    with pytest.raises(InvalidUserAgentString, match=USER_AGENT_ERROR_MSG):
        request_session(
            user_agent_components=UserAgentComponents(
                service_name=user_agent_components["service_name"],
                version=user_agent_components["version"],
                organization=user_agent_components["org"],
                environment=user_agent_components["env"],
                sys_info=user_agent_components["sys_info"],
            )
        )


def test_remove_session(request_session):
    # type: (Callable) -> None
    session = RequestSession(host="https://kiwi.com")
    before = len(session.session_instances)
    session.remove_session()
    assert len(session.session_instances) == before - 1


def test_close_all_sessions():
    # type: () -> None
    session = RequestSession(host="https://kiwi.com")
    session.prepare_new_session()
    assert len(RequestSession.session_instances) >= 2
    RequestSession.close_all_sessions()
    assert not RequestSession.session_instances


@pytest.mark.parametrize(
    "method, path, expected_status",
    [
        ("get", "/status/200", 200),
        ("post", "/status/200", 200),
        ("put", "/status/200", 200),
        ("delete", "/status/200", 200),
        ("patch", "/status/200", 200),
    ],
)
def test_method(request_session, method, path, expected_status):
    # type: (Callable, str, str, int) -> None
    """Test calling specific method."""
    session = request_session()  # type: RequestSession
    assert getattr(session, method)(path=path).status_code == expected_status


@pytest.mark.parametrize(
    "status_code, raises",
    [
        (200, None),
        (404, RequestSessionException),
        (409, RequestSessionException),
        (500, HTTPError),
        (503, HTTPError),
        (505, HTTPError),
    ],
)
def test_raise_for_status(mocker, httpbin, status_code, raises):
    # type: (Mock, Httpbin, int, Exception) -> None
    """Test raising of an exception when rejected with 4xx."""
    session = RequestSession(host=httpbin.url, request_category=REQUEST_CATEGORY)
    mock_sys = mocker.patch("request_session.utils.sys", spec_set=sys)
    mock_sys.exc_info.return_value = (HTTPError, HTTPError(), "fake_traceback")
    if raises:
        with pytest.raises(raises):
            session.get(path="/status/{status_code}".format(status_code=status_code))

        if isinstance(raises, HTTPError):
            assert mock_sys.exc_info()[1].__sentry_source == "third_party"
            assert mock_sys.exc_info()[1].__sentry_pd_alert == "disabled"
    else:
        session.get(path="/status/{status_code}".format(status_code=status_code))


@pytest.mark.parametrize(
    "exceptions, max_retries, expected_call_count",
    [
        (itertools.cycle([requests.exceptions.ConnectionError("ECONNRESET")]), 0, 2),
        (itertools.cycle([requests.exceptions.ConnectionError("ECONNRESET")]), 1, 2),
        (itertools.cycle([requests.exceptions.ConnectionError("ECONNRESET")]), 2, 3),
        (
            itertools.cycle(
                [
                    requests.exceptions.ConnectionError("ECONNRESET"),
                    requests.exceptions.ConnectionError,
                ]
            ),
            0,
            2,
        ),
    ],
)
def test_econnreset_error(
    httpbin, mocker, exceptions, max_retries, expected_call_count
):
    # type: (Httpbin, Mock, Iterator[Exception], int, int) -> None
    used_sessions = []

    def _prepare_new_session(self):  # type: ignore
        self.session = mocker.Mock(spec=requests.Session)
        self.session_instances.append(self.session)
        self.session.request.side_effect = next(exceptions)

        used_sessions.append(self.session)

    client = RequestSession(
        host=httpbin.url, max_retries=max_retries, request_category=REQUEST_CATEGORY
    )
    mock_log = mocker.Mock(autospec=True)
    mock_exception_log_and_metrics = mocker.Mock(
        spec=RequestSession._exception_log_and_metrics
    )
    client.log = mock_log  # type: ignore
    client._exception_log_and_metrics = mock_exception_log_and_metrics  # type: ignore

    mocker.patch.object(
        RequestSession, "prepare_new_session", new=_prepare_new_session, spec_set=True
    )

    _prepare_new_session(client)

    with pytest.raises(RequestException):
        client.get("/status/500")
    actual_call_count = sum(session.request.call_count for session in used_sessions)

    mock_log.assert_called_with(
        "info", "{category}.session_replace".format(category=client.request_category)
    )
    assert mock_exception_log_and_metrics.call_count == 1
    assert actual_call_count == expected_call_count


@pytest.mark.parametrize(
    "inputs, expected",
    [
        (
            {"path": "/status/200", "tags": [], "max_retries": 10},
            {
                "exception": False,
                "call_count": 0,
                "request_params": {
                    "url": "",
                    "timeout": 10,
                    "verify": True,
                    "params": None,
                },
            },
        ),
        (
            {"path": "/status/500", "tags": [], "max_retries": 10},
            {
                "exception": HTTPError,
                "description": INTERNAL_ERROR_MSG,
                "call_count": 11,
                "error": "http_error",
                "request_params": {
                    "url": "",
                    "timeout": 10,
                    "verify": True,
                    "params": None,
                },
                "error_tags": [],
                "status_code": 500,
            },
        ),
        (
            {"path": "/status/408", "tags": [], "max_retries": 10},
            {
                "exception": HTTPError,
                "description": TIMEOUT_ERROR_MSG,
                "call_count": 11,
                "error": "http_error",
                "request_params": {
                    "url": "",
                    "timeout": 10,
                    "verify": True,
                    "params": None,
                },
                "error_tags": [],
                "status_code": 408,
            },
        ),
    ],
)
def test_logging(mocker, request_session, inputs, expected):
    # type: (Mock, Callable, Dict[str, Any], Dict[str, Any]) -> None
    mock_exception_log_and_metrics = mocker.Mock(
        spec_set=RequestSession._exception_log_and_metrics
    )
    client = request_session(max_retries=inputs["max_retries"])
    client._exception_log_and_metrics = mock_exception_log_and_metrics
    expected["request_params"]["url"] = "{}{}".format(client.host, inputs["path"])

    calls = []
    for attempt in range(1, expected["call_count"] + 1):
        calls.append(
            mocker.call(
                error=expected["exception"](expected["description"]),
                request_category=client._get_request_category(),
                request_params=expected["request_params"],
                dd_tags=expected["error_tags"],
                status_code=expected["status_code"],
                attempt=attempt,
            )
        )

    if expected["exception"]:
        with pytest.raises(expected["exception"]):
            client.get(path=inputs["path"], tags=inputs["tags"])
    else:
        client.get(path=inputs["path"], tags=inputs["tags"])

    assert mock_exception_log_and_metrics.call_count == expected["call_count"]
    # compare everything manually because exceptions cannot be compared directly
    # with mock.assert_has_calls
    for mock, actual in zip(calls, mock_exception_log_and_metrics.mock_calls):
        for key, value in actual[2].items():
            if key == "error":
                assert type(mock[2][key]) is type(value)
                assert mock[2][key].args == value.args
            else:
                assert mock[2][key] == value


@pytest.mark.parametrize(
    "path, max_retries, status, error, call_count",
    [
        ("/status/200", 0, "success", None, 1),
        ("/status/408", 5, "error", "http_error", 6),
        ("/status/500", 0, "error", "http_error", 1),
        ("/status/500", 1, "error", "http_error", 2),
    ],
)
def test_metric_increment(
    mocker, request_session, path, max_retries, status, error, call_count
):
    # type: (Mock, Callable, str, int, str, Union[str, None], int) -> None
    """Test correct incrementing of metrics when call is performed."""
    mock_statsd = mocker.MagicMock(spec_set=Statsd)
    client = request_session(
        max_retries=max_retries, statsd=mock_statsd
    )  # type: RequestSession
    client.get(path=path, raise_for_status=False)

    calls = []
    for attempt in range(1, call_count + 1):
        metric = "{}.{}".format(client._get_request_category(), "request")
        tags = ["status:{}".format(status)]
        if error:
            tags.append("error:{}".format(error))
        calls.append(mocker.call(metric, tags=tags + ["attempt:{}".format(attempt)]))

    assert mock_statsd.increment.call_count == call_count
    mock_statsd.increment.assert_has_calls(calls)


def test_get_request_category(httpbin):
    # type: (Httpbin) -> None
    client = RequestSession(host=httpbin.url)

    with pytest.raises(
        AttributeError, match="`request_category` is required parameter."
    ):
        client._get_request_category()

    assert (
        client._get_request_category(request_category=REQUEST_CATEGORY)
        == REQUEST_CATEGORY
    )

    client.request_category = REQUEST_CATEGORY

    assert client._get_request_category() == REQUEST_CATEGORY


@pytest.mark.parametrize(
    "path, seconds, max_retries, tags, call_count",
    [
        ("/status/500", 1, 1, [], 1),
        ("/status/500", 1, 2, ["test:success"], 2),
        ("/status/500", 1, 0, ["test:success"], 0),
    ],
)
def test_sleep_before_repeat(
    mocker, request_session, path, seconds, max_retries, tags, call_count
):
    # type: (Mock, Callable, str, int, int, List[str], int) -> None
    mock_ddtrace = mocker.Mock(spec_set=Statsd)
    mock_sleep = mocker.Mock()
    client = request_session(
        max_retries=max_retries, ddtrace=mock_ddtrace, raise_for_status=False
    )  # type: RequestSession
    client.sleep = mock_sleep  # type: ignore

    client.get(path=path, sleep_before_repeat=seconds, tags=tags)
    assert mock_sleep.call_count == call_count
    if call_count:
        mock_sleep.assert_called_with(seconds, client.request_category, tags)


@pytest.mark.parametrize(
    "inputs, expected",
    [
        (
            {
                "request_type": "post",
                "tags": ["test:success"],
                "run": 1,
                "path": "/status/200",
            },
            {},
        ),
        (
            {
                "request_type": "get",
                "tags": ["test:failed"],
                "run": 1,
                "path": "/status/500",
            },
            {},
        ),
    ],
)
def test_send_request(request_session, mocker, inputs, expected):
    # type: (Callable, Mock, Dict[str, Any], Dict[str, Any]) -> None
    mock_statsd = mocker.MagicMock(spec_set=Statsd)
    client = request_session(statsd=mock_statsd)  # type: RequestSession
    request_params = {
        "url": client.host + inputs["path"],
        "timeout": client.timeout,
        "verify": client.verify,
        "params": None,
    }

    response = client._send_request(  # type: ignore
        inputs["request_type"],
        request_params,
        inputs["tags"],
        inputs["run"],
        client.request_category,
    )

    assert isinstance(response, requests.Response)
    mock_statsd.timed.assert_called_once_with(
        "{}.response_time".format(client.request_category),
        use_ms=True,
        tags=inputs["tags"],
    )


def test_sleep(httpbin, mocker):
    # type: (Httpbin, Mock) -> None
    seconds = 1
    tags = ["testing:sleep"]
    meta = {"request_category": REQUEST_CATEGORY, "testing": "sleep"}
    mock_ddtrace = mocker.MagicMock(spec_set=Ddtrace)
    mock_traced_sleep = mocker.patch(
        "request_session.request_session.traced_sleep", autospec=True
    )
    client = RequestSession(host=httpbin.url, ddtrace=mock_ddtrace)
    client.sleep(seconds, REQUEST_CATEGORY, tags)

    mock_traced_sleep.assert_called_once_with(
        REQUEST_CATEGORY + "_retry", seconds, mock_ddtrace, meta
    )


@pytest.mark.parametrize(
    "inputs, expected",
    [
        (
            {
                "error": requests.exceptions.Timeout("Timeout"),
                "attempt": 1,
                "tags": [],
                "request_params": {},
                "verbose_logging": False,
                "status_code": 408,
            },
            {
                "tags": ["status:error", "error:timeout", "attempt:1"],
                "extra_params": {
                    "description": "Timeout",
                    "response_text": "",
                    "status": "error",
                    "attempt": 1,
                },
                "error_type": "read_timeout",
            },
        ),
        (
            {
                "error": requests.exceptions.HTTPError("HTTPError"),
                "attempt": 1,
                "tags": [],
                "request_params": {},
                "verbose_logging": False,
                "status_code": 400,
            },
            {
                "tags": ["status:error", "error:http_error", "attempt:1"],
                "extra_params": {
                    "description": "HTTPError",
                    "response_text": "",
                    "status": "error",
                    "attempt": 1,
                },
                "error_type": "http_error",
            },
        ),
        (
            {
                "error": requests.exceptions.ConnectionError("ConnectionError"),
                "attempt": 1,
                "tags": [],
                "request_params": {},
                "verbose_logging": False,
                "status_code": 444,
            },
            {
                "tags": ["status:error", "error:connection_error", "attempt:1"],
                "extra_params": {
                    "description": "ConnectionError",
                    "response_text": "",
                    "status": "error",
                    "attempt": 1,
                },
                "error_type": "connection_error",
            },
        ),
        (
            {
                "error": requests.exceptions.URLRequired("URLRequired"),
                "attempt": 1,
                "tags": [],
                "request_params": {},
                "verbose_logging": False,
                "status_code": None,
            },
            {
                "tags": ["status:error", "error:request_exception", "attempt:1"],
                "extra_params": {
                    "description": "URLRequired",
                    "response_text": "",
                    "status": "error",
                    "attempt": 1,
                },
                "error_type": "request_exception",
            },
        ),
        (
            {  # custom tags passed to the _exception_log_and_metrics
                "error": requests.exceptions.Timeout("Timeout"),
                "attempt": 1,
                "tags": ["custom:tags"],
                "request_params": {},
                "verbose_logging": False,
                "status_code": 408,
            },
            {
                "tags": ["status:error", "custom:tags", "error:timeout", "attempt:1"],
                "extra_params": {
                    "description": "Timeout",
                    "response_text": "",
                    "status": "error",
                    "attempt": 1,
                    "custom": "tags",
                },
                "error_type": "read_timeout",
            },
        ),
    ],
)
def test_exception_and_log_metrics(request_session, mocker, inputs, expected):
    # type: (Callable, Mock, Dict[str, Any], Dict[str, Any]) -> None
    mock_log = mocker.Mock()
    mock_metric_increment = mocker.Mock()
    client = request_session(
        verbose_logging=inputs["verbose_logging"]
    )  # type: RequestSession
    client.log = mock_log  # type: ignore
    client.metric_increment = mock_metric_increment  # type: ignore

    client._exception_log_and_metrics(  # type: ignore
        error=inputs["error"],
        request_category=client.request_category,
        request_params=inputs["request_params"],
        dd_tags=inputs["tags"],
        status_code=inputs["status_code"],
        attempt=inputs["attempt"],
    )

    mock_log.assert_called_once_with(
        "exception",
        "{}.failed".format(client.request_category),
        error_type=expected["error_type"],
        status_code=inputs["status_code"],
        **expected["extra_params"]
    )

    mock_metric_increment.assert_called_once_with(
        metric="request",
        request_category=client.request_category,
        tags=expected["tags"],
    )


def test_get_response_text(mocker):
    # type: (Mock) -> None
    mock_response = mocker.Mock(spec_set=requests.Response)
    mock_response.text = "response_text"
    assert RequestSession.get_response_text(mock_response) == "response_text"
    assert RequestSession.get_response_text("not_a_response_obj") == ""


def test_reporting(request_session, mocker):
    # type: (Callable, Mock) -> None
    """Test reporting of failure when rejected with 4xx."""
    mock_sentry_client = mocker.Mock(spec_set=SentryClient)
    session = request_session(raise_for_status=False, sentry_client=mock_sentry_client)
    session.get(path="/status/404", report=True)
    mock_sentry_client.captureException.assert_called_once_with(extra=None)


@pytest.mark.parametrize(
    ("exception, status_code, expected"),
    [
        (requests.exceptions.RequestException(), None, True),
        (requests.exceptions.ConnectionError(), None, True),
        (requests.exceptions.Timeout(), None, True),
        (requests.exceptions.HTTPError(), 400, False),
        (requests.exceptions.HTTPError(), 399, True),
        (requests.exceptions.HTTPError(), 408, True),  # Timeout is server error
        (requests.exceptions.HTTPError(), 499, False),
        (requests.exceptions.HTTPError(), 500, True),
        (requests.exceptions.HTTPError(), None, True),
    ],
)
def test_is_server_error(exception, status_code, expected):
    # type: (RequestException, Union[int, None], bool) -> None
    assert RequestSession.is_server_error(exception, status_code) == expected
