"""Test the utilities."""
import sys
from typing import Dict, List

import pytest

from request_session.protocols import Ddtrace
from request_session.utils import (
    dict_to_string,
    reraise_as_third_party,
    split_tags_and_update,
    traced_sleep,
)

from ._compat import Mock


def test_reraise_as_third_party(mocker):
    # type: (Mock) -> None
    mock_sys = mocker.patch("request_session.utils.sys", spec_set=sys)
    reraise_as_third_party()

    assert mock_sys.exc_info()[1].__sentry_source == "third_party"
    assert mock_sys.exc_info()[1].__sentry_pd_alert == "disabled"


@pytest.mark.parametrize(
    "dictionary, tags, expected",
    [
        ({}, ["key:value"], {"key": "value"}),
        ({"key1": "value1"}, ["key2:value2"], {"key1": "value1", "key2": "value2"}),
    ],
)
def test_split_tags_and_update(dictionary, tags, expected):
    # type: (Dict[str, str], List[str], Dict[str, str]) -> None
    split_tags_and_update(dictionary, tags)
    assert dictionary == expected


@pytest.mark.parametrize(
    "dictionary, expected",
    [
        ({"key": "value"}, "key=value"),
        ({"key1": "value1", "key2": "value2"}, "key1=value1 key2=value2"),
        ({}, ""),
    ],
)
def test_dict_to_string(dictionary, expected):
    # type: (Dict[str, str], str) -> None
    assert dict_to_string(dictionary) == expected


def test_traced_sleep(mocker):
    # type: (Mock) -> None
    seconds = 1
    request_category = "request_category"
    meta = {"request_category": request_category, "testing": "sleep"}
    mock_ddtrace = mocker.MagicMock(spec_set=Ddtrace)
    mock_span = mocker.Mock()
    mock_ddtrace.tracer.trace.return_value.__enter__.return_value = mock_span
    mock_time = mocker.patch("request_session.utils.time", autospec=True)

    traced_sleep(request_category, seconds, mock_ddtrace, meta)

    mock_ddtrace.tracer.trace.assert_called_once_with(request_category, service="sleep")

    mock_span.set_metas.assert_called_once_with(meta)
    mock_time.sleep.assert_called_once_with(seconds)
