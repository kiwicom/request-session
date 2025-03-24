"""Just a conftest."""

import http.server
import socketserver
import threading

import pytest

from request_session import RequestSession


class TestHandler(http.server.SimpleHTTPRequestHandler):
    """Custom HTTP request handler for testing."""

    def do_GET(self):
        """Handle GET requests."""
        if self.path.startswith("/status/"):
            status_code = int(self.path.split("/")[2])
            self.send_response(status_code)
            self.end_headers()
            self.wfile.write(b"")
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

    def do_POST(self):
        """Handle POST requests."""
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def do_PUT(self):
        """Handle PUT requests."""
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def do_DELETE(self):
        """Handle DELETE requests."""
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def do_PATCH(self):
        """Handle PATCH requests."""
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")


@pytest.fixture(scope="function")
def test_server():
    """Start a test HTTP server."""
    port = 0  # Let the OS choose a free port
    handler = TestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        port = httpd.socket.getsockname()[1]
        thread = threading.Thread(target=httpd.serve_forever)
        thread.daemon = True
        thread.start()
        yield f"http://localhost:{port}"
        httpd.shutdown()
        httpd.server_close()
        thread.join()


@pytest.fixture(scope="function")
def request_session(test_server):  # pylint: disable=redefined-outer-name
    """Create a RequestSession instance for testing."""

    def inner(*args, **kwargs):
        return RequestSession(
            *args, host=test_server, request_category="test", **kwargs
        )

    return inner
