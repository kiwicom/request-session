"""Utilites used in RequestSession."""
import logging
from contextlib import contextmanager

import attr

DATEFMT = "%Y-%m-%d %H:%M.%S"
FORMAT = "%(asctime)s %(message)s\t  %(tags)s "


logging.basicConfig(format=FORMAT, datefmt=DATEFMT)
logger = logging.getLogger()


@attr.s
class UserAgentComponents(object):
    """Helper class to wrap user-agent items into one object."""

    service_name = attr.ib(validator=[attr.validators.instance_of(str)], type=str)
    version = attr.ib(validator=[attr.validators.instance_of(str)], type=str)
    organization = attr.ib(validator=[attr.validators.instance_of(str)], type=str)
    environment = attr.ib(validator=[attr.validators.instance_of(str)], type=str)
    sys_info = attr.ib(None, type=str)


class InvalidUserAgentString(Exception):
    """Provided user agent string is not in correct format."""


class APIError(Exception):
    """Base error for API mishandling."""

    default_message = "API error occured."

    def __init__(self, *args, **kwargs):
        if not args:
            args = (self.default_message,)
        self.original_exc = kwargs.get("original_exc")

        Exception.__init__(self, *args)


@contextmanager
def null_context_manager(*args, **kwargs):
    """Do nothing."""
    yield


def reraise_as_third_party(sys):
    setattr(sys.exc_info()[1], "__sentry_source", "third_party")
    setattr(sys.exc_info()[1], "__sentry_pd_alert", "disabled")


def split_tags_and_update(dictionary, tags):
    """Update dict with tags from string.

    Individual tags must be in format of <key>:<value>.
    """
    dictionary.update(dict(tag.split(":", 1) for tag in tags))  # type: ignore
    return dictionary


def dict_to_string(dictionary):
    """Convert dictionary to key=value pairs separated by a space."""
    return " ".join(
        [u"{}={}".format(key, value) for key, value in sorted(dictionary.items())]
    )
