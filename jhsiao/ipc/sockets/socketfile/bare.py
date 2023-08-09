__all__ = ['bind', 'connect', 'BindError', 'ConnectError', 'MultiError']
import socket

class MultiError(Exception):
    def __init__(self, *args):
        super(MultiError, self).__init__(*args)

    def __str__(self):
        return '\n\t'.join(map(str, self.args))

class ConnectError(MultiError):
    pass

class BindError(MultiError):
    pass

def bind(addr, timeout=5):
    """Return a bound socket.

    addr: address to bind to.
        str: A unix socket name. (Force to abstract if not already)
        pair of (str, port): ip, port. Random port if port is 0.
    timeout:
        The binding timeout and timeout of returned socket.
    """
    if isinstance(addr, str):
        if not addr.startswith('\0'):
            addr = '\0' + addr
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.bind(addr)
            return sock
        except Exception as e:
            raise BindError(e)
    else:
        host, port = addr[:2]
        errors = []
        for aftype, socktype, proto, cannon, addr in socket.getaddrinfo(
                host, port, 0, 0, 0, 0):
            try:
                s = socket.socket(aftype, socktype, proto)
            except Exception as e:
                errors.append(e)
                continue
            try:
                s.settimeout(timeout)
                if aftype == socket.AF_INET and addr[0] == '':
                    addr = ('0.0.0.0', addr[1])
                s.bind(addr[:2])
                return s
            except Exception as e:
                errors.append(e)
                continue
        raise BindError(*errors)

def connect(addr, timeout=5):
    """Return a connected socket.

    addr: address to connect to.
        str: A unix socket name. (Forced to abstract if not already)
        pair of (str, port): ip, port.
    timeout:
        The connecting timeout.  Also used as the returned socket timeout.
    """
    if isinstance(addr, str):
        if not addr.startswith('\0'):
            addr = '\0' + addr
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(addr)
            return sock
        except Exception as e:
            raise ConnectError(e)
    else:
        errors = []
        host, port = addr[:2]
        for aftype, socktype, proto, cannon, addr in socket.getaddrinfo(
                host, port, 0, 0, 0, 0):
            try:
                s = socket.socket(aftype, socktype, proto)
            except Exception as e:
                errors.append(e)
                continue
            try:
                s.settimeout(timeout)
                if aftype == socket.AF_INET6 and addr[0] == '::':
                    addr = ('::1', addr[1])
                elif aftype == socket.AF_INET and addr[0] in ('', '0.0.0.0', 'localhost'):
                    addr = ('127.0.0.1', addr[1])
                s.connect(addr[:2])
                return s
            except Exception as e:
                errors.append(e)
                s.close()
                continue
        raise ConnectError(*errors)
