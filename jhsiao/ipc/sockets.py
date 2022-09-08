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
    'get_ip', 'Sockfile', 'Listener',
    'bind_inet', 'connect_inet', 'connect_proxy',
    'bind', 'connect'
]

import functools
import io
import os
import platform
import re
import socket
import subprocess
import sys

try:
    import errno
except ImportError:
    EAGAIN = 11
    EWOULDBLOCK = 10035 if platform.system() == 'Windows' else 11
else:
    EAGAIN = getattr(errno, 'EAGAIN', 11)
    EWOULDBLOCK = getattr(
        errno,
        'EWOULDBLOCK',
        10035 if platform.system() == 'Windows' else 11)

#------------------------------
# cloexec close socket in child processes
# example: without, child would keep server bound
#          if parent crashes, cannot rebind
#------------------------------
def set_cloexec():
    """Return a set_cloexec(sock, close) func."""
    if sys.version_info >= (3,4):
        def set_cloexec(sock, cloexec):
            """Set inheritability."""
            if sock.get_inheritable() != cloexec:
                sock.set_inheritable(cloexec)
    else:
        try:
            if platform.system() == 'Windows':
                from ctypes import windll, wintypes
                SetHandleInformation = windll.kernel32.SetHandleInformation
                SetHandleInformation.argtypes = [
                    wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD]
                SetHandleInformation.restype = wintypes.BOOL
                # from https://msdn.microsoft.com/en-us/library/windows/desktop/ms724935(v=vs.85).aspx
                HANDLE_FLAG_INHERIT = 1
                def set_cloexec(sock, cloexec):
                    """Set cloexec value for the socket."""
                    SetHandleInformation(
                        sock.fileno(), HANDLE_FLAG_INHERIT, 1-int(cloexec))
            else:
                import fcntl
                def set_cloexec(sock, cloexec):
                    """Set cloexec value for the socket."""
                    fd = sock.fileno()
                    flags = fcntl.fcntl(fd, fcntl.F_GETFD)
                    if cloexec:
                        flags |= fcntl.FD_CLOEXEC
                    else:
                        flags &= ~fcntl.FD_CLOEXEC
                    fcntl.fcntl(fd, fcntl.F_SETFD, flags)
        except:
            warned = []
            def set_cloexec(sock, cloexec):
                if not warned:
                    warned.append(0)
                    print(
                        ('WARNING: set_cloexec could not be defined'
                        ' and cloexec will not be set'),
                        file = sys.stderr)
    return set_cloexec
set_cloexec = set_cloexec()
SOCK_CLOEXEC = getattr(socket, 'SOCK_CLOEXEC', 0)
# If socket has SOCK_CLOEXEC, then socket.socket() always returns
# non-inheritable socket so adding SOCK_CLOEXEC doesn't change anything
# right? If it's not defined, then the returned socket might be
# inheritable, but it's not defined anyways which means it wouldn't
# affect socket.socket() anyways, not sure.

def _get_ip(cmd, header, search):
    """Return ips from header and search.

    Assume cmd output follows hanging indent conventions.
    cmd: commandline command to obtain ip info
    header: re.Pattern with 'device' group
    search: re.Pattern with 'ip' group
    """
    chunks = []
    data = subprocess.check_output(cmd).decode(sys.stdin.encoding)
    for line in data.splitlines():
        # ipconfig, ip, ifconfig all have
        # each section in similar format where 1st line is unindented
        # and following lines are
        if re.match(r'^\S', line):
            chunks.append([line])
        elif line.strip():
            chunks[-1].append(line)
    ret = {}
    for chunk in chunks:
        m = header.search(chunk[0])
        if m:
            name = m.group('device')
            ips = []
            for line in chunk[1:]:
                n = search.search(line)
                if n:
                    ips.append(n.group('ip'))
            if ips:
                ret[name] = ips
    return ret

def ipconfig(family='inet'):
    """Extract info from ipconfig."""
    winfam = {'inet': 'IPv4', 'inet6': 'IPv6'}[family]
    return _get_ip(
        ['ipconfig'],
        re.compile('adapter (?P<device>.*):'),
        re.compile('{} Address.*: (?P<ip>[a-fA-F0-9.:]+)'.format(winfam)))

def ifconfig(family='inet'):
    """Extract info from ifconfig."""
    return _get_ip(
        ['ifconfig'],
        re.compile('(?P<device>\\S+)'),
        re.compile('{} addr: ?(?P<ip>[a-fA-F0-9.:]+)'.format(family)))

def ipa(family='inet'):
    """Extract info from ip a."""
    return _get_ip(
        ['ip', 'a'],
        re.compile('\\d+: (?P<device>\\S+):'),
        re.compile('{} (?P<ip>[a-fA-F0-9.:]+)'.format(family)))

def default_ip(family='inet'):
    """Get ip info via udp broadcast."""
    if family == 'inet':
        fam, addr = socket.AF_INET, ('<broadcast>', 0)
    else:
        fam, addr = socket.AF_INET6, ('ffff::1', 80, 0, 0)
    try:
        s = socket.socket(fam, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.connect(addr)
        ret = s.getsockname()
        s.close()
        return ret[0]
    except Exception:
        return None

# NOTE: on windows, it seems like
# socket.getaddrinfo(socket.gethostname(), 0, socket.AF_INET) can return
# the ipv4 address and
# socket.getaddrinfo(socket.gethostname(), 0, socket.AF_INET6) can
# return the ipv6 addresses, but these fail on ubuntu where it just
# returns the values in /etc/hosts even if ip a and ifconfig show other
# addresses as well, and the values in /etc/hosts are incorrect.
def get_ip(family='inet'):
    """Return a dict of interface and ip for address family.

    Information is gathered via subprocess by using:
        Linux:   ip, ifconfig
        Windows: ipconfig
        If cannot distinguish, then bind a udp broadcast socket
        and return whatever ip is given.
    for family, use:
        IPv4:  "inet"
        IPv6:  "inet6"
    """
    ret = {}
    try:
        bak = default_ip(family)
        if bak:
            ret[''] = [bak]
        if platform.system() == 'Windows':
            ret.update(ipconfig(family))
        else:
            try:
                ret.update(ipa(family))
            except Exception:
                ret.update(ifconfig(family))
    except Exception:
        pass
    return ret

class Sockfile(io.RawIOBase):
    """Wrap a socket in a file-like object.

    shutdown observations:
        SHUT_RD: this side will return b'' whenever calling receive and
            no data is available.  The otherside can still write data
            and this side will receive it.

        SHUT_WR: This side can no longer write data.
                 The Other side will receive b'' whenever reading data.

        If SHUT_RD and SHUT_WR, connection seems to be auto-broken.  ie
        if SHUT_RD, receive data until SHUT_WR, after which connection
        is broken. (Though fd still exists.)
    """
    SHUT_RD = socket.SHUT_RD
    SHUT_WR = socket.SHUT_WR
    SHUT_RDWR = socket.SHUT_RDWR
    def __init__(self, sock, mode = 'rwb'):
        """Wrap a socket.

        sock: socket to wrap
        mode: mode, determines whether read() or write() are available.
            Also determines the default for self.shutdown()
        """
        super(Sockfile, self).__init__()
        self.socket = sock
        if 'b' not in mode:
            print(
                'WARNING: Sockfile only handles binary io but b not present in mode',
                file=sys.stderr)
        self._w = bool(set('wa+').intersection(mode))
        self._r = bool(set('r+').intersection(mode))
        if not (self._w or self._r):
            raise Exception("Sockfile neither read nor write")
        FLAGS = ''
        if self._r:
            FLAGS ='RD'
            self._read = self._block_to_none(sock.recv)
            self._readinto = self._block_to_none(sock.recv_into)
            self._rpos = 0
        if self._w:
            FLAGS += 'WR'
            self._write = self._block_to_none(sock.send)
            self._wpos = 0
        self._shut = getattr(socket, 'SHUT_{}'.format(FLAGS))
        self.fileno = sock.fileno
        self._name = None

    @property
    def name(self):
        """Some identifier, str if unix, tup if inet."""
        if self._name is None:
            try:
                self._name = self.socket.getpeername()
            except Exception:
                try:
                    self._name = '"bad socket fd{}"'.format(self.fileno())
                except Exception:
                    self._name = '"bad socket"'
        return self._name

    def shutdown(self, method=None):
        """Shutdown the the wrapped socket.

        Method can be socket.SHUT_[RD|WR|RDWR]
        If None, then method will default to RD, WR or RDWR
        depending on whether the Sockfile was opened with
        read-only, write-only or read and write modes.
        """
        if method is None:
            method = self._shut
        try:
            self.socket.shutdown(method)
        except Exception:
            pass

    def detach(self):
        """Detach from the wrapped socket.

        Set closed state and return the wrapped socket. Note however
        that some internal references may still point to the socket
        so calling any functions after detaching is undefined.
        """
        io.RawIOBase.close(self)
        ret = self.socket
        self.socket = None
        return ret

    #IOBase
    def close(self):
        """Close socket."""
        if self.socket is not None:
            self.shutdown(socket.SHUT_RDWR)
            self.detach().close()
    # fileno = socket.fileno()
    def flush(self):
        pass
    def isatty(self):
        return False
    def readable(self):
        return self._r
    # readline and readlines are free by defining read()

    def seekable(self):
        return False
    def seek(self, *args):
        raise io.UnsupportedOperation("sockfile cannot seek")
    def tell(self):
        """Return position.

        If readable, return number of bytes read from initialization.
        Otherwise, return number of bytes written from initizliation.
        """
        if self._r:
            return self._rpos
        return self._wpos
    def rtell(self):
        """Total number of bytes read so far."""
        return self._rpos
    def wtell(self):
        """Total bytes written so far."""
        return self._wpos
    def truncate(self):
        raise io.UnsupportedOperation("sockfile cannot seek")

    # writelines
    def writable(self):
        return self._w

    @staticmethod
    def _block_to_none(func):
        """Convert socket timeout and EAGAIN, EWOULDBLOCK to None."""
        @functools.wraps(func)
        def wrap(arg):
            try:
                return func(arg)
            except socket.timeout:
                return None
            except EnvironmentError as e:
                if e.errno in (EAGAIN, EWOULDBLOCK):
                    return None
                raise
        return wrap
    # RawIOBase
    def _read(self, amt=-1):
        raise io.UnsupportedOperation('read')

    def read(self, amt=-1):
        if amt is None or amt < 0:
            ret = self.readall()
        else:
            ret = self._read(amt)
        if ret:
            self._rpos += len(ret)
        return ret

    def readinto(self, buf):
        amt = self._readinto(buf)
        if amt:
            self._rpos += amt
        return amt

    def _write(self, data):
        raise io.UnsupportedOperation('write')
    def write(self, data):
        ret = self._write(data)
        if ret:
            self._wpos += ret
        return ret

class Listener(object):
    """Wrap a listening socket.

    Set some options before returning accepted connections.
    """
    def __init__(self, sock, cloexec=True, nodelay=None, timeout=None):
        self.sock = sock
        self._cloexec = cloexec
        self._nodelay = nodelay
        self._timeout = timeout
    def __getattr__(self, name):
        val = getattr(self.sock, name)
        if callable(val):
            setattr(self, name, val)
        return val
    def accept(self, cloexec=None, nodelay=None, timeout=Ellipsis):
        """Returns accepted socket and address.

        Additionally sets cloexec and nodelay if applicable.
        """
        s, a = self.sock.accept()
        set_cloexec(s, self._cloexec if cloexec is None else cloexec)
        if s.type == socket.SOCK_STREAM and nodelay is not None:
            s.setsockopt(
                socket.IPPROTO_TCP, socket.TCP_NODELAY, int(nodelay))
        s.settimeout(self._timeout if timeout is Ellipsis else timeout)
        return s, a

class MultiError(Exception):
    """All alternatives failed.

    errors attribute = list of exceptions, 1 per alternative.
    """
    def __init__(self, errors):
        Exception.__init__(
            self,
            '\n'.join(['socket creation failed:']+[str(e.args) for e in errors]))
        self.errors = errors

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
    cloexecflag = SOCK_CLOEXEC if cloexec else 0
    for af, socktype, proto, cannon, addr in addrs:
        try:
            s = socket.socket(af, socktype | SOCK_CLOEXEC, proto)
        except Exception as e:
            errors.append(e)
        else:
            try:
                set_cloexec(s, cloexec)
                s.setsockopt(
                    socket.SOL_SOCKET, socket.SO_REUSEADDR, int(reuse))
                if s.type == socket.SOCK_STREAM:
                    s.setsockopt(
                        socket.IPPROTO_TCP, socket.TCP_NODELAY,
                        int(nodelay))
                s.bind(addr[:2])
                s.settimeout(timeout)
                return Listener(s, cloexec, nodelay, timeout)
            except Exception as e:
                s.close()
                errors.append(e)
    raise MultiError(errors)

class ProxyWrap(Sockfile):
    """Always read at most 1 byte to avoid consuming extra data.

    The main purpose is to just find the end of the proxy response.
    even if less efficient, this should only be used once per
    connection so it's fine if it isn't efficient.
    """
    def read(self, amt=None):
        return super(ProxyWrap, self).read(1)
    def readinto(self, buf):
        return super(ProxyWrap, self).readinto(memoryview(buf)[:1])

def connect_proxy(proxy, host, port, *args):
    """simple use of proxy to connect to host/port."""
    if not isinstance(proxy, str):
        proxy = os.environ.get('https_proxy', os.environ.get('http_proxy'))
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
            f = ProxyWrap(sock, 'rb')
            try:
                line = f.readline().decode('utf-8')
                version, code, reason = line.split(None, 2)
                if int(code) != 200:
                    raise Exception(reason)
                else:
                    for line in f:
                        if not (line and line.endswith(b'\r\n')):
                            break
                        elif line == b'\r\n':
                            ok = True
                            return sock
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

    if isinstance(hostOrAddr, tuple):
        # ipv6 gives a 4-tuple, only need the first 2
        host, port = hostOrAddr[:2]
    else:
        host = hostOrAddr
    if not host:
        host = '127.0.0.1'
    if proxy and host not in ('localhost', '127.0.0.1', '::'):
        try:
            return connect_proxy(
                proxy, host, port, family, tp, proto, flags,
                cloexec, nodelay, timeout, False)
        except Exception:
            pass
    addrs = socket.getaddrinfo(host, port, family, tp, proto, flags)
    errors = []
    cloexecflag = SOCK_CLOEXEC if cloexec else 0
    for af, socktype, proto, cannon, addr in addrs:
        try:
            s = socket.socket(af, socktype|cloexecflag, proto)
        except Exception as e:
            errors.append(e)
        else:
            try:
                set_cloexec(s, cloexec)
                if s.type == socket.SOCK_STREAM:
                    s.setsockopt(
                        socket.IPPROTO_TCP, socket.TCP_NODELAY,
                        int(nodelay))
                s.settimeout(1)
                # Convert all interfaces to localhost.
                if af == socket.AF_INET6 and addr[0] == '::':
                    addr = ('::1', addr[1])
                elif af == socket.AF_INET and addr[0] == '0.0.0.0':
                    addr = ('127.0.0.1', addr[1])
                s.connect(addr[:2])
                s.settimeout(timeout)
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
            set_cloexec(s, cloexec)
            s.bind(fname)
            s.settimeout(timeout)
        except Exception:
            s.close()
            raise
        return Listener(s, cloexec, None, timeout)

    def connect_unix(
        fname, cloexec=True, timeout=None,
        socktype=socket.SOCK_STREAM, **kwargs):
        """Return a connected unix socket."""
        s = socket.socket(socket.AF_UNIX, socktype)
        try:
            set_cloexec(s, cloexec)
            s.settimeout(timeout)
            s.connect(fname)
        except Exception:
            s.close()
            raise
        return s

def bind(value=None, **kwargs):
    """Return bound socket. Dispatch to bind_*."""
    if value is None:
        # prefer unix over inet
        try:
            return bind_unix(**kwargs)
        except NameError:
            return bind_inet(**kwargs)
    if isinstance(value, tuple):
        return bind_inet(value, **kwargs)
    else:
        return bind_unix(value, **kwargs)

def connect(value, **kwargs):
    """Return connected socket. Dispatch to connect_*."""
    if isinstance(value, tuple):
        return connect_inet(value, **kwargs)
    else:
        return connect_unix(value, **kwargs)
