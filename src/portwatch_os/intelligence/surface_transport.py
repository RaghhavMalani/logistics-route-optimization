"""Persistent, verified HTTPS transport for the scheduled Open-Meteo collector."""

from dataclasses import dataclass
from http.client import HTTPSConnection, HTTPException
import socket
import ssl
from threading import Lock
from time import monotonic
from urllib.parse import urlencode


CONNECT_TIMEOUT = 3
READ_TIMEOUT = 8
MAX_RESPONSE_BYTES = 1024 * 1024


class SurfaceConnectTimeout(TimeoutError):
    """TCP or TLS timed out before an HTTP request could be sent."""


class SurfaceTransportError(RuntimeError):
    """An HTTP or transport failure without exposing request internals."""

    def __init__(self, kind):
        super().__init__(kind)
        self.kind = kind


@dataclass(frozen=True)
class SurfaceResponse:
    status: int
    retry_after: str | None
    content: bytes


class SurfaceConnection(HTTPSConnection):
    def __init__(self, host):
        self.context = ssl.create_default_context()
        self.context.set_alpn_protocols(["http/1.1"])
        # Native-cert adapters can require a full chain at every handshake.
        self.can_resume = type(self.context).__module__ == "ssl"
        super().__init__(host, timeout=CONNECT_TIMEOUT, context=self.context)
        self.session = None
        self.address_index = 0

    def connect(self):
        deadline = monotonic() + CONNECT_TIMEOUT
        answers = socket.getaddrinfo(self.host, self.port, socket.AF_INET, socket.SOCK_STREAM)
        addresses = sorted({answer[4] for answer in answers})
        if not addresses:
            raise socket.gaierror("No IPv4 address for Open-Meteo surface")
        address = addresses[self.address_index % len(addresses)]
        self.address_index += 1
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as raw:
            try:
                raw.settimeout(self._remaining(deadline))
                raw.connect(address)
                raw.settimeout(self._remaining(deadline))
                tls = self.context.wrap_socket(raw, server_hostname=self.host, session=self.session)
            except TimeoutError as error:
                raise SurfaceConnectTimeout("Open-Meteo TCP/TLS timed out") from error
        tls.settimeout(READ_TIMEOUT)
        self.sock = tls

    @staticmethod
    def _remaining(deadline):
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError("TCP/TLS budget expired")
        return remaining


class SurfaceTransport:
    def __init__(self):
        self.connection = SurfaceConnection("api.open-meteo.com")
        self.lock = Lock()

    def fetch(self, params):
        with self.lock:
            return self._fetch(params)

    def _fetch(self, params):
        connection = self.connection
        try:
            connection.request("GET", "/v1/forecast?" + urlencode(params),
                               headers={"User-Agent": "PortWatch-Capstone/1.0"})
            tls = connection.sock
            with connection.getresponse() as response:
                session_at_headers = tls.session if connection.can_resume else None
                content = response.read(MAX_RESPONSE_BYTES + 1)
                if len(content) > MAX_RESPONSE_BYTES:
                    raise SurfaceTransportError("response_too_large")
                if connection.can_resume:
                    connection.session = tls.session or session_at_headers
                return SurfaceResponse(response.status, response.getheader("Retry-After"), content)
        except SurfaceConnectTimeout:
            connection.close()
            raise
        except TimeoutError as error:
            connection.close()
            raise SurfaceTransportError("http_timeout") from error
        except (OSError, HTTPException, SurfaceTransportError) as error:
            connection.close()
            if isinstance(error, SurfaceTransportError):
                raise
            raise SurfaceTransportError(type(error).__name__) from error
