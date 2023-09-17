import socket

from jhsiao.ipc.sockets.threaded import reader, listener
from jhsiao.ipc.formats import chunkpkl
from jhsiao.ipc.sockets import sockets, sockfile
from jhsiao.ipc import polling

class Wrapper(chunkpkl.Reader):
    def __init__(self, socket):
        super(Wrapper, self).__init__(sockfile.Sockfile(socket))

def test_threaded_reader():
    poller = polling.Poller()
    L = listener.PollWrapListener(
        sockets.bind_inet('0.0.0.0', 0), poller, Wrapper,
        verbose=True)
    L.listen(1)
    c = sockets.connect_inet(L.getsockname())
    s, a = L.accept()
    poller.register(L, poller.r)
    poller.register(s, poller.r)
    rd = reader.Reader(poller, s, True)
    rd.start()

    s1 = sockets.connect_inet(L.getsockname())
    f1 = chunkpkl.BWriter(s1.makefile('wb'))
    s2 = sockets.connect_inet(L.getsockname())
    f2 = chunkpkl.BWriter(s2.makefile('wb'))

    assert len(rd.get(1)) == 0
    f1.write(1)
    f2.write(b'whatever')
    f1.flush()
    f2.flush()
    results = rd.get(1)
    assert len(results) > 0
    if len(results) == 1:
        results.extend(rd.get(1))
    assert len(results) == 2
    assert 1 in results
    assert b'whatever' in results
    f1.close()
    s1.close()
    f2.close()
    s2.close()
    c.close()
    rd.join()
    s.close()
    L.close()
