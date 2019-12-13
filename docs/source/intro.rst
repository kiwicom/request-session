Introduction
============

**RequestSession** is an HTTP library built on top of requests_
that makes your life easier by retrying failed requests,
loging the results or even sends metrics to DataDogHQ.
RequestSession can also measure the time of requests.

Use `RequestSession` to create a client module for accessing
a group of resources served on a common endpoint with default
values valid for all or most of the calls you need to make.
For your convenience, some defaults are already provided.

.. _requests: https://requests.kennethreitz.org/en/master/

Installation
************

``request_session`` can be installed using
``pip install request-session``.

Basic Usage
***********

.. code-block:: python

    from request_session import RequestSession

    client = RequestSession(
        host="https://jobs.kiwi.com",
        max_retries=4,                  # how many times to retry in case server error occurs
        raise_for_status=True,          # raise an error if failed on every attempt
    )

    response = client.get(
        path="/",
        sleep_before_repeat=1,      # how long to wait untill next try
        tags=["get:jobs.kiwi.com"], # tags to send to DataDogHQ
        request_category="jobs",    # what to log to stdout/stderr
    )
