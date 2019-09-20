# request_session

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Python: 3.7](https://img.shields.io/badge/python-3.7-green.svg)](https://python.org)
[![Python: 3.6](https://img.shields.io/badge/python-3.6-green.svg)](https://python.org)
[![Python: 2.7](https://img.shields.io/badge/python-2.7-green.svg)](https://python.org)

**RequestSession** is a helper class built on top of the `requests.Session`
to help with default configuration, automatic retry, logging and metrics.
Every call to `GET` or `POST` methods will generate logs and metrics.

## Usage

To install `request_session`, use pip:

```bash
pip install request_session
```

```python
# file.py

from kw.request_session import RequestSession

client = RequestSession(
    host="jobs.kiwi.com",
    max_retries=4,
    timeout=20,
    raise_for_status=True,
)
response = client.get("jobs.kiwi.com", tags=["get:jobs.kiwi.com"])
```

Some benefits of using `request_session`:

- Metrics: On each call you make to `GET` and `POST` methods several metrics are sent.

- Logs: Each exception on the request can be logged.

- Retry: It is possible to configure a retry in case of request failure.

## Contributing

Create a merge request and assign it to Josef Podaný for review.

## How to run test

To run all tests you just need to run the command `tox`.

> Note that tox doesn't know when you change the `requirements.txt`
> and won't automatically install new dependencies for test runs.
> Run `pip install tox-battery` to install a plugin which fixes this silliness.
