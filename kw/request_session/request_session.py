"""Base modules for implementing adapters."""
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
from .protocols import SentryClient, Statsd
from .utils import APIError, dict_to_string
from .utils import logger as builtin_logger
from .utils import null_context_manager, reraise_as_third_party, split_tags_and_update

Timeout = namedtuple("Timeout", ["connection_timeout", "read_timeout"])


@attr.s
class RequestSession(object):

    """Helper class for url requests with common settings.

    RequestSession is a helper class built on top of the `requests.Session`
    to help with default configuration, retry, logging and metrics.
    Every call to `get` or `post` methods will generate logs and metrics.
    To name events and metrics we use `request_category`
    parameters of the class or method.

    Recommended way to use `RequestSession` is to create a client module
    for accessing group of resources served on common endpoint with default values
    that are valid for all or most of the calls you need to make.
    For your convenience some defaults are provided like default timeout for calls etc.

    Attributes
        - host: Host name
        - headers: Dictionary of HTTP Headers to send with the Request
        - auth: Auth tuple to enable Basic/Digest/Custom HTTP Auth
        - timeout: How many seconds to wait for the server to send data
        - verify: Either a boolean, in which case it controls whether we verify
                the server's TLS certificate, or a string, in which case it must
                be a path to a CA bundle to use. Defaults to ``True``.
        - max_retries: Number of retries if the execution fail with server error
        - verbose_logging: If true add to event request parameters
                        which are passed to request
        - request_category: Name of event and metric
        - datadog_service_name: String representing name of service in DataDog for
                                better tracing

    **Metrics**

    On each call you make to `post` and `get` methods several metrics are sent.
    All metric names are composed from `request_category` parameter
    (either from class property or from call argument) and prefixed with `booking`:

    - response time, booking.{request_category}.response_time:
        response time metric is used to time how long it took for a client to receive
        response (if any). Metric name is composed of `booking.` prefix,
        `request category` as base for the metric name and `.response_time` as postfix

    - request status, booking.{request_category}.request:
        request status metric is used to track the success status of the request.

        Status is tracked with two tag groups:

            - status:
                status can have 2 values: success or error

            - error (optional):
               error tag is added to event only if request is failed (status:error tag
               is present in event) and it is used to describe error type in better
               detail.

               Possible values are:

                - timeout: request has timed out

                - http_error: server has responded http 4xx or 5xx

                - connection_error: connection to server failed

                - request_exception: other

    Additionally, you can include you own tags that will be appended to metric tags.

    **Logs**

    Each exception on the request can be logged.
    There are 2 implied levels of exception: error and warning.
    Exception that happened on a try that can not be repeated will be treated as error
    and will always be logged, exception that happened on a try that can be repeated is
    treated as warning and it will not be logged if `report` parameter of the method
    call is set to `False`.

    Log event name is composed in following way:  {request_category}.failed

    Parameters of the event:

    - error_type:
        always present in event and provides context of the error with possible values:

            - read_timeout: request has timed out

            - http_error: server has responded http 4xx or 5xx

            - connection_error: connection to server failed

            - request_exception: other

    - description:
        `description` contains string representation of the `requests.exception`

    - text:
        `text` contains response text in case of http error, if response object
        had any text

    - request_params (optional):
        if attribute `verbose_logging` of the instance is set to `True` event will
        also contain request parameters passed to request

    Explanation of the distinction between error and warning exception type:

    For example, we have a request that can be repeated:

    - on a first try the request times out

    - we repeat request and it is successful

    In this case we reached the final goal, the request was successfully transferred,
    even if it needed a push. The exception report can be informative
    so we can log it as warning.

    In another example, we have a request that can be repeated:

    - on a first try the request times out

    - we repeat request and it times out again and we reached maximum number of retry

    In this case we did not reach the final goal, the request failed.
    The first failure can be logged as a warning, but second failure was critical
    and will always be logged as error.

    **Retry**

    It is possible to configure a retry in case of request failure.
    By default the number of retries is set to 0.
    You can set number of retries for all requests trough instance attribute
    `max_retries` or you can pass it as an optional parameter `max_retries`.
    The value passed trough method call has precedence.
    The parameter is number of retries on failure, not maximum number of attempts.
    Eg. if retry is set to 2 and there are no success on any attempt,
    the total number of requests will be 3: nominal request and retry 2 times on
    failure.


    Note: the request will not be retried in case of client error,
    that is if server responded with http 4xx, but not http 408 Request Timeout

    If `sleep_before_repeat` parameter is passed,
    the method will wait for that amount of seconds before retry.


    Example::
        session = RequestSession(host="google.com", max_retries=2)

        response = session.get(
            "search",
            request_category="bmw.fan.club",
            params={"q": "BMW+E90+330i"},
            timeout=5,
            tags=["search:bmw"]
        )
    """

    host = attr.ib(None, type=str, converter=str)

    headers = attr.ib(None, type=dict)
    auth = attr.ib(None, type=tuple)

    timeout = attr.ib(10, type=Union[float, Tuple[float, float], Timeout])
    verify = attr.ib(True, type=Union[bool, str])

    max_retries = attr.ib(0, type=int, validator=attr.validators.instance_of(int))
    verbose_logging = attr.ib(False, type=bool)

    request_category = attr.ib(None, type=str)

    raise_for_status = attr.ib(
        True, type=bool, validator=attr.validators.instance_of(bool)
    )

    user_agent = attr.ib(None, type=str)

    session_instances = []  # type: List[requests.Session]

    ddtrace = attr.ib(None)

    datadog_service_name = attr.ib(None, type=str)

    statsd = attr.ib(None, type=Statsd)  # type: Statsd

    sentry_client = attr.ib(None, type=SentryClient)  # type: SentryClient

    logger = attr.ib(None, type=Callable)

    log_prefix = attr.ib("requestsession", type=str)

    metric_name = attr.ib("request", type=str)

    allowed_log_levels = attr.ib(
        ("debug", "info", "warning", "error", "critical", "exception", "log"),
        type=Tuple[str],
    )

    def __attrs_post_init__(self):
        self.prepare_new_session()

    def prepare_new_session(self):
        """Prepare new configured session."""
        self.session = requests.Session()
        self.session_instances.append(self.session)

        adapter = requests.adapters.HTTPAdapter(max_retries=1)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        if self.user_agent is not None:
            self.session.headers.update({"User-Agent": self.user_agent})

        if self.datadog_service_name is not None:
            if not self.ddtrace or (self.ddtrace and not self.ddtrace.config):
                raise APIError(
                    "Ddtrace must be provided in order to report to datadog service."
                )
            tracing_config = self.ddtrace.config.get_from(self.session)
            tracing_config["service_name"] = self.datadog_service_name

        if self.headers is not None:
            self.session.headers.update(self.headers)

        if self.auth is not None:
            self.session.auth = self.auth

    def remove_session(self):
        """Close session and remove it from list of session instances."""
        if self.session in self.session_instances:
            del self.session_instances[self.session_instances.index(self.session)]
        self.session.close()

    def close_all_sessions(self):
        """Close and remove all sessions in self.session_instances."""
        for session in self.session_instances:
            session.close()
        self.session_instances = []

    def delete(
        self,
        path,  # type: str
        request_category=None,  # type: Optional[str]
        max_retries=None,  # type: Optional[int]
        report=True,  # type: Optional[bool]
        sleep_before_repeat=None,  # type: Optional[float]
        tags=None,  # type: Optional[list]
        raise_for_status=None,  # type: Optional[bool]
        **request_kwargs
    ):
        # type: (...) -> Optional[requests.Response]
        r"""Delete request against a service.

        :param str path: url path, will be combined with ``self.host`` to build whole
            request url
        :param str request_category: (optional) category for log and metric reporting,
            can be set on client init
        :param int max_retries: (optional) number of retries if the execution fail with
            server error
        :param bool report: (optional) report request exceptions to error_lib.swallow
        :param float sleep_before_repeat: (optional) seconds to sleep before another
            retry
        :param list tags: (optional) tags for Datadog
        :param bool raise_for_status: (optional) raise an exception in case of an error
            response
        :param \*\*request_kwargs: Optional arguments that request takes.
            Check `_process()` for more info.

        :return: http response object

        :raises requests.RequestException: server error on operation
            (if raise_for_status is True)
        :raises APIError: client error on operation (if raise_for_status is True)
        """
        url = urljoin(self.host, path)
        return self._process(
            "delete",
            url,
            request_category=request_category,
            max_retries=max_retries,
            report=report,
            sleep_before_repeat=sleep_before_repeat,
            tags=tags,
            raise_for_status=raise_for_status,
            **request_kwargs
        )

    def get(
        self,
        path,  # type: str
        request_category=None,  # type: Optional[str]
        max_retries=None,  # type: Optional[int]
        report=True,  # type: Optional[bool]
        sleep_before_repeat=None,  # type: Optional[float]
        tags=None,  # type: Optional[list]
        raise_for_status=None,  # type: Optional[bool]
        **request_kwargs
    ):
        # type: (...) -> Optional[requests.Response]
        r"""Get request against a service.

        :param str path: url path, will be combined with ``self.host`` to build whole
            request url
        :param str request_category: (optional) category for log and metric reporting,
            can be set on client init
        :param int max_retries: (optional) number of retries if the execution fail with
            server error
        :param bool report: (optional) report request exceptions to error_lib.swallow
        :param float sleep_before_repeat: (optional) seconds to sleep before another
            retry
        :param list tags: (optional) tags for Datadog
        :param bool raise_for_status: (optional) raise an exception in case of an error
            response
        :param \*\*request_kwargs: Optional arguments that request takes.
            Check `_process()` for more info.

        :return: http response object

        :raises requests.RequestException: server error on operation
            (if raise_for_status is True)
        :raises APIError: client error on operation (if raise_for_status is True)
        """
        url = urljoin(self.host, path)
        return self._process(
            "get",
            url,
            request_category=request_category,
            max_retries=max_retries,
            report=report,
            sleep_before_repeat=sleep_before_repeat,
            tags=tags,
            raise_for_status=raise_for_status,
            **request_kwargs
        )

    def post(
        self,
        path,  # type: str
        request_category=None,  # type: Optional[str]
        max_retries=None,  # type: Optional[int]
        report=True,  # type: Optional[bool]
        sleep_before_repeat=None,  # type: Optional[float]
        tags=None,  # type: Optional[list]
        raise_for_status=None,  # type: Optional[bool]
        **request_kwargs
    ):
        # type: (...) -> Optional[requests.Response]
        r"""Post request against a service.

        :param str path: url path, will be combined with ``self.host`` to build whole
            request url
        :param str request_category: (optional) category for log and metric reporting,
            can be set on client init
        :param int max_retries: (optional) number of retries if the execution fail with
            server error
        :param bool report: (optional) report request exceptions to error_lib.swallow
        :param float sleep_before_repeat: (optional) seconds to sleep before another
            retry
        :param list tags: (optional) tags for Datadog
        :param bool raise_for_status: (optional) raise an exception in case of an error
        response
        :param \*\*request_kwargs: Optional arguments that request takes.
            Check `_process()` for more info.

        :return: http response object

        :raises requests.RequestException: server error on operation
            (if raise_for_status is True)
        :raises APIError: client error on operation (if raise_for_status is True)
        """
        url = urljoin(self.host, path)
        return self._process(
            "post",
            url,
            request_category=request_category,
            max_retries=max_retries,
            report=report,
            sleep_before_repeat=sleep_before_repeat,
            tags=tags,
            raise_for_status=raise_for_status,
            **request_kwargs
        )

    def put(
        self,
        path,  # type: str
        request_category=None,  # type: Optional[str]
        max_retries=None,  # type: Optional[int]
        report=True,  # type: Optional[bool]
        sleep_before_repeat=None,  # type: Optional[float]
        tags=None,  # type: Optional[list]
        raise_for_status=None,  # type: Optional[bool]
        **request_kwargs
    ):
        # type: (...) -> Optional[requests.Response]
        r"""Put request against a service.

        :param str path: url path, will be combined with ``self.host`` to build whole
            request url
        :param str request_category: (optional) category for log and metric reporting,
            can be set on client init
        :param int max_retries: (optional) number of retries if the execution fail with
            server error
        :param bool report: (optional) report request exceptions to error_lib.swallow
        :param float sleep_before_repeat: (optional) seconds to sleep before another
            retry
        :param list tags: (optional) tags for Datadog
        :param bool raise_for_status: (optional) raise an exception in case of an
            error response
        :param \*\*request_kwargs: Optional arguments that request takes.
            Check `_process()` for more info.

        :return: http response object

        :raises requests.RequestException: server error on operation
            (if raise_for_status is True)
        :raises APIError: client error on operation (if raise_for_status is True)
        """
        url = urljoin(self.host, path)
        return self._process(
            "put",
            url,
            request_category=request_category,
            max_retries=max_retries,
            report=report,
            sleep_before_repeat=sleep_before_repeat,
            tags=tags,
            raise_for_status=raise_for_status,
            **request_kwargs
        )

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
        **request_kwargs
    ):
        # type: (...) -> Optional[requests.Response]
        r"""Run a request against a service depending on a request type.

        :param str request_type: `post` or `get`
        :param str url: URL for the new Request object.
        :param str request_category: (optional) category for log and metric reporting,
            can be set on client init
        :param int max_retries: number of retries if the execution fail with server
            error
        :param bool report: report request exceptions to error_lib.swallow
        :param float sleep_before_repeat: seconds to sleep before another retry
        :param list tags: tags for Datadog
        :param bool raise_for_status: raise an exception in case of an error response
        :param \*\*request_kwargs: Optional arguments that request takes:

        * url: (optional) to override ``url`` param.
        * params: (optional) Dictionary or bytes to be sent in the query string for
            the Request.
        * data: (optional) Dictionary or list of tuples ``[(key, value)]``
            (will be form-encoded), bytes, or file-like object to send in the body of
            the Request.
        * json: (optional) A JSON serializable Python object to send in the body of
            the Request.
        * headers: (optional) Dictionary of HTTP Headers to send with the Request.
        * cookies: (optional) Dict or CookieJar object to send with the Request.
        * files: (optional) Dictionary of ``'name': file-like-objects``
        * auth: (optional) Auth tuple to enable Basic/Digest/Custom HTTP Auth.
        * timeout: (optional) How many seconds to wait for the server to send data
            before giving up, as a float, or a :ref:`(connect timeout, read timeout)
            <timeouts>` tuple.
        * allow_redirects: (optional) Boolean.
            Enable/disable GET/OPTIONS/POST/PUT/PATCH/DELETE/HEAD redirection.
            Defaults to ``True``.
        * proxies: (optional) Dictionary mapping protocol to the URL of the proxy.
        * verify: (optional) Either a boolean, in which case it controls whether we
            verify the server's TLS certificate, or a string,
            in which case it must be a path to a CA bundle to use.
            Defaults to ``True``.
        * stream: (optional) if ``False``, the response content will be immediately
            downloaded.
        * cert: (optional) if String, path to ssl client cert file (.pem).
            If Tuple, ('cert', 'key') pair.

        :return: http response object

        :raises requests.RequestException: server error on operation
            (if raise_for_status is True)
        :raises APIError: client error on operation (if raise_for_status is True)
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
                    metric=self.metric_name,
                    request_category=request_category,
                    tags=success_tags,
                    attempt=run,
                )

                self._log_with_params(
                    request_params, response, success_tags, request_category
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
                        self.log(
                            "info",
                            "{log_prefix}.{request_category}.session_replace".format(
                                log_prefix=self.log_prefix,
                                request_category=request_category,
                            ),
                        )
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
                            reraise_as_third_party(sys)
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
                        raise APIError(str(error), original_exc=error)
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

        :param request_type: HTTP method
        :param request_params: parameters to call the request with
        :param tags: tags to be added to metrics
        :param run: attempt number
        :param request_category: category for log and metric reporting
        :return: requests.Response
        """
        metric_name = "{request_category}.response_time".format(
            request_category=request_category
        )
        timed = self.statsd.timed if self.statsd is not None else null_context_manager

        with timed(metric_name, use_ms=True, tags=tags):
            response = self.session.request(method=request_type, **request_params)
        return response

    def _log_with_params(self, request_params, response, tags, request_category):
        # type: (Dict, requests.Response, List[str], str) -> None
        """Prepare parameters and log response.

        :param request_params: parameters used in the request
        :param response: response
        :param tags: tags denoting success of the request
        :param request_category: category of the request
        """
        extra_params = (
            {
                "request_params": json.dumps(request_params),
                "response_text": self.get_response_text(response),
            }
            if self.verbose_logging
            else {}
        )
        extra_params = split_tags_and_update(extra_params, tags)
        self.log(
            "info",
            "{log_prefix}.{category}".format(
                log_prefix=self.log_prefix, category=request_category
            ),
            status_code=response.status_code,
            **extra_params
        )

    def sleep(self, seconds, request_category, tags):
        # type: (float, str, List[str]) -> None
        """Call sleep function and send metrics to datadog.

        :param float seconds: float or int number of seconds to sleep
        :param request_category: request category
        :param tags: tags for datadog

        :return: None
        """
        trace_name = request_category.replace(".", "_") + "_retry"
        meta = {"request_category": request_category}
        meta = split_tags_and_update(meta, tags)
        with self.ddtrace.tracer.trace(trace_name, service="sleep") as span:
            if meta:
                span.set_metas(meta)
            time.sleep(seconds)  # Ignore KeywordBear

    def metric_increment(self, metric, request_category, tags, attempt=None):
        # type: (str, str, list, Optional[int]) -> None
        """Metric request increment.

        :param metric: name of the metric to be incremented
        :param request_category: request category
        :param tags: tags to increment metric with
        :param attempt: number of attempt of the request
        """
        new_tags = list(tags) if tags else []
        if attempt:
            new_tags.append("attempt:{attempt}".format(attempt=attempt))

        if self.statsd is not None:
            metric_name = "{metric_base}.{metric_type}".format(
                metric_base=request_category, metric_type=metric
            )
            self.statsd.increment(metric_name, tags=new_tags)

    def log(self, level, request_category, **kwargs):
        # type: (str, str, **Any) -> None
        """Proxy to log with provided logger.

        Builtin logging library is used otherwise.

        :param level: string describing log level
        :param request_category: request category to be logged
        :param **kwargs: kw arguments to be logged
        """
        if not level in self.allowed_log_levels:
            raise APIError("Provided log level is not allowed.")
        event_name = "{prefix}.{category}".format(
            prefix=self.log_prefix, category=request_category
        )
        if self.logger is not None:
            getattr(self.logger, level)(event_name, **kwargs)
        else:
            getattr(builtin_logger, level)(
                event_name, extra={"tags": dict_to_string(kwargs)}
            )

    def _exception_log_and_metrics(
        self,
        error,  # type: requests.RequestException
        request_category,  # type: str
        request_params,  # type: Dict
        dd_tags,  # type: List[str]
        status_code,  # type: Union[int, None]
        attempt=None,  # type: Optional[int]
    ):
        # type: (...) -> None
        """Assign appropriate metric and log for exception.

        :param error: exception that occured
        :param request_category: string describing request category
        :param request_params: parameters used to make the HTTP call
        :param dd_tags: tags to increment metric with
        :param status_code: HTTP status code of the response
        """
        tags = (
            ["status:error", "attempt:{}".format(attempt)]
            if attempt
            else ["status:error"]
        )
        tags.extend(dd_tags)
        response_text = self.get_response_text(error.response)
        extra_params = {"description": str(error), "response_text": response_text}
        extra_params = split_tags_and_update(extra_params, tags)

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
            "{log_prefix}.{request_category}.failed".format(
                log_prefix=self.log_prefix, request_category=request_category
            ),
            error_type=error_type,
            status_code=status_code,
            **extra_params
        )

        self.metric_increment(
            metric=self.metric_name, request_category=request_category, tags=tags
        )

    @staticmethod
    def is_server_error(error, http_code):
        # type: (requests.RequestException, Optional[int]) -> bool
        """Exception type and response code match server error.

        :param error: exception
        :param http_code: response HTTP status code
        :return: if error is server error
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

        :param response: requests.Response object
        :return: response text
        """
        try:
            return response.text
        except (AttributeError, UnicodeDecodeError):
            return ""

    def _get_request_category(self, request_category=None):
        # type: (str) -> str
        """Get request category.

        :param request_category: request_category passed in function
        :return: request category method call, RequestSession init or default
        """
        request_category = request_category or self.request_category
        if request_category is None:
            raise APIError("'request_category' is required parameter.")

        return request_category
