"""Support partial reads, return once a complete pickle has been found."""
__all__ = ['PickleReader']
import pickle

from socketfile import viewreader, bufferedreader

class PickleReader(bufferedreader.BufferedReader):
    """Read serial pickles."""

    def extract(self, out, newstart):
        """Extract objects from buffer into out.

        out: container
            Should support append()
        Return amount of data consumed.
        """
        if self.buf.find(pickle.STOP, newstart, self.stop) < 0:
            return 0
        start = 0
        with viewreader.ViewReader(self.view[:self.stop]) as f:
            try:
                while 1:
                    out.append(pickle.load(f))
                    start = f.pos
            except Exception:
                pass
        if start:
            if start == self.stop:
                self.stop = 0
            else:
                trail = self.view[start:self.stop]
                self.stop = len(trail)
                self.view[:self.stop] = trail
        return start

if __name__ == '__main__':
    import io
    import os
    import numpy as np
    import threading
    r, w = os.pipe()
    reader = io.open(r, 'rb')
    writer = io.open(w, 'wb')
    item1 = pickle.dumps(b'hello world')
    item2 = pickle.dumps(32)

    item3 = pickle.dumps(np.empty((480,640,3), np.uint8))

    def readloop(reader):
        try:
            pr = PickleReader(reader)
            connected = True
            objs = []
            while pr.read(objs):
                for obj in objs:
                    print(obj)
                objs = []
            for obj in objs:
                print(obj)
            print('disconnected')
        finally:
            pr.close()

    t = threading.Thread(target=readloop, args=[reader])
    t.start()
