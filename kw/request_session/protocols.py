"""Simple protocols to duck type dependency injections."""
from abc import ABCMeta, abstractmethod
from typing import Any, Dict, List, Optional

import attr
from six import add_metaclass


@add_metaclass(ABCMeta)
class SentryClient(object):
    """SentryClient protocol."""

    def captureException(self, exc_info=None, **kwargs):
        # type: (Any, Any) -> None
        """Creates an event from an exception.

        >>> try:
        >>>     exc_info = sys.exc_info()
        >>>     client.captureException(exc_info)
        >>> finally:
        >>>     del exc_info

        If exc_info is not provided, or is set to True, then this method will
        perform the ``exc_info = sys.exc_info()`` and the requisite clean-up
        for you.

        ``kwargs`` are passed through to ``.capture``.
        """


@add_metaclass(ABCMeta)
class Tracer(object):
    """Statsd Tracer protocol."""

    def trace(self, name, service=None, resource=None, span_type=None):
        # type: (str, Optional[str], Optional[str], Optional[str]) -> Span
        """Return a span that will trace an operation called `name`.

        The context that created the span as well as the span parenting,
        are automatically handled by the tracing function.

        :param str name: the name of the operation being traced
        :param str service: the name of the service being traced. If not set,
                            it will inherit the service from its parent.
        :param str resource: an optional name of the resource being tracked.
        :param str span_type: an optional operation type.

        You must call `finish` on all spans, either directly or with a context
        manager::

            >>> span = tracer.trace('web.request')
                try:
                    # do something
                finally:
                    span.finish()

            >>> with tracer.trace('web.request') as span:
                    # do something

        Trace will store the current active span and subsequent child traces will
        become its children::

            parent = tracer.trace('parent')     # has no parent span
            child  = tracer.trace('child')      # is a child of a parent
            child.finish()
            parent.finish()

            parent2 = tracer.trace('parent2')   # has no parent span
            parent2.finish()
        """


@attr.s
@add_metaclass(ABCMeta)
class Span(object):
    """Span protocol."""

    tracer = attr.ib(None, type=Tracer)
    name = attr.ib(None, type=str)
    service = attr.ib(None, type=str)
    resource = attr.ib(None, type=str)
    span_type = attr.ib(None, type=str)
    trace_id = attr.ib(None, type=int)
    parent_id = attr.ib(None, type=int)
    span_id = attr.ib(None, type=int)
    start = attr.ib(None, type=int)
    context = attr.ib(None, type=object)

    def set_metas(self, kvs):
        # type: (Any) -> None
        """Set metas."""

    def __enter__(self):
        # type: () -> Span
        pass

    def __exit__(self, *args, **kwargs):
        # type: (*Any, **Any) -> None
        pass


@add_metaclass(ABCMeta)
class Config(object):
    """Statsd Config protocol."""

    def get_from(self, obj):
        # type: (Any) -> Any
        """Retrieves the configuration for the given object.

        Any object that has an attached `Pin` must have a configuration
        and if a wrong object is given, an empty `dict` is returned
        for safety reasons.
        """


@add_metaclass(ABCMeta)
class Ddtrace(object):
    """Ddtrace protocol."""

    config = None  # type: Config
    tracer = None  # type: Tracer


@add_metaclass(ABCMeta)
class Statsd(object):
    """Statsd protocol."""

    def increment(self, metric, value=1, tags=None, sample_rate=1):
        # type: (str, int, List[str], int) -> None
        """Increment a counter, optionally setting a value, tags and a sample rate.

        >>> statsd.increment('page.views')
        >>> statsd.increment('files.transferred', 124)
        """

    def timed(self, metric=None, tags=None, sample_rate=1, use_ms=None):
        # type: (str, List[str], int, bool) -> TimedContextManagerDecorator
        """A decorator or context manager that will measure the distribution of a function's/context's run time.

        Optionally specify a list of tags or a
        sample rate. If the metric is not defined as a decorator, the module
        name and function name will be used. The metric is required as a context
        manager.
        ::

            @statsd.timed('user.query.time', sample_rate=0.5)
            def get_user(user_id):
                # Do what you need to ...
                pass

            # Is equivalent to ...
            with statsd.timed('user.query.time', sample_rate=0.5):
                # Do what you need to ...
                pass

            # Is equivalent to ...
            start = time.time()
            try:
                get_user(user_id)
            finally:
                statsd.timing('user.query.time', time.time() - start)
        """


@add_metaclass(ABCMeta)
class TimedContextManagerDecorator(object):
    """TimedContextManagerDecorator protocol."""

    statsd = attr.ib(None, type=Statsd)
    metric = attr.ib(None, type=str)
    tags = attr.ib(None, type=List[str])
    sample_rate = attr.ib(None, type=int)
    use_ms = attr.ib(None, type=bool)
    elapsed = attr.ib(None, type=int)

    def __enter__(self):
        # type: () -> TimedContextManagerDecorator
        pass

    def __exit__(self, type, value, traceback):  # pylint: disable=redefined-builtin
        # type: (Any, Any, Any) -> None
        pass
