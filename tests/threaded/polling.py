"""Test polling classes."""
import platform
import socket
if platform.system() != 'Windows':
    import os

from jhsiao.ipc.sockets import sockfile
from jhsiao.ipc.formats.stream import line

class RWPair(line.Reader, line.QWriter):
    pass

class Listener(object):
    def __init__(self, poller):
        self.poller = poller
        self.L = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.L.settimeout(0)
        self.L.bind(('127.0.0.1', 0))
        self.L.listen(1)
        self.fileno = self.L.fileno
        poller.register(self, poller.s)
        self.accepted = []

    def readinto1(self, out):
        s, a = self.L.accept()
        s.settimeout(0)
        thing = RWPair(sockfile.Sockfile(s, 'r+'))
        self.poller[thing] = self.poller.r
        self.accepted.append(thing)
        return -2

    def close(self):
        self.fileno = None
        self.L.close()

def _test_poller(cls):
    poller = cls()
    L = Listener(poller)
    try:
        results, bad = poller.get(.1)
        assert not results and not bad
        poller.step()
        results, bad = poller.get(.1)
        assert not results and not bad

        c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c.connect(L.L.getsockname())
        poller.step()
        results, bad = poller.get(.1)
        assert not results and not bad
        f = c.makefile('rwb')
        f.write(b'hello world\n')
        f.flush()
        poller.step()

        results, bad = poller.get(.1)
        assert len(results) == 1
        assert L.accepted
        assert results[0][0] is L.accepted[0]
        assert results[0][1] == b'hello world\n'
        assert not bad
        results[0][0].write(b'hello to you too!\n')
        poller.flush(results[0][0])
        poller.step()
        poller.step()
        response = f.readline()
        assert response == b'hello to you too!\n'
        f.close()
        c.close()
        poller.step(1)
        results, bad = poller.get(.1)
        assert not results and bad
        assert len(bad) == 1
        assert bad[0] is L.accepted[0]
        bad[0].close()
        L.accepted.pop()
        objs = list(poller.close())
        assert len(objs) == 1
        assert objs[0] is L
    finally:
        L.close()
        poller.close()

def _test_poller_thread(cls):
    poller = cls()
    poller.start()
    L = Listener(poller)
    try:
        results, bad = poller.get(.1)
        assert not results and not bad

        c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c.connect(L.L.getsockname())
        results, bad = poller.get(.1)
        assert not results and not bad
        f = c.makefile('rwb')
        f.write(b'hello world\n')
        f.flush()
        results, bad = poller.get(.1)
        assert len(results) == 1
        assert L.accepted
        assert results[0][0] is L.accepted[0]
        assert results[0][1] == b'hello world\n'
        assert not bad
        results[0][0].write(b'hello to you too!\n')
        poller.flush(results[0][0])
        response = f.readline()
        assert response == b'hello to you too!\n'
        f.close()
        c.close()
        results, bad = poller.get(.1)
        assert not results and bad
        assert len(bad) == 1
        assert bad[0] is L.accepted[0]
        bad[0].close()
        L.accepted.pop()
        objs = list(poller.close())
        assert len(objs) == 1
        assert objs[0] is L
    finally:
        L.close()
        poller.close()

from jhsiao.ipc.threaded.polling import select
def test_poller_select():
    _test_poller(select.SelectPoller)

def test_poller_thread_select():
    _test_poller_thread(select.SelectPoller)

if platform.system() != 'Windows':
    pass
