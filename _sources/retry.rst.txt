Automatic Retries
=================

It is possible to configure a retry in case of request failure.
The number of retries is set to 0 by default.
You can set the number of retries for all requests trough the object's attribute
``max_retries`` or you can pass the number as an optional parameter
``max_retries``. When calling an HTTP method.
The value passed trough method call has precedence.
The parameter is the number of retries on failure, not a maximum number of attempts.
E.g. if retry is set to 2 and there is no success on any attempt,
the total number of requests will be 3: nominal request and 2 retries on
failure.

Important note: the request  is not retried in case of client error,
that is if the server responded with HTTP 4xx,
not including HTTP 408 Request Timeout

If ``sleep_before_repeat`` parameter is passed,
the method waits for that amount of seconds before retrying.

Examples
********

.. code-block:: python

    from request_session import RequestSession
    import structlog

    logger = structlog.get_logger()

    client = RequestSession(
        host="http://httpbin.org/", # to showcase the usage, we're going to call httpbin
        prefix="demo",              # name of the app
        logger=logger,              # log information using structlog
    )

    client.get(
        "/status/500",              # all requests should fail with 500
        sleep_before_repeat=1,      # wait 1 second before retrying
        max_retries=2,              # if failed, retry twice
        request_category="httpbin") # use "httpbin" when logging

This setup generates the following logs:

.. code-block:: bash

    2019-11-15 08:52.25 demo.httpbin.failed             attempt=1 description=500 Server Error: INTERNAL SERVER ERROR for url: http://httpbin.org/status/500 error_type=http_error response_text= status=error status_code=500
    2019-11-15 08:52.26 demo.httpbin.failed             attempt=2 description=500 Server Error: INTERNAL SERVER ERROR for url: http://httpbin.org/status/500 error_type=http_error response_text= status=error status_code=500
    2019-11-15 08:52.27 demo.httpbin.failed             attempt=3 description=500 Server Error: INTERNAL SERVER ERROR for url: http://httpbin.org/status/500 error_type=http_error response_text= status=error status_code=500

From the logs, we can see that 3 requests have been made in total
(initial one and 2 retries),
from which all of them have failed.
