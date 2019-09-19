"""Utilites used in RequestSession."""
import logging

DATEFMT = "%Y-%m-%d %H:%M.%S"
FORMAT = "%(asctime)s %(message)s\t  %(tags)s "


logging.basicConfig(format=FORMAT, datefmt=DATEFMT)
logger = logging.getLogger()


def dict_to_string(dictionary):
    """Convert dictionary to key=value pairs separated by a space."""
    return " ".join(
        [u"{}={}".format(key, value) for key, value in sorted(dictionary.items())]
    )
