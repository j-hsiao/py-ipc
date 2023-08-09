__all__ = ['SocketPickleReader']
import select
import socket
import threading
import os
import queue

from socketfile import picklereader, bare, poller


class ClientMixIn(object):
    def __init__(self, socket, *args, **kwargs):
        super(ClientMixIn, self).__init__(
            socket.makefile('rb'), *args, **kwargs)
        self.socket = socket

    def fileno(self):
        return self.socket.fileno()

    def close(self):
        super(ClientMixIn, self).close()
        self.socket.close()


class PickleClient(ClientMixIn, picklereader.PickleReader):
    pass

class LineClient(ClientMixIn, picklereader.PickleReader):
    pass



class SocketPickleReader(object):
    """Read pickles from multiple sockets.

    Handle multiple sockets in a single thread.
    """
    def __init__(self, addr, expire=None, timeout=5, client_type=PickleClient):
        self.client_type = client_type
        self.addr = addr
        self.expire = expire
        self.cond = threading.Condition()
        self.q = []
        listener = bare.bind(addr, None)
        listener.settimeout(timeout)
        listener.listen(5)
        self.sockname = listener.getsockname()
        self.signal = bare.connect(listener.getsockname())
        stop, addr = listener.accept()
        self.thread = threading.Thread(target=self._run, args=[listener, stop])
        self.thread.start()

    def _hasitems(self):
        return len(self.q)

    def get(self, timeout=None):
        with self.cond:
            if self.q or self.cond.wait_for(self._hasitems, timeout):
                ret = self.q
                self.q = []
                return ret
            return None

    def close(self):
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
        server = SocketPickleReader(args.ip)
    else:
        server = SocketPickleReader((args.ip, args.port))
    print(server.sockname)
    try:
        while 1:
            things = server.get(1)
            if things:
                print('got', len(things), 'items')
                print(things[:5])
    except KeyboardInterrupt:
        pass
    finally:
        print('Closed')
        server.close()
