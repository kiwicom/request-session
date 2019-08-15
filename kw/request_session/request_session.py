"""Base modules for implementing adapters."""
from collections import namedtuple
import re
from typing import Any, Dict, List, Optional, Tuple, Union  # pylint: disable=unused-import
from urllib.parse import urljoin

import attr
import ddtrace
from kw import json  # type: ignore
import requests
import requests.adapters
import structlog

from .. import error_lib, sentry_client, settings, statsd
from ..context import execution_context
from ..exceptions import APIError, InvalidUserAgentString
from ..utils import traced_sleep

Timeout = namedtuple("Timeout", ["connection_timeout", "read_timeout"])

log = structlog.get_logger()


@attr.s
class RequestSession(object):
    """Helper class for url requests with common settings.

    RequestSession is a helper class built on top of the `requests.Session` to help with default configuration, retry,
    logging and metrics. Every call to `get` or `post` methods will generate logs and metrics. To name events and
    metrics we use `request_category` parameters of the class or method.

    Recommended way to use `RequestSession` is to create a client module for accessing group of resources served
    on common endpoint with default values that valid for all or most of the calls you need to make. For your
    convenience some defaults are provided like default timeout for calls etc.

    Attributes
        - host: Host name
        - headers: Dictionary of HTTP Headers to send with the Request
        - auth: Auth tuple to enable Basic/Digest/Custom HTTP Auth
        - timeout: How many seconds to wait for the server to send data
        - verify: Either a boolean, in which case it controls whether we verify
                the server's TLS certificate, or a string, in which case it must be a path
                to a CA bundle to use. Defaults to ``True``.
        - max_retries: Number of retries if the execution fail with server error
        - verbose_logging: If true add to event request parameters which are passed to request
        - request_category: Name of event and metric
        - datadog_service_name: String representing name of service in DataDog for better tracing

    **Metrics**

    On each call you make to `post` and `get` methods several metrics are sent. All metric names are composed from
    `request_category` parameter (either from class property or from call argument) and prefixed with `booking`:

    - response time, booking.{request_category}.response_time:
        response time metric is used to time how long it took for a client to receive response (if any). Metric name is
        composed of `booking.` prefix, `request category` as a base for the metric name and `.response_time` as postfix

    - request status, booking.{request_category}.request:
        request status metric is used to track the success status of the request.

        Status is tracked with two tag groups:

            - status:
                status can have 2 values: success or error

            - error (optional):
               error tag is added to event only if request is failed (status:error tag is present in event) and it is
               used to describe error type in better detail.

               Possible values are:

                - timeout: request has timed out

                - http_error: server has responded http 4xx or 5xx

                - connection_error: connection to server failed

                - request_exception: other

    Additionally, you can include you own tags that will be appended to metric tags.

    **Logs**

    Each exception on the request can be logged. There are 2 implied levels of exception: error and warning. Exception
    that happened on a try that can not be repeated will be treated as error and will always be logged, exception that
    happened on a try that can be repeated is treated as warning and it will not be logged if `report` parameter of the
    method call is set to `False`.

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
        `text` contains response text in case of http error, if response object had any text

    - request_params (optional):
        if attribute `verbose_logging` of the instance is set to `True` event will also contain request parameters
        passed to request

    Explanation of the distinction between error and warning exception type:

    For example, we have a request that can be repeated:

    - on a first try the request times out

    - we repeat request and it is successful

    In this case we reached the final goal, the request was successfully transferred, even if it needed a push. The
    exception report can be informative so we can log it as warning.

    In another example, we have a request that can be repeated:

    - on a first try the request times out

    - we repeat request and it times out again and we reached maximum number of retry

    In this case we did not reach the final goal, the request failed. The first failure can be logged as a warning, but
    second failure was critical and will always be logged as error.

    **Retry**

    It is possible to configure a retry in case of request failure. By default the number of retries is set to 0. You
    can set number of retries for all requests trough instance attribute `max_retries` or you can pass it as an optional
    parameter `max_retries`. The value passed trough method call has precedence. The parameter is number of retries on
    failure, not maximum number of attempts. Eg. if retry is set to 2 and there are no success on any attempt, the total
    number of requests will be 3: nominal request and retry 2 times on failure.


    Note: the request will not be retried in case of client error, that is if server responded with http 4xx, but not
    http 408 Request Timeout

    If `sleep_before_repeat` parameter is passed, the method will wait for that amount of seconds before retry.


    Example::
        session = RequestSession(host="google.com", max_retries=2)

        response = session.get(

            "search", request_category="bmw.fan.club", params={"q": "BMW+E90+330i"}, timeout=5, tags=["search:bmw"]

        )
    """

    host = attr.ib(None, type=str, converter=str)

    headers = attr.ib(None, type=dict)
    auth = attr.ib(None, type=tuple)

    timeout = attr.ib(10, type=Union[float, Tuple[float, float], Timeout])
    verify = attr.ib(settings.api_clients.SSL_VERIFY, type=Union[bool, str])

    max_retries = attr.ib(0, type=int, validator=attr.validators.instance_of(int))
    verbose_logging = attr.ib(False, type=bool)

    request_category = attr.ib(None, type=str)

    raise_for_status = attr.ib(True, type=bool, validator=attr.validators.instance_of(bool))

    user_agent_components = attr.ib(None, type=UserAgentComponents)
    user_agent = attr.ib(None, type=str)

    session_instances = []  # type: List[requests.Session]

    datadog_service_name = attr.ib(None, type=str)

    def __attrs_post_init__(self):
        self.prepare_new_session()

    def prepare_new_session(self):
        self.session = requests.Session()
        self.session_instances.append(self.session)

        adapter = requests.adapters.HTTPAdapter(max_retries=1)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        if self.user_agent is not None:
            self.session.headers.update({"User-Agent": self.user_agent})
        elif self.user_agent_components is not None:
            self.set_user_agent()

        if self.datadog_service_name is not None:
            tracing_config = ddtrace.config.get_from(self.session)
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

    def set_user_agent(self):
        """Set proper user-agent string to header according to RFC22."""
        pattern = r"^(?P<service_name>\S.+?)\/(?P<version>\S.+?) \((?P<organization>\S.+?) (?P<environment>\S.+?)\)(?: ?(?P<sys_info>.*))$"
        string = "{service_name}/{version} ({organization} {environment}) {sys_info}".format(
            service_name=self.user_agent_components.service_name,
            version=self.user_agent_components.version,
            organization=self.user_agent_components.organization,
            environment=self.user_agent_components.environment,
            sys_info=self.user_agent_components.sys_info if self.user_agent_components.sys_info else "",
        ).strip()
        if not re.match(pattern, string):
            raise InvalidUserAgentString("Provided User-Agent string is not valid.")
        self.user_agent = string
        self.session.headers.update({"User-Agent": string})

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

        :param str path: url path, will be combined with ``self.host`` to build whole request url
        :param str request_category: (optional) category for log and metric reporting, can be set on client init
        :param int max_retries: (optional) number of retries if the execution fail with server error
        :param bool report: (optional) report request exceptions to error_lib.swallow
        :param float sleep_before_repeat: (optional) seconds to sleep before another retry
        :param list tags: (optional) tags for Datadog
        :param bool raise_for_status: (optional) raise an exception in case of an error response
        :param \*\*request_kwargs: Optional arguments that request takes. Check `_process()` for more info.

        :return: http response object

        :raises requests.RequestException: server error on operation (if raise_for_status is True)
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

        :param str path: url path, will be combined with ``self.host`` to build whole request url
        :param str request_category: (optional) category for log and metric reporting, can be set on client init
        :param int max_retries: (optional) number of retries if the execution fail with server error
        :param bool report: (optional) report request exceptions to error_lib.swallow
        :param float sleep_before_repeat: (optional) seconds to sleep before another retry
        :param list tags: (optional) tags for Datadog
        :param bool raise_for_status: (optional) raise an exception in case of an error response
        :param \*\*request_kwargs: Optional arguments that request takes. Check `_process()` for more info.

        :return: http response object

        :raises requests.RequestException: server error on operation (if raise_for_status is True)
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

        :param str path: url path, will be combined with ``self.host`` to build whole request url
        :param str request_category: (optional) category for log and metric reporting, can be set on client init
        :param int max_retries: (optional) number of retries if the execution fail with server error
        :param bool report: (optional) report request exceptions to error_lib.swallow
        :param float sleep_before_repeat: (optional) seconds to sleep before another retry
        :param list tags: (optional) tags for Datadog
        :param bool raise_for_status: (optional) raise an exception in case of an error response
        :param \*\*request_kwargs: Optional arguments that request takes.  Check `_process()` for more info.

        :return: http response object

        :raises requests.RequestException: server error on operation (if raise_for_status is True)
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

        :param str path: url path, will be combined with ``self.host`` to build whole request url
        :param str request_category: (optional) category for log and metric reporting, can be set on client init
        :param int max_retries: (optional) number of retries if the execution fail with server error
        :param bool report: (optional) report request exceptions to error_lib.swallow
        :param float sleep_before_repeat: (optional) seconds to sleep before another retry
        :param list tags: (optional) tags for Datadog
        :param bool raise_for_status: (optional) raise an exception in case of an error response
        :param \*\*request_kwargs: Optional arguments that request takes.  Check `_process()` for more info.

        :return: http response object

        :raises requests.RequestException: server error on operation (if raise_for_status is True)
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
        :param str request_category: (optional) category for log and metric reporting, can be set on client init
        :param int max_retries: number of retries if the execution fail with server error
        :param bool report: report request exceptions to error_lib.swallow
        :param float sleep_before_repeat: seconds to sleep before another retry
        :param list tags: tags for Datadog
        :param bool raise_for_status: raise an exception in case of an error response
        :param \*\*request_kwargs: Optional arguments that request takes:

            * url: (optional) to override ``url`` param.
            * params: (optional) Dictionary or bytes to be sent in the query string for the Request.
            * data: (optional) Dictionary or list of tuples ``[(key, value)]`` (will be form-encoded), bytes,
                    or file-like object to send in the body of the Request.
            * json: (optional) A JSON serializable Python object to send in the body of the Request.
            * headers: (optional) Dictionary of HTTP Headers to send with the Request.
            * cookies: (optional) Dict or CookieJar object to send with the Request.
            * files: (optional) Dictionary of ``'name': file-like-objects``
            * auth: (optional) Auth tuple to enable Basic/Digest/Custom HTTP Auth.
            * timeout: (optional) How many seconds to wait for the server to send data
                    before giving up, as a float, or a :ref:`(connect timeout, read
                    timeout) <timeouts>` tuple.
            * allow_redirects: (optional) Boolean. Enable/disable GET/OPTIONS/POST/PUT/PATCH/DELETE/HEAD redirection.
                    Defaults to ``True``.
            * proxies: (optional) Dictionary mapping protocol to the URL of the proxy.
            * verify: (optional) Either a boolean, in which case it controls whether we verify
                    the server's TLS certificate, or a string, in which case it must be a path
                    to a CA bundle to use. Defaults to ``True``.
            * stream: (optional) if ``False``, the response content will be immediately downloaded.
            * cert: (optional) if String, path to ssl client cert file (.pem). If Tuple, ('cert', 'key') pair.

        :return: http response object

        :raises requests.RequestException: server error on operation (if raise_for_status is True)
        :raises APIError: client error on operation (if raise_for_status is True)
        """
        if not tags:
            tags = []

        request_params = {"url": url, "timeout": self.timeout, "verify": self.verify, "params": None}  # type: Dict
        request_params.update(request_kwargs)

        response = None
        max_runs = 1 + (self.max_retries if max_retries is None else max_retries)
        request_category = self._get_request_category(request_category)
        raise_for_status = raise_for_status if raise_for_status is not None else self.raise_for_status

        run, retries_on_econnreset = 0, 0
        # this will set maximum number of retries to max_runs where econnreset retries are not counting and maximum number of of retries on econnreset is also set to max_runs
        while run < max_runs + retries_on_econnreset:
            run += 1
            try:
                metric_name = "{metric_base}.response_time".format(metric_base=request_category)
                with statsd.timed(metric_name, use_ms=True, tags=tags):
                    response = self.session.request(method=request_type, **request_params)

                response.raise_for_status()

                success_tags = list(tags) if tags else []
                success_tags.extend(["status:success", "attempt:{attempt}".format(attempt=run)])
                self.metric_increment(metric="request", request_category=request_category, tags=success_tags)

                extra_params = (
                    {"request_params": json.dumps(request_params), "response_text": self.get_response_text(response)}
                    if self.verbose_logging
                    else {}
                )
                extra_params = self.split_tags(extra_params, success_tags)
                log.info(
                    "requestsession.{}".format(request_category),
                    response_status_code=response.status_code,
                    **extra_params
                )

            except requests.RequestException as error:
                error_tags = list(tags) if tags else []
                error_tags.extend(["attempt:{attempt}".format(attempt=run)])  # type: list

                status_code = self._get_status_code(response)

                self.exception_log_and_metrics(error, request_category, request_params, error_tags, status_code)

                if self.is_server_error(error, status_code):
                    if isinstance(error, requests.exceptions.ConnectionError) and "ECONNRESET" in str(error):
                        log.info("requestsession.{}.session_replace".format(request_category))
                        self.remove_session()
                        self.prepare_new_session()

                        retries_on_econnreset += 1

                    # try again in case of ECONNRESET, even for api client with 0 retries
                    if (
                        run == max_runs + retries_on_econnreset or max(max_runs, 2) == retries_on_econnreset
                    ):  # failed on last try
                        if raise_for_status:
                            error_lib.reraise_as_third_party()
                        return response

                else:
                    # Client error, request is not valid and server rejected it with http 4xx, but not timeout
                    # No point in retry
                    if report:
                        response_text = self.get_response_text(response)
                        extra_data = {"response_text": response_text} if response_text != "" else None
                        sentry_client.captureException(extra=extra_data)

                    if raise_for_status:
                        raise APIError(str(error), original_exc=error)
                    return response

                if sleep_before_repeat:
                    self.sleep(sleep_before_repeat, request_category, tags)

            else:
                return response

        return None

    @staticmethod
    def split_tags(dictionary, tags):
        dictionary.update(dict(tag.split(":", 1) for tag in tags))  # type: ignore
        return dictionary

    def sleep(self, seconds, request_category, tags):
        # type: (float, str, List[str]) -> None
        """Call sleep function and send metrics to datadog.

        :param float seconds: float or int number of seconds to sleep
        :param request_category: request category for datadog
        :param tags: tags for datadog

        :return: None
        """
        trace_name = request_category.replace(".", "_") + "_retry"
        meta = {"request_category": request_category}
        meta = self.split_tags(meta, tags)
        traced_sleep(trace_name, seconds, meta=meta)

    @staticmethod
    def metric_increment(metric, request_category, tags):
        # type: (str, str, list) -> None
        """Metric request increment."""
        metric_name = "{metric_base}.{metric_type}".format(metric_base=request_category, metric_type=metric)
        statsd.increment(metric_name, tags=tags)

    @staticmethod
    def log_exception(error, error_type, request_category, status_code, **details):
        # type: (str, str, str, Optional[int], **str) -> None
        """Log request exception."""
        event_name = "{error_base}.{error}".format(error_base=request_category, error=error)
        log.exception(event_name, error_type=error_type, status_code=status_code, **details)

    def exception_log_and_metrics(self, error, request_category, request_params, dd_tags, status_code):
        # type: (requests.RequestException, str, Dict,  list, Optional[int]) -> None
        """Assign appropriate metric and log for exception."""
        tags = ["status:error"]
        tags.extend(dd_tags)
        response_text = self.get_response_text(error.response)
        extra_params = {"description": str(error), "response_text": response_text}
        extra_params = self.split_tags(extra_params, tags)

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

        self.log_exception("failed", error_type, request_category, status_code, **extra_params)
        self.metric_increment(metric="request", request_category=request_category, tags=tags)

    @staticmethod
    def is_server_error(error, http_code):
        # type: (requests.RequestException, Optional[int]) -> bool
        """Exception type and response code match server error."""

        if not isinstance(error, requests.exceptions.HTTPError):
            return True

        if http_code is not None and (400 <= http_code < 500 and not http_code == 408):
            return False

        return True

    @staticmethod
    def _get_status_code(response):
        # type: (Optional[requests.Response]) -> Optional[int]
        """Get status code from response."""

        # Danger: do not use `if response:` syntax
        #  bool(response) for `Response` instances with status in range > 400 returns `False`
        # check `def __bool__(self):` in `requests.models.Response`
        if response is None:
            return None

        return response.status_code

    @staticmethod
    def get_response_text(response):
        # type: (requests.Response) -> str
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
