"""Read from multiple sockets."""
__all__ = ['SocketReader', 'ClientMixIn', 'PickleClient']
import io
import socket
import threading
import sys
import time

from socketfile import poller, picklereader, bare

class ClientMixIn(object):
    """Mixin for client for SocketReader.

    Superclass should take a binary readable file as argument.
    """
    def __init__(self, socket, *args, **kwargs):
        super(ClientMixIn, self).__init__(
            socket.makefile('rb'), *args, **kwargs)
        self.socket = socket

    def detach(self):
        raise io.UnsupportedOperation

    def fileno(self):
        return self.socket.fileno()

    def close(self):
        super(ClientMixIn, self).close()
        self.socket.close()

class PickleClient(ClientMixIn, picklereader.PickleReader):
    pass

class SocketReader(object):
    """Read pickles from multiple sockets.

    Handle multiple sockets in a single thread.
    """
    def __init__(self, addr, client_type=PickleClient, qtype=list):
        """Initialize SocketReader.

        addr: str | tuple | socket
            The address to bind to (see bare.bind) or the listening
            socket to use.  If an accept timeout is required (ie. if
            using ssl socket), then create the listening socket
            separately and give that as argument.
        client: type
            The client type to use for parsing the incoming data.
            It should be a subclass of ClientMixIn and `bases.Reader`.
        qtype: container type
            qtype should be instantiable with no arguments and support
            the `append()` operation.
        """
        if sys.version_info.major > 2:
            self.get = self._get_py3
        else:
            self.get = self._get_py2
        self.qtype = qtype
        self.client_type = client_type
        self.addr = addr
        self.cond = threading.Condition()
        self.q = qtype()
        if isinstance(addr, (tuple, str)):
            listener = bare.bind(addr, None)
        else:
            listener = addr
        listener.listen(5)
        self.sockname = listener.getsockname()
        self.signal = bare.connect(listener.getsockname())
        stop, addr = listener.accept()
        self.thread = threading.Thread(target=self._run, args=[listener, stop])
        self.thread.start()

    def _hasitems(self):
        return len(self.q)

    def get(self, timeout=None):
        """Get a sequence of collected data or None if none.

        timeout: None | float
            Timeout to wait for objects.
        """
        return self.get(timeout)

    def _get_py3(self, timeout=None):
        """Get a sequence of collected data or None if none.

        timeout: None | float
            Timeout to wait for objects.
        """
        with self.cond:
            if (not self.q and
                    (timeout == 0
                     or not self.cond.wait_for(
                        self._hasitems, timeout))):
                return None
            ret = self.q
            self.q = self.qtype()
            return ret

    def _get_py2(self, timeout=None):
        """Get a sequence of collected data or None if none.

        timeout: None | float
            Timeout to wait for objects.
        """
        with self.cond:
            if not self.q:
                if timeout == 0:
                    return None
                elif timeout is None:
                    while not self.q:
                        self.cond.wait()
                else:
                    end = time.time() + timeout
                    while not self.q and timeout > 0:
                        self.cond.wait(timeout)
                        timeout = end - time.time()
                    if not self.q:
                        return None
            ret = self.q
            self.q = self.qtype()
            return ret

    def close(self):
        """Close the reader."""
        if self.thread is not None:
            self.signal.close()
            self.thread.join()
            self.thread = None

    def _run(self, listener, stop):
        clients = {
            listener.fileno():listener,
            stop.fileno(): stop,
        }
        poll = poller.Poller()
        poll.register(listener, 'r')
        poll.register(stop, 'r')
        while 1:
            r, w, x = poll()
            for item in r:
                client = clients[item]
                if client is listener:
                    try:
                        client, addr = listener.accept()
                    except socket.timeout:
                        pass
                    else:
                        print('new connection from', addr)
                        clients[client.fileno()] = PickleClient(client)
                        poll.register(client, 'r')
                elif client is stop:
                    for client in clients.values():
                        poll.unregister(client.fileno())
                        client.close()
                    return
                else:
                    with self.cond:
                        connected = client.read(self.q)
                        self.cond.notify()
                    if not connected:
                        print('disconnected')
                        poll.unregister(client.fileno())
                        client.close()
                        del clients[item]


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('ip', nargs='?', default='localhost', help='ip or unix socket if port < 0')
    p.add_argument('-p', '--port', default=1234, type=int, help='dummy server port')
    args = p.parse_args()

    if args.port < 0:
        addr = args.ip
    else:
        addr = (args.ip, args.port)
    server = SocketReader(addr)
    print(server.sockname)
    try:
        while 1:
            things = server.get(1)
            if things:
                print('got', len(things), 'items')
                if len(things) > 5:
                    print(things[-5:])
                else:
                    print(things)
    except KeyboardInterrupt:
        pass
    finally:
        print('Closed')
        server.close()

