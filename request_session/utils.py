"""Utilites used in RequestSession."""
import logging
import sys
import time
from typing import Any, Dict, Iterator, List, Optional, Text

from .protocols import Ddtrace


class UserAgentComponents(object):
    """Helper class to wrap user-agent items into one object."""

    def __init__(self, service_name, version, organization, environment, sys_info=None):
        # type: (str, str, str, str, Optional[str]) -> None
        self.service_name = service_name
        self.version = version
        self.organization = organization
        self.environment = environment
        self.sys_info = sys_info


def reraise_as_third_party():
    # type: () -> None
    """Add tags to raised exception for Sentry."""
    setattr(sys.exc_info()[1], "__sentry_source", "third_party")
    setattr(sys.exc_info()[1], "__sentry_pd_alert", "disabled")


def split_tags_and_update(dictionary, tags):
    # type: (Dict[str, str], List[str]) -> None
    """Update dict with tags from string.

    Individual tags must be in format of <key>:<value>.
    """
    dictionary.update(dict(tag.split(":", 1) for tag in tags))  # type: ignore


def dict_to_string(dictionary):
    # type: (Dict[str, Any]) -> Text
    """Convert dictionary to key=value pairs separated by a space."""
    return " ".join(
        [u"{}={}".format(key, value) for key, value in sorted(dictionary.items())]
    )


def traced_sleep(trace_name, seconds, ddtrace, meta=None):
    # type: (str, float, Ddtrace, Optional[dict]) -> None
    """Sleep function that is traced in datadog.

    :param str trace_name: the name of the operation being traced
    :param float seconds: seconds param for sleep()
    :param dict meta: meta tags to be added to trace e.g. `{"caller": "create_connection"}`

    :return: None
    """
    with ddtrace.tracer.trace(trace_name, service="sleep") as span:
        if meta:
            span.set_metas(meta)
        time.sleep(seconds)
