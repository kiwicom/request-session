"""Main RequestSession module."""
import re
import sys
import time
from collections import namedtuple
from typing import List  # pylint: disable=unused-import
from typing import Any, Callable, Dict, Optional, Tuple, Union

import attr
import requests
import requests.adapters
import simplejson as json

from ._compat import urljoin
from .exceptions import InvalidUserAgentString, RequestSessionException
from .protocols import Ddtrace, SentryClient, Statsd
from .utils import (
    UserAgentComponents,
    dict_to_string,
    reraise_as_third_party,
    split_tags_and_update,
    traced_sleep,
)

Timeout = namedtuple("Timeout", ["connection_timeout", "read_timeout"])


class RequestSession(object):
    """Helper class for HTTP requests with common settings.

    :param str host: Host name
    :param dict headers: (optional) Dictionary of HTTP headers to be used.
    :param tuple auth: (optional) Authorization tuple to enable
        Basic/Digest/Custom HTTP Auth.
    :param timeout: (optional) How many seconds to wait until retrying.
        Defaults to 10.
    :type timeout: [float, Timeout, Tuple[float, float]]
    :param verify: (optional) Either a boolean, in which case it controls whether
        to verify the servers TLS certificate, or a string, in which case it must
        be a path to a CA bundle to use. Defaults to ``True``.
    :type verify: [bool, str]
    :param int max_retries: (optional) Number of retries if the execution fails with
        server error. Defaults to 0.
    :param bool verbose_logging: (optional) If true, add request's parameters to event
        being logged. Defaults to ``False``.
    :param str request_category: (optional) Name of the event. ``request_category`` has
        to passed to the object or as an argument when calling some HTTP method.
    :param bool raise_for_status: (optional) Raise an exception in case of an error.
        Defaults to ``False``.
    :param str user_agent: (optional) User-Agent to be set in headers.
    :param list[requests.Session] session_instances: (optional) A list of
        ``requests.Session`` to be used to make the HTTP requests.
    :param Ddtrace ddtrace: (optional) DataDog function to be used to trace, track and
        send metrics for individual HTTP requests.
    :param Statsd statsd: (optional) Datadog module to log metrics.
    :param SentryClient sentry_client: (optional) Sentry module to log exceptions.
    :param Callable logger: (optional) Logger to be used when logging to `stdout`
        and `stderr`. If none is set, `builtin_logger` is used. Defaults to ``None``.
    :param str log_prefix: (optional) Prefix to be used when logging to `stdout`
        and `stderr`. Defaults to ``requestsession``.
    :param Tuple[str] allowed_log_levels: (optional) Log levels that are supported by
        the `logger` used. Defaults to
        ``("debug", "info", "warning", "error", "critical", "exception", "log")``.
    """

    session_instances = []  # type: List[requests.Session]

    def __init__(
        self,
        host=None,  # type: str
        auth=None,  # type: Optional[Tuple]
        timeout=10,  # type: Union[float, Tuple[float, float], Timeout]
        verify=True,  # type: Union[bool, str]
        max_retries=0,  # type: int
        verbose_logging=False,  # type: bool
        headers=None,  # type: Optional[Dict]
        request_category=None,  # type: Optional[str]
        raise_for_status=True,  # type: bool
        user_agent=None,  # type: Optional[str]
        user_agent_components=None,  # type: Optional[UserAgentComponents]
        ddtrace=None,  # type: Optional[Ddtrace]
        statsd=None,  # type: Optional[Statsd]
        sentry_client=None,  # type: Optional[SentryClient]
        logger=None,  # type: Optional[Callable]
        log_prefix="requestsession",  # type: str
        allowed_log_levels=(
            "debug",
            "info",
            "warning",
            "error",
            "critical",
            "exception",
            "log",
        ),  # type: Tuple
    ):
        # type: (...) -> None
        self.host = host
        self.auth = auth
        self.timeout = timeout
        self.verify = verify
        self.max_retries = max_retries
        self.verbose_logging = verbose_logging
        self.headers = headers
        self.request_category = request_category
        self.raise_for_status = raise_for_status
        self.user_agent = user_agent
        self.user_agent_components = user_agent_components
        self.ddtrace = ddtrace
        self.statsd = statsd
        self.sentry_client = sentry_client
        self.logger = logger
        self.log_prefix = log_prefix
        self.allowed_log_levels = allowed_log_levels

        self.prepare_new_session()

    def prepare_new_session(self):
        # type: () -> None
        """Prepare new configured session."""
        self.session = requests.Session()
        self.session_instances.append(self.session)

        adapter = requests.adapters.HTTPAdapter(max_retries=1)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        if self.user_agent is not None:
            self.session.headers.update({"User-Agent": self.user_agent})
        elif self.user_agent_components is not None:
            self.set_user_agent()

        if self.headers is not None:
            self.session.headers.update(self.headers)

        if self.auth is not None:
            self.session.auth = self.auth  # type: ignore

    def remove_session(self):
        # type: () -> None
        """Close session and remove it from list of session instances."""
        if self.session in self.session_instances:
            del self.session_instances[self.session_instances.index(self.session)]
        self.session.close()

    def set_user_agent(self):
        # type: () -> None
        """Set proper user-agent string to header according to RFC22."""
        pattern = r"^(?P<service_name>\S.+?)\/(?P<version>\S.+?) \((?P<organization>\S.+?) (?P<environment>\S.+?)\)(?: ?(?P<sys_info>.*))$"
        string = "{service_name}/{version} ({organization} {environment}) {sys_info}".format(
            service_name=self.user_agent_components.service_name,  # type: ignore
            version=self.user_agent_components.version,  # type: ignore
            organization=self.user_agent_components.organization,  # type: ignore
            environment=self.user_agent_components.environment,  # type: ignore
            sys_info=self.user_agent_components.sys_info  # type: ignore
            if self.user_agent_components.sys_info  # type: ignore
            else "",
        ).strip()
        if not re.match(pattern, string):
            raise InvalidUserAgentString("Provided User-Agent string is not valid.")
        self.user_agent = string
        self.session.headers.update({"User-Agent": string})

    @classmethod
    def close_all_sessions(cls):
        # type: () -> None
        """Close and remove all sessions in cls.session_instances."""
        for session in cls.session_instances:
            session.close()
        cls.session_instances = []

    def delete(self, path, **kwargs):
        # type: (str, Any) -> Optional[requests.Response]
        r"""Delete request against a service.

        :param str path: URL path, will be combined with ``self.host`` to build whole
            request url.
        :param \*\*kwargs: Optional arguments that request takes
            - check request_session and requests packages documentation for further reference.

        :return requests.Response: HTTP Response Object

        :raises requests.RequestException: Server error on operation
            (if raise_for_status is True).
        :raises RequestSessionException: Client error on operation (if raise_for_status is True)
        """
        url = urljoin(self.host, path) if self.host else path
        return self._process("delete", url, **kwargs)

    def get(self, path, **kwargs):
        # type: (str, Any) -> Optional[requests.Response]
        r"""Get request against a service.

        :param str path: URL path, will be combined with ``self.host`` to build whole
            request URL.
        :param \*\*kwargs: Optional arguments that request takes
            - check request_session and requests packages documentation for further reference.

        :return requests.Response: HTTP Response Object

        :raises requests.RequestException: Server error on operation
            (if raise_for_status is True).
        :raises RequestSessionException: Client error on operation (if raise_for_status is True)
        """
        url = urljoin(self.host, path) if self.host else path
        return self._process("get", url, **kwargs)

    def post(self, path, **kwargs):
        # type: (str, Any) -> Optional[requests.Response]
        r"""Post request against a service.

        :param str path: url path, will be combined with ``self.host`` to build whole
            request url.
        :param \*\*kwargs: Optional arguments that request takes
            - check request_session and requests packages documentation for further reference.

        :return requests.Response: HTTP Response Object

        :raises requests.RequestException: Server error on operation
            (if raise_for_status is True).
        :raises RequestSessionException: Client error on operation (if raise_for_status is True).
        """
        url = urljoin(self.host, path) if self.host else path
        return self._process("post", url, **kwargs)

    def put(self, path, **kwargs):
        # type: (str, Any) -> Optional[requests.Response]
        r"""Put request against a service.

        :param str path: URL path, will be combined with ``self.host`` to build whole
            request url.
        :param \*\*kwargs: Optional arguments that request takes
            - check request_session and requests packages documentation for further reference.

        :return requests.Response: HTTP Response Object

        :raises requests.RequestException: Server error on operation
            (if raise_for_status is True).
        :raises RequestSessionException: Client error on operation (if raise_for_status is True)
        """
        url = urljoin(self.host, path) if self.host else path
        return self._process("put", url, **kwargs)

    def patch(self, path, **kwargs):
        # type: (str, Any) -> Optional[requests.Response]
        r"""Patch request against a service.

        :param str path: URL path, will be combined with ``self.host`` to build whole
            request url.
        :param \*\*kwargs: Optional arguments that request takes
            - check request_session and requests packages documentation for further reference.

        :return requests.Response: HTTP Response Object

        :raises requests.RequestException: Server error on operation
            (if raise_for_status is True).
        :raises RequestSessionException: Client error on operation (if raise_for_status is True)
        """
        url = urljoin(self.host, path) if self.host else path
        return self._process("patch", url, **kwargs)

    def _process(
        self,
        request_type,  # type: str
        url,  # type: str
        request_category=None,  # type: Optional[str]
        max_retries=None,  # type: Optional[int]
        report=True,  # type: Optional[bool]
        sleep_before_repeat=None,  # type: Optional[float]
        tags=None,  # type: Optional[list]
        raise_for_status=None,  # type: Optional[bool]
        **request_kwargs  # type: Any
    ):
        # type: (...) -> Optional[requests.Response]
        r"""Run a request against a service depending on a request type.

        :param str request_type: `post` or `get`
        :param str url: URL for the new Request object.
        :param str request_category: (optional) Category for log and metric reporting,
            can be set on client init.
        :param int max_retries: Number of retries if the execution fail with server
            error.
        :param bool report: Report request exceptions to error_lib.swallow.
        :param float sleep_before_repeat: Seconds to sleep before another retry.
        :param list tags: tags for Datadog
        :param bool raise_for_status: Raise an exception in case of an error response.
        :param \*\*request_kwargs: Optional arguments that request takes:

        :return requests.Response: HTTP Response Object

        :raises requests.RequestException: Server error on operation.
            (if raise_for_status is True).
        :raises RequestSessionException: Client error on operation (if raise_for_status is True).
        """
        tags = [] if not tags else tags

        request_params = {
            "url": url,
            "timeout": self.timeout,
            "verify": self.verify,
            "params": None,
        }  # type: Dict
        request_params.update(request_kwargs)

        response = None
        request_category = self._get_request_category(request_category)
        raise_for_status = (
            raise_for_status if raise_for_status is not None else self.raise_for_status
        )

        max_runs = 1 + (self.max_retries if max_retries is None else max_retries)
        run, retries_on_econnreset = 0, 0
        # this will set maximum number of retries to max_runs where econnreset retries
        # are not counting and maximum number of of retries on econnreset is also
        # set to max_runs
        while run < max_runs + retries_on_econnreset:
            run += 1
            try:
                response = self._send_request(
                    request_type, request_params, tags, run, request_category
                )
                response.raise_for_status()

                success_tags = list(tags) if tags else []
                success_tags.append("status:success")

                self.metric_increment(
                    metric="request",
                    request_category=request_category,
                    tags=success_tags,
                    attempt=run,
                )

                self._log_with_params(
                    request_params,
                    response,
                    success_tags,
                    request_category,
                    attempt=run,
                    url=url,
                )

            except requests.RequestException as error:
                error_tags = list(tags) if tags else []

                status_code = None if response is None else response.status_code

                is_econnreset_error = isinstance(
                    error, requests.exceptions.ConnectionError
                ) and (
                    "ECONNRESET" in str(error)
                    or "Connection reset by peer" in str(error)
                )

                if not is_econnreset_error:
                    self._exception_log_and_metrics(
                        error=error,
                        request_category=request_category,
                        request_params=request_params,
                        dd_tags=error_tags,
                        status_code=status_code,
                        attempt=run,
                    )

                if self.is_server_error(error, status_code):
                    if is_econnreset_error:
                        self.log("info", "{}.session_replace".format(request_category))
                        self.remove_session()
                        self.prepare_new_session()

                        retries_on_econnreset += 1

                    # try again in case of ECONNRESET,
                    # even for api client with 0 retries
                    failed_on_last_try = (
                        run == max_runs + retries_on_econnreset
                        or max(max_runs, 2) == retries_on_econnreset
                    )

                    if failed_on_last_try:
                        if is_econnreset_error:
                            self._exception_log_and_metrics(
                                error=error,
                                request_category=request_category,
                                request_params=request_params,
                                dd_tags=error_tags,
                                status_code=status_code,
                                attempt=run,
                            )

                        if raise_for_status:
                            reraise_as_third_party()
                            raise  # pylint: disable=misplaced-bare-raise
                        return response

                else:
                    # Client error, request is not valid and server rejected it with
                    # http 4xx, but not timeout, there is no point in retrying.
                    if report and self.sentry_client is not None:
                        response_text = self.get_response_text(response)
                        extra_data = (
                            {"response_text": response_text}
                            if response_text != ""
                            else None
                        )
                        self.sentry_client.captureException(extra=extra_data)

                    if raise_for_status:
                        raise RequestSessionException(str(error), original_exc=error)
                    return response

                if sleep_before_repeat:
                    if self.ddtrace is not None:
                        self.sleep(sleep_before_repeat, request_category, tags)
                    else:
                        time.sleep(sleep_before_repeat)

            else:
                return response

        return None

    def _send_request(self, request_type, request_params, tags, run, request_category):
        # type: (str, Dict[str, Any], List[str], int, str) -> requests.Response
        """Send the request and metrics.

        :param str request_type: HTTP method
        :param Dict[str, Any] request_params: Parameters to call the request with.
        :param List[str] tags: Tags to be added to metrics.
        :param int run: Attempt number.
        :param str request_category: Category for log and metric reporting.
        :return requests.Response: HTTP Response Object.
        """
        metric_name = "{request_category}.response_time".format(
            request_category=request_category
        )

        if not self.statsd:
            return self.session.request(method=request_type, **request_params)

        with self.statsd.timed(metric_name, use_ms=True, tags=tags):
            if self.ddtrace:
                with self.ddtrace.tracer.trace(
                    "api.request",
                    service="booking_api_requests",
                    resource=request_category,
                ):
                    response = self.session.request(
                        method=request_type, **request_params
                    )
            else:
                response = self.session.request(method=request_type, **request_params)
        return response

    def _log_with_params(
        self, request_params, response, tags, request_category, attempt, url
    ):
        # type: (Dict, requests.Response, List[str], str, int, str) -> None
        """Prepare parameters and log response.

        :param Dict request_params: Parameters used in the request.
        :param requests.Response response: HTTP Response.
        :param List[str] tags: Tags denoting success of the request.
        :param str request_category: Category of the request.
        """
        extra_params = (
            {
                "request_params": json.dumps(request_params),
                "response_text": self.get_response_text(response),
            }
            if self.verbose_logging
            else {}
        )
        split_tags_and_update(extra_params, tags)
        self.log(
            "info",
            request_category,
            status_code=response.status_code,
            attempt=attempt,
            url=url,
            **extra_params
        )

    def sleep(self, seconds, request_category, tags):
        # type: (float, str, List[str]) -> None
        """Call sleep function and send metrics to datadog.

        :param float seconds: float or int number of seconds to sleep
        :param str request_category: request category
        :param List[str] tags: tags for datadog
        """
        trace_name = request_category.replace(".", "_") + "_retry"
        meta = {"request_category": request_category}
        split_tags_and_update(meta, tags)
        traced_sleep(trace_name, seconds, self.ddtrace, meta)  # type: ignore

    def metric_increment(self, metric, request_category, tags, attempt=None):
        # type: (str, str, list, Optional[int]) -> None
        """Metric request increment.

        :param str metric: Name of the metric to be incremented.
        :param str request_category: request category
        :param List[str] tags: Tags to increment metric with.
        :param int attempt: Number of attempt of the request.
        """
        new_tags = list(tags) if tags else []
        if attempt:
            new_tags.append("attempt:{attempt}".format(attempt=attempt))

        if self.statsd is not None:
            metric_name = "{metric_base}.{metric_type}".format(
                metric_base=request_category, metric_type=metric
            )
            self.statsd.increment(metric_name, tags=new_tags)

    def log(self, level, event, **kwargs):
        # type: (str, str, **Any) -> None
        r"""Proxy to log with provided logger.

        Builtin logging library is used otherwise.
        :param level: string describing log level
        :param event: event (<request_category> or <request_category>.<action>)
        :param \*\*kwargs: kw arguments to be logged
        """
        if not level in self.allowed_log_levels:
            raise AttributeError("Provided log level is not allowed.")
        event_name = "{prefix}.{event}".format(prefix=self.log_prefix, event=event)
        if self.logger is not None:
            getattr(self.logger, level)(event_name, **kwargs)

    def _exception_log_and_metrics(
        self,
        error,  # type: requests.RequestException
        request_category,  # type: str
        request_params,  # type: Dict
        dd_tags,  # type: List[str]
        status_code,  # type: Union[int, None]
        attempt,  # type: int
    ):
        # type: (...) -> None
        """Assign appropriate metric and log for exception.

        :param requests.RequestException error: exception that occured
        :param str request_category: String describing request category.
        :param Dict request_params: Parameters used to make the HTTP call.
        :param List[str] dd_tags: Tags to increment metric with.
        :param Union[int, None] Status_code: HTTP status code of the response.
        """
        tags = ["status:error"]

        tags.extend(dd_tags)
        response_text = self.get_response_text(error.response)
        extra_params = {"description": str(error), "response_text": response_text}
        split_tags_and_update(extra_params, tags)

        if isinstance(error, requests.exceptions.Timeout):
            error_type = "read_timeout"
            tags.append("error:timeout")

        elif isinstance(error, requests.exceptions.HTTPError):
            error_type = "http_error"
            tags.append("error:http_error")

        elif isinstance(error, requests.exceptions.ConnectionError):
            error_type = "connection_error"
            tags.append("error:connection_error")
        else:
            error_type = "request_exception"
            tags.append("error:request_exception")

        if self.verbose_logging is True:
            extra_params["request_params"] = json.dumps(request_params)

        self.log(
            "exception",
            "{}.failed".format(request_category),
            error_type=error_type,
            status_code=status_code,
            attempt=attempt,
            **extra_params
        )

        self.metric_increment(
            metric="request",
            request_category=request_category,
            tags=tags + ["attempt:{}".format(attempt)],
        )

    @staticmethod
    def is_server_error(error, http_code):
        # type: (requests.RequestException, Optional[int]) -> bool
        """Exception type and response code match server error.

        :param requests.RequestException error: exception
        :param int http_code: (optional) response HTTP status code
        :return bool: whether error is server error
        """
        if not isinstance(error, requests.exceptions.HTTPError):
            return True

        if http_code is not None and (400 <= http_code < 500 and not http_code == 408):
            return False

        return True

    @staticmethod
    def get_response_text(response):
        # type: (Union[requests.Response, Any]) -> str
        """Return response text if exists.

        :param request.Response response: HTTP Response Object
        :return str: response text
        """
        try:
            return response.text
        except (AttributeError, UnicodeDecodeError):
            return ""

    def _get_request_category(self, request_category=None):
        # type: (str) -> str
        """Get request category. Passed in request category has a precedence.

        :param str request_category: (optional) Request category passed in function.
            Defaults to `None`.
        :return: Request category

        :raises RequestSessionException: Raised when `request_category` was not provided.
        """
        request_category = request_category or self.request_category
        if request_category is None:
            raise AttributeError("`request_category` is required parameter.")

        return request_category
