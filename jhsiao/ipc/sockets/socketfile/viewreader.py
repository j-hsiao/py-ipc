"""Read a buffer like a file.

Because pickle does not give any interface to determine the position of
the end of pickle data, wrap it in a file-like object to track the total
number of bytes consumed.
"""
__all__ = ['ViewReader']

import io

class ViewReader(io.RawIOBase):
    def __init__(self, view):
        self.view = view
        self.pos = 0

    def read(self, amt=None):
        if amt is None or amt < 0:
            start = self.pos
            self.pos = len(self.view)
            return self.view[start:].tobytes()
        else:
            start = self.pos
            self.pos += amt
            return self.view[start:self.pos].tobytes()

    def readinto(self, buf):
        start = self.pos
        self.pos += len(buf)
        chunk = self.view[start:self.pos]
        amt = len(chunk)
        buf[:amt] = chunk
        return amt

    def readable(self):
        return True
    def seekable(self):
        return False
    def writable(self):
        return False

if __name__ == '__main__':
    with BufReader(memoryview(b'hello world!\ngoodbye world!\n')) as f:
        print(f.read(1))
        print(f.readinto(bytearray(2)))
        print(f.readline())
        print(list(f))

    import pickle
    data = pickle.dumps((b'hello world', 'tits'))
    with BufReader(
            memoryview(data + b'whatever')) as f:
        print(pickle.load(f))
        print(len(f.view), f.pos)
        print(f.read())
