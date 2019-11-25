Logging
=======

Each exception occurring on the request can be logged.
There are 2 implied levels of exceptions: error and warning.
An exception that happened on the last try is treated
as an error and is *always* logged.
An exception that happened on a try that can be repeated is
treated as a warning and it is ignored if parameter ``report``
in the method call is set to ``False``.

RequestSession allows you to pass in your own custom logger
to be used for logging information,
even though we encourage you to use ``structlog``.
If you want to provide your own logger,
be sure that the logger has all the following methods implemented:
``debug, info, warning, error, critical, exception, log``

The format of log events is ``{log_prefix}.{request_category}.{postfix}``,
where ``log_prefix`` and ``request_category`` are user specified,
but ``postfix`` will be generated depending on the outcome of the request.

- ``log_prefix`` is usually the name of your application

- ``request_category`` is usually the name of the request you are making

- ``postfix`` may be empty if the request was successful,
  ``failed`` if request failed or ``session_replace``
  if the request failed and the connection has been reset.

Parameters of the logged event:

- **error_type**:

    always present in event and provides context of the error with
    possible values:

        - ``read_timeout``: request has timed out
        - ``http_error``: server has responded http 4xx or 5xx
        - ``connection_error``: connection to server failed
        - ``request_exception``: other

- **description**:

    ``description`` contains string representation of the
    ``requests.exception``

- **text**:

    ``text`` may contain response text in case of ``http error``
    if it had any text

- **request_params** (optional):

    if attribute ``verbose_logging`` of the instance is set to ``True``,
    event will also contain request parameters passed to request

You can pass your own logger to the object to be used as long as
it supports all neccesary methods described in
``RequestSession.allowed_log_levels``, e.g. ``structlog``.


Examples of logging
********************

Let's say we have a request that can be repeated:

- the request times out on a first try
- we repeat the request successfully this time

In this case we reached the final goal, the request was successfully
transferred, even if it needed a push. The exception report can
be informative so we can log it as warning.

The scenario above will look like this:

.. code-block:: python

    from request_session import RequestSession
    import structlog

    log = structlog.get_logger()

    client = RequestSession(
        host="http://some-url.org",
        request_category="retry-showcase",
        logger=log,
        log_prefix="demo",
    )
    client.get("/specific/path", sleep_before_repeat=1, max_retries=2, raise_for_status=False)

.. code-block:: bash

    2019-11-15 09:17.58 demo.retry-showcase.failed            attempt=1 description=408 Client Error: REQUEST TIMEOUT for url: http://some-url.org/specific/path error_type=http_error response_text= status=error status_code=408
    2019-11-15 09:17.59 demo.retry-showcase                   status=success status_code=300

In another example, we have a request that can be repeated:

- the request times out on a first try
- we repeat the request and it times out again,
  eventually reaching the maximum number of retries

In this case we did not reach the final goal, the request failed.
The first failure can be logged as a warning,
but second failure was critical and will always
be logged as an error.
