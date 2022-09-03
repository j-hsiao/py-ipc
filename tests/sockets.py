from __future__ import print_function
import socket

from mipy.tests import TestSuite

from mipy.ipc import sockets

t = TestSuite()
@t.test()
def inet(args):
    L = sockets.bind_inet()
    if not L:
        print('bind failed')
        return
    L.listen(1)
    print(L.getsockname())
    c = sockets.connect_inet(L.getsockname())
    if c is None:
        print('connect failed')
        return
    s, a = L.accept()
    assert s.recv(c.send(b'hello world')) == b'hello world'
    s.close()
    c.close()
    L.close()

@t.test()
def unix(args):
    try:
        L = sockets.bind_unix()
    except AttributeError:
        print('bind_unix not available')
        return
    if not L:
        print('bind failed')
        return
    L.listen(1)
    print(repr(L.getsockname()))
    c = sockets.connect_unix(L.getsockname())
    if c is None:
        print('connect failed')
        return
    s, a = L.accept()
    assert s.recv(c.send(b'hello world')) == b'hello world'
    s.close()
    c.close()
    L.close()

@t.test()
def bindconnect(args):
    L = sockets.bind()
    L.listen(1)
    print(L.family, L.type)
    c = sockets.connect(L.getsockname())
    s, a = L.accept()
    assert s.recv(c.send(b'hello')) == b'hello'
    c.close()
    s.close()
    L.close()

@t.test(
    t.arg('family', help='ip family', default='inet', nargs='?')
)
def ip(args):
    for k, v in sockets.get_ip(args.family).items():
        print(repr(k))
        for ip in v:
            print('   ', ip)
