"""Support partial reads, return once a complete pickle has been found."""
__all__ = ['PickleReader']
import pickle

from . import viewreader, bufferedreader

class PickleReader(bufferedreader.BufferedReader):
    """Read serial pickles."""

    def extract(self, out, newstart):
        """Extract objects from buffer into out.

        out: container
            Should support append()
        Return amount of data consumed.
        """
        if self.buf.find(pickle.STOP, newstart, self.stop) < 0:
            if self.stop == len(self.buf):
                try:
                    self._grow()
                except Exception:
                    return -1
            return 0
        start = 0
        count = 0
        with viewreader.ViewReader(self.view[:self.stop]) as f:
            try:
                while 1:
                    out.append(pickle.load(f))
                    start = f.pos
                    count += 1
            except Exception:
                pass
        if start:
            if start == self.stop:
                self.stop = 0
            else:
                trail = self.view[start:self.stop]
                self.stop -= start
                self.view[:self.stop] = trail
        elif self.stop == len(self.buf):
            try:
                self._grow()
            except Exception:
                return -1
        return start

if __name__ == '__main__':
    import io
    import os
    import numpy as np
    import threading
    r, w = os.pipe()
    reader = io.open(r, 'rb')
    writer = io.open(w, 'wb')
    pr = PickleReader(reader)
    objs = []
    item1 = memoryview(pickle.dumps(b'hello world'))
    arr = np.empty((480,640,3), np.uint8)
    item2 = memoryview(pickle.dumps(arr))
    try:

        writer.write(item1[:1])
        writer.flush()
        assert pr.readinto1(objs) == 0

        writer.write(item1[1:])
        writer.flush()
        assert pr.readinto1(objs) > 0

        writer.write(item1)
        writer.flush()
        objs, ret = pr.read()
        assert len(objs) == 1
        assert ret > 0

        blocksize = 1024
        for stop in range(blocksize, len(item2) + blocksize - 1, blocksize):
            print(stop, end='\r')
            writer.write(item2[stop-blocksize:stop])
            writer.flush()
            if stop < len(item2):
                assert pr.readinto1(objs) == 0
            else:
                assert pr.readinto1(objs) > 1
        assert np.all(arr == objs[-1])

        writer.close()
        assert pr.readinto1(objs) == -1

        print(len(pr.buf), len(item2))
        print('pass')
    finally:
        pr.close()
        writer.close()
