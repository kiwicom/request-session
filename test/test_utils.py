"""Test the utilities."""
import pytest

from kw.request_session.utils import (
    dict_to_string,
    reraise_as_third_party,
    split_tags_and_update,
)


def test_reraise_as_third_party(mocker):
    mock_sys = mocker.MagicMock()
    reraise_as_third_party(mock_sys)

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
    assert split_tags_and_update(dictionary, tags) == expected


@pytest.mark.parametrize(
    "dictionary, expected",
    [
        ({"key": "value"}, "key=value"),
        ({"key1": "value1", "key2": "value2"}, "key1=value1 key2=value2"),
        ({}, ""),
    ],
)
def test_dict_to_string(dictionary, expected):
    assert dict_to_string(dictionary) == expected
