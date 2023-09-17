import socket

from jhsiao.ipc.sockets import sockfile
from jhsiao.ipc.formats.stream import line

class Listener(object):
    def __init__(self, poller):
        self.poller = poller
        poller[self] = poller.s
        self.L = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.L.bind(('127.0.0.1', 0))
        self.L.listen(1)
        self.fileno = self.L.fileno

    def readinto1(self, out):
        s, a = self.L.accept()
        self.poller.register(
            line.Reader(sockfile.Sockfile(s, 'r')),
            self.poller.r)
        return -2

    def close(self):
        self.L.close()

def _test_rpoller(cls):
    poller = cls()
    L = Listener(poller)
    assert not poller.get(1)
    poller.step()
    assert not poller.get(1)

    c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    c.connect(L.L.getsockname())
    poller.step()
    assert not poller.get(1)
    f = c.makefile('wb')
    f.write(b'hello world\n')
    f.flush()

    result = poller.get(1)
    assert result
    assert result[0] == b'hello world\n'
    objs = poller.close()
    c.close()
    for obj in objs:
        obj.close()
