Metrics
=======

In order to use this feature, you must have DataDog integration set up.

Everytime you call ``POST``, ``GET``, ``PUT`` or ``DELETE`` methods,
several metrics are sent. All metric names are composed from
``request_category`` parameter (either from object property or from
argument passed to the method):

- **response time** - ``booking.{request_category}.response_time``:

    Response time metric is used to time how long it took for a client
    to receive response (if any).

- **request status** - ``booking.{request_category}.request``:

    Request status metric is used to track the success status of the request.

    Status is tracked with two tag groups:

        - **status**:

            status can have 2 values: ``success`` or ``error``

        - **error** (optional):

            error tag is added to event only if request failed
            (status:error tag is present in the event) and it is used
            to describe error type in better detail.

            Possible values are:

                - ``timeout``: request has timed out
                - ``http_error``: server has responded http 4xx or 5xx
                - ``connection_error``: connection to server failed
                - ``request_exception``: other

    Bear in mind that ``statsd.namespace`` can be used in order to
    prepend desired prefix to the metric, e.g. setting
    ``statsd.namespace = "prefix"`` and calling
    ``metric_increment(metric="metric", request_category="category")`` will
    produce ``prefix.category.metric`` instead of ``category.metric``.

    Additionally, you can include you own tags that will be appended to
    metric tags.

Example of Sending Metrics
**************************

To send metrics to DataDogHQ, just pass the ``statsd`` and ``dd-trace``
packages to the object ``RequestSession`` object:

.. code-block:: python

    import ddtrace
    import statsd
    from request_session import RequestSession

    # ...some setting up of statsd and ddtrace...

    client = RequestSession(
        host="https://google.com"
        request_category="google_search",
        max_retries=2,
        datadog_service_name="dd_service_name",
        ddtrace=ddtrace,
        statsd=statsd,
    )

    response = client.get(path="/some_path")
