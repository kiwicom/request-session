"""Module ensuring lib compatibilty."""
from __future__ import absolute_import

try:
    from urlparse import urljoin  # pylint: disable=unused-import,import-error
except ImportError:
    from urllib.parse import urljoin  # pylint: disable=unused-import,import-error
