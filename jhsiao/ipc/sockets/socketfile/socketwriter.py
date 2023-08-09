__all__ = ['SocketWriter']
import io
import pickle
import socket

from socketfile import bare

class SocketWriter(object):
    """Write to a socket."""
    def __init__(self, addr, timeout=5):
        """Connect to addr and use makefile as wrapped file obj.

        Raise if fail to connect.
        """
        socket = bare.connect(addr, timeout)
        super(SocketWriter, self).__init__(socket.makefile('wb'))
        self.socket = socket

    def detach(self):
        """SocketWriter doesn't wrap external file so disable detach."""
        raise io.UnsupportedOperation

    def close(self):
        super(SocketWriter, self).close()
        self.socket.close()

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('ip', nargs='?', default='localhost', help='ip or unix socket if port < 0')
    p.add_argument('-p', '--port', type=int, default=1234)
    p.add_argument('-a', '--auto', type=float, help='duration')
    p.add_argument('-c', '--count', type=int, help='count')
    p.add_argument('-f', '--format', choices=('pickle', 'line'), default='pickle')
    args = p.parse_args()
    if args.port < 0:
        addr = args.ip
    else:
        addr = (args.ip, args.port)

    if args.format == 'pickle':
        from socketfile import picklewriter
        class SocketPickleWriter(SocketWriter, picklewriter.PickleWriter):
            pass
        writer = SocketPickleWriter(addr)
        if args.auto:
            import time
            now = time.time()
            count = 0
            while time.time() - now < args.auto:
                count += 1
                writer.write(count)
            writer.close()
            print('total:', count)
        elif args.count:
            for i in range(args.count):
                writer.write(i)
            writer.close()
        else:
            import sys
            if sys.version_info.major > 2:
                inp = input
            else:
                inp = raw_input
            try:
                while 1:
                    try:
                        message = inp('>>> ')
                    except (KeyboardInterrupt, EOFError):
                        print('end')
                        writer.close()
                        break
                    writer.write(message)
                    writer.flush()
            finally:
                writer.close()
    else:
        from socketfile import linereader, bare
        sock = bare.connect(addr, 5)
        try:
            with sock.makefile('w') as f:
                if args.auto:
                    import time
                    now = time.time()
                    count = 0
                    while time.time() - now < args.auto:
                        count += 1
                        f.write(str(count))
                        f.write('\n')
        finally:
            sock.close()
