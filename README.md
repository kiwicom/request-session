# request_session

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Python: 3.7](https://img.shields.io/badge/python-3.7-green.svg)](https://python.org)
[![Python: 3.6](https://img.shields.io/badge/python-3.6-green.svg)](https://python.org)
[![Python: 2.7](https://img.shields.io/badge/python-2.7-green.svg)](https://python.org)

**RequestSession** is an HTTP library built on top of [`requests`](https://requests.kennethreitz.org/en/master/)
that makes your live easier by retrying whenever a request fails,
logs the results or even sends metrics to DataDogHQ.
**RequestSession** can measure the time of the request.

## Usage

To install `request_session`, use pip:

```bash
pip install request_session
```

```python
from request_session import RequestSession

client = RequestSession(
    host="https://jobs.kiwi.com",
    max_retries=4,          # how many times to retry in case server error occurs
    raise_for_status=True,  # raise an error if failed on every attempt
)

response = client.get(
    path="/",
    sleep_before_repeat=1,      # how long to wait untill next try  
    tags=["get:jobs.kiwi.com"], # tags to send to DataDogHQ
    request_category="jobs",    # what to log to stdout/stderr
)
```

Some benefits of using `RequestSession`:

- Metrics: On each call you make to `GET`, `POST`, `PUT` and `DELETE` methods,
  several metrics are sent. (Duration of the request, how many requests were sent)

- Logs: Each exception on the request can be logged.

- Retry: It is possible to configure a retry in case of request failure.

## Contributing

Create a merge request and assign it to Josef Podaný for review.

## How to run test

To run all tests you just need to run the command `tox`.

> Note that tox doesn't know when you change the `requirements.txt`
> and won't automatically install new dependencies for test runs.
> Run `pip install tox-battery` to install a plugin which fixes this silliness.
