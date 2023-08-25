"""
helper functions for binding or connecting to sockets, socket
manipulation, etc.

binding:
    unix: 'somepath'
    abstract unix: '\0someabstractpath'
    IPv4: ('ip address', portl), for all, use '0.0.0.0'
        and 'localhost' for localhost
        NOTE: on ubuntu, using '0' seems to be fine for getaddrinfo
        but on windows, '0' was giving errors, must be '0.0.0.0'
    IPv6: ('ipv6 address', port), for all, use '::', and '::1' for
        localhost
"""
from __future__ import print_function
__all__ = [
    'bind_inet',
    'connect_inet',
    'bind',
    'connect',
]

import os
import socket

from jhsiao.ipc.sockets import util, sockfile, listener

class MultiError(Exception):
    """All alternatives failed.

    errors attribute = list of exceptions, 1 per alternative.
    """
    def __str__(self):
        return ' | '.join(map(repr, self.args))

class BindError(MultiError):
    pass

class ConnectError(MultiError):
    pass

def bind_inet(
    host=None, port=0, family=0, tp=0, proto=0, flags=0,
    cloexec=True, reuse=True, nodelay=False, timeout=None):
    """Return a Listener bound to port.

    timeout will be used for accepted sockets as well as
    the listener socket itself.
    Falsey host is shorthand for ipv4 all interfaces '0.0.0.0'.
    """
    orig = host
    if isinstance(host, tuple):
        host, port = host[:2]
    if host == '':
        host = '0.0.0.0'
    addrs = socket.getaddrinfo(host, port, family, tp, proto, flags)
    errors = []
    cloexecflag = util.SOCK_CLOEXEC if cloexec else 0
    for af, socktype, proto, cannon, addr in addrs:
        try:
            s = socket.socket(af, socktype | util.SOCK_CLOEXEC, proto)
        except Exception as e:
            errors.append(e)
        else:
            try:
                util.set_cloexec(s, cloexec)
                s.setsockopt(
                    socket.SOL_SOCKET, socket.SO_REUSEADDR, int(reuse))
                if s.type == socket.SOCK_STREAM:
                    s.setsockopt(
                        socket.IPPROTO_TCP, socket.TCP_NODELAY,
                        int(nodelay))
                s.bind(addr[:2])
                s.settimeout(timeout)
                return listener.Listener(s, cloexec, nodelay, timeout)
            except Exception as e:
                s.close()
                errors.append(e)
    raise BindError(*errors)

class _ProxyWrap(sockfile.Sockfile):
    """Always read at most 1 byte to avoid consuming extra data.

    The main purpose is to just find the end of the proxy response.
    even if less efficient, this should only be used once per
    connection so it's fine if it isn't efficient.
    """
    def read(self, amt=None):
        return super(_ProxyWrap, self).read(1)
    def readinto(self, buf):
        return super(_ProxyWrap, self).readinto(memoryview(buf)[:1])

def _connect_proxy(proxy, host, port, *args):
    """simple use of proxy to connect to host/port.

    send basic CONNECT request, ignore headers.
    Return resulting socket.
    """
    if not isinstance(proxy, str):
        proxy = os.environ.get('https_proxy', os.environ.get('http_proxy'))
    if not proxy:
        return connect_inet(host, port, *args)
    pproto, addr = proxy.split('://', 1)
    phost, pport = addr.rsplit(':', 1)
    sock = connect_inet(phost, int(pport), *args)
    ok = False
    try:
        if pproto == 'http':
            # need to ensure that no extra data is read...
            # so only read absolute minimum to find end of headers
            sock.sendall(
                'CONNECT {}:{} HTTP/1.1\r\n\r\n'.format(
                    host, port).encode('utf-8'))
            f = _ProxyWrap(sock, 'rb')
            try:
                line = f.readline().decode('utf-8')
                version, code, reason = line.split(None, 2)
                if int(code) != 200:
                    raise ConnectionError('Proxy http error', reason)
                else:
                    for line in f:
                        if not (line and line.endswith(b'\r\n')):
                            break
                        elif line == b'\r\n':
                            ok = True
                            return sock
                    raise ConnectionError(
                        'Unrecognized proxy response:', line)
            finally:
                f.detach()
        elif pproto == 'https':
            # not implemented for now
            # would probably wrap in ssl or something
            pass
        raise NotImplementedError
    finally:
        if not ok:
            sock.close()


def connect_inet(
    hostOrAddr, port=None, family=0, tp=0, proto=0, flags=0,
    cloexec=True, nodelay=False, timeout=None, proxy=True):
    """Return socket connected to (host, port).

    hostOrAddr: tuple of (host,port) (like from getsockname()) or just
        host.
    port: port to bind to if hostOrAddr is just host.
    Falsey host is shorthand for ipv4 localhost '127.0.0.1'.
    proxy: use proxy? if str, then use that as proxy specification
        otherwise, if Truthy, search environment for
        http_proxy/https_proxy.
        If proxy fails, try to connect directly.
    """
    if port is None:
        # ipv6 gives a 4-tuple, only need the first 2
        host, port = hostOrAddr[:2]
    else:
        host = hostOrAddr
    if not host:
        host = '127.0.0.1'
    if proxy and host not in ('localhost', '127.0.0.1', '::'):
        return _connect_proxy(
            proxy, host, port, family, tp, proto, flags,
            cloexec, nodelay, timeout, False)
    addrs = socket.getaddrinfo(host, port, family, tp, proto, flags)
    errors = []
    cloexecflag = util.SOCK_CLOEXEC if cloexec else 0
    for af, socktype, proto, cannon, addr in addrs:
        try:
            s = socket.socket(af, socktype|cloexecflag, proto)
        except Exception as e:
            errors.append(e)
        else:
            try:
                util.set_cloexec(s, cloexec)
                if s.type == socket.SOCK_STREAM:
                    s.setsockopt(
                        socket.IPPROTO_TCP, socket.TCP_NODELAY,
                        int(nodelay))
                # Convert all interfaces to localhost.
                if af == socket.AF_INET6 and addr[0] == '::':
                    addr = ('::1', addr[1])
                elif af == socket.AF_INET and addr[0] == '0.0.0.0':
                    addr = ('127.0.0.1', addr[1])
                s.settimeout(timeout)
                s.connect(addr[:2])
                return s
            except Exception as e:
                s.close()
                errors.append(e)
    raise MultiError(errors)


if hasattr(socket, 'AF_UNIX'):
    import uuid
    __all__.extend(('bind_unix', 'connect_unix'))
    def bind_unix(
        fname=None, cloexec=True, timeout=None,
        socktype=socket.SOCK_STREAM, **kwargs):
        """Return a Listener unix socket(SOCK_STREAM).

        Use None for a randomly generated abstract unix socket address.
        """
        if fname is None:
            fname = '\x00' + uuid.uuid4().hex
        s = socket.socket(socket.AF_UNIX, socktype)
        try:
            if cloexec:
                util.set_cloexec(s, cloexec)
            s.bind(fname)
            s.settimeout(timeout)
        except Exception:
            s.close()
            raise
        return s

    def connect_unix(
        fname, cloexec=True, timeout=None,
        socktype=socket.SOCK_STREAM, **kwargs):
        """Return a connected unix socket."""
        s = socket.socket(socket.AF_UNIX, socktype)
        try:
            if cloexec:
                util.set_cloexec(s, cloexec)
            s.settimeout(timeout)
            s.connect(fname)
        except Exception:
            s.close()
            raise
        return s

def bind(value=None, **kwargs):
    """Return bound socket. Dispatch to bind_*.

    value: The bind specification.
        None: Try unix socket, fallback to random inet socket
        (ip, port): bind_inet
        str:
            'host:port': (contains 1 colon): parse into (ip, port) and
                bind_inet
            otherwise bind_unix
    """
    if value is None:
        # prefer unix over inet
        try:
            return bind_unix(**kwargs)
        except NameError:
            return bind_inet(**kwargs)
    if isinstance(value, str):
        parts = value.split(':')
        if len(parts) == 2:
            host, port = parts
            return bind_inet((host, int(port)), **kwargs)
        else:
            return bind_unix(value, **kwargs)
    else:
        return bind_inet(value, **kwargs)

def connect(value, **kwargs):
    """Return connected socket. Dispatch to connect_*."""
    if isinstance(value, str):
        parts = value.split(':')
        if len(parts) == 2:
            host, port = parts
            return connect_inet((host, int(port)), **kwargs)
        else:
            return connect_unix(value, **kwargs)
    else:
        return connect_inet(value, **kwargs)
