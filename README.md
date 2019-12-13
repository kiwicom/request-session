# request-session

[![Versions](https://img.shields.io/pypi/pyversions/request-session)](https://pypi.org/project/request-session/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**`request-session`** is an HTTP library built on top of [`requests`](https://requests.kennethreitz.org/en/master/)
that makes your live easier by retrying whenever a request fails,
logs the results or even sends metrics and traces to DataDogHQ.
**RequestSession** also measures the time of the request.

Use **`RequestSession`** to create a client module for accessing a group of resources
served on a common endpoint with default values valid for all or
most of the calls you need to make. For your convenience,
some defaults are already provided.

## Usage

To install `request-session`, use pip:

```bash
pip install request-session
```

```python
from request_session import RequestSession

client = RequestSession(
    host="https://jobs.kiwi.com",
    max_retries=4,          # how many times to retry in case server error occurs
    raise_for_status=True,  # raise an exception if failed on every attempt
)

response = client.get(
    path="/",
    sleep_before_repeat=1,      # how many seconds to wait untill next try  
    request_category="jobs",    # what to log to stdout/stderr
)
```

## Benefits of using `RequestSession`

* **Retry**: It is possible to configure a retry in case of request failure.
* **Logs**: Result of the request can also be logged to `stdout`.
* **Metrics**: On each call you make to `GET`, `POST`, `PUT`, `PATCH`, and
DELETE` methods, several metrics are sent to your datadog client -
duration of the request, how many requests were sent,
outcome of the request (a DataDog integration is needed).
* **Tracing**: `RequestSession` can send tracing info to DataDog
(an APM integration is needed).

You can find more details about `RequestSession`'s benefits and examples in
[the official documentation](https://readthedocs.com).

## Contributing

Create a merge request and assign it to Josef Podaný for review.

## How to run test

To run all tests you just need to run the command `tox`.

> Note that tox doesn't know when you change the `requirements.txt`
> and won't automatically install new dependencies for test runs.
> Run `pip install tox-battery` to install a plugin which fixes this silliness.
