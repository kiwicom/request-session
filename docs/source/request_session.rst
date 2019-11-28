request_session package
========================

request\_session
----------------------------------------

.. automodule:: request_session.request_session
   :members:
   :undoc-members:
   :show-inheritance:

Additional ``requests`` parameters
##################################

Since ``RequestSession`` uses ``requests.Session``,
you can pass any parameters that ``requests.Session``
takes to any of the ``GET``, ``POST``, ``PUT`` and ``DELETE``
methods as a keyword argument:

* url: (*optional*) To override ``url`` param.

* params: (*optional*) Dictionary or bytes to be sent in the query string for
  the Request.

* data: (*optional*) Dictionary or list of tuples ``[(key, value)]``
  (which is form-encoded by requests_), bytes, or file-like object to send
  in the body of the Request.

* json: (*optional*) A JSON serializable Python object to send in the body of
  the Request.

* headers: (*optional*) Dictionary of HTTP Headers to send with the Request.

* cookies: (*optional*) Dict or CookieJar object to send with the Request.

* files: (*optional*) Dictionary of ``'name': file-like-objects``

* auth: (*optional*) Auth tuple to enable Basic/Digest/Custom HTTP Auth.

* timeout: (*optional*) How many seconds to wait for the server to send data
  before giving up, as a float, or a ``(connect timeout, read timeout)
  <timeouts>`` tuple.

* allow_redirects: (*optional*) Boolean.
  Enable/disable GET/OPTIONS/POST/PUT/PATCH/DELETE/HEAD redirection.
  Defaults to ``True``.

* proxies: (*optional*) Dictionary mapping protocol to the URL of the proxy.

* verify: (*optional*) Can be either:

  * A boolean, in which case it controls whether we
    verify the TLS certificate of the server.

  * A string, in which case it must be a path to
    a CA bundle to use. Defaults to ``True``.

* stream: (*optional*) If it is ``False``, the response content is immediately
  downloaded.

* cert: (*optional*) If it is a ``String``, path to ssl client cert file (.pem).
  If it is a ``Tuple``, ('cert', 'key') pair.

protocols
---------------------------------

.. automodule:: request_session.protocols
   :members:
   :undoc-members:
   :show-inheritance:


utilities
-----------------------------

.. automodule:: request_session.utils
   :members:
   :undoc-members:
   :show-inheritance:

.. _requests: https://requests.kennethreitz.org/en/master/
