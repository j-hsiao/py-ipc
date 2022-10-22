from __future__ import print_function
from jhsiao.ipc.polling import Poller
import socket
import sys
import time

def test_oneshot():
    l = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    l.bind(('localhost', 0))
    l.listen(1)
    L = 0.1
    S = L/2

    p = Poller()
    p.register(l, p.RFLAGS)
    # no data should block
    now = time.time()
    assert not any(p.poll(L))
    assert time.time()-now > S
    c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    c.connect(('localhost', l.getsockname()[1]))
    #has data should return immediately
    now = time.time()
    assert p.poll(L)[0]
    assert time.time()-now < S
    #level triggered no oneshot should return immediately again
    now = time.time()
    assert p.poll(L)[0]
    assert time.time()-now < S
    s, a = l.accept()
    s.close()
    c.close()

    # testing oneshot
    p.modify(l, p.RFLAGS|p.OFLAGS)
    # no data, should block
    now = time.time()
    assert not any(p.poll(L))
    assert time.time()-now > S
    # oneshot but no event means should block again
    now = time.time()
    assert not any(p.poll(L))
    assert time.time()-now > S
    c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    c.connect(('localhost', l.getsockname()[1]))
    #make sure active flags set not empty
    p.register(c, p.RFLAGS)
    #has data should return immediately once
    now = time.time()
    assert p.poll(L)[0]
    assert time.time()-now < S
    now = time.time()
    assert not any(p.poll(L))
    assert time.time()-now > S
    # modify to rearm the fd
    p.modify(l, p.RFLAGS|p.OFLAGS)
    now = time.time()
    assert p.poll(L)[0]
    assert time.time()-now < S
    now = time.time()
    assert not any(p.poll(L))
    assert time.time()-now > S
    # modify to remove oneshot
    p.modify(l, p.RFLAGS)
    now = time.time()
    assert p.poll(L)[0]
    assert time.time()-now < S
    now = time.time()
    assert p.poll(L)[0]
    assert time.time()-now < S
    s, a = l.accept()
    p.unregister(c)
    p.unregister(l)
    s.close()
    c.close()
    l.close()
    p.close()
    print('pass')


def test_poller():
    p = Poller()
    import socket
    l = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    l.bind(('', 0))
    l.listen(1)
    c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    c.connect(('localhost', l.getsockname()[1]))
    s, a = l.accept()
    l.close()
    try:
        p.register(c, 'rw')
        r,w,x = p.poll(1)
        assert not r and w and not x
        s.send(b'hello')
        r,w,x = p.poll(1)
        assert r and w and not x
        c.recv(5)
        r,w,x = p.poll(1)
        assert not r and w and not x
        c.settimeout(1)
        written = 0
        print('filling socket buffer...', end='')
        sys.stdout.flush()
        try:
            data = b'hello world'*1024
            while 1:
                wrote = c.send(data)
                if wrote != len(data):
                    print('wrote less data')
                written += wrote
        except socket.timeout:
            print('done')
            print('filled at', written)
        assert not any(p.poll(1))
        buf = memoryview(bytearray(8192))
        s.settimeout(1)
        print('emptying socket buffer...')
        try:
            received = s.recv_into(buf)
            res = p.poll(1)
            while not res[1]:
                received += s.recv_into(buf)
                res = p.poll(0)
            print('unblocked at', received, list(map(len, res)))
            while 1:
                received += s.recv_into(buf)
        except socket.timeout:
            print('done')
            print('received total of', received)
        assert written == received
    finally:
        p.close()
        c.close()
        s.close()

    print('pass')

if __name__ == '__main__':
    from jhsiao.tests import simple
    simple(globals())
