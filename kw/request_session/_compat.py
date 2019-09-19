"""Module ensuring lib compatibilty."""
from __future__ import absolute_import

import sys

if sys.version_info[0] < 3:
    from urlparse import urljoin  # pylint: disable=unused-import,import-error
else:
    from urrlib.parse import urljoin  # pylint: disable=unused-import,import-error
