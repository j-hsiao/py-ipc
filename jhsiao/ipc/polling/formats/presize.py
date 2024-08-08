"""Use a prefix size to determine size of the sent message."""
import struct

import io
from .. import base

class VPresize(base.Resource):
    """Variable length prefix size."""

    _FORMAT = 'extend'

    def rproces(self):
        pass

    def format(self, data):
        pass

class Presize(base.Resource):
    """Fixed prefix size."""
    _FORMAT = 'extend'

    def __init__(self, f, poller, rq, fmt='>Q'):
        super(Presize, self).__init__(f, poller, rq)
        self.fmt = struct.Struct('>Q')
        gen = self.format()
        next(gen)
        self.format = gen.send

    def detach(self):
        self.format = None
        return super(Presize, self).detach()


    def format(self):
        """Generator to format data.

        The generator.send() method will replace self.format
        """
        data = yield
        pack = self.fmt.pack
        while 1:
            data = yield memoryview(pack(len(data))), data

    def rprocess(self):
        view = memoryview(bytearray(io.DEFAULT_BUFFER_SIZE))
        unpack_from = self.fmt.unpack_from
        size = self.fmt.size
        start = end = 0
        while 1:
            cur = end-start
            if cur < size:
                view[:cur] = view[start:end]
                start = 0
                end = yield view, cur, size
            datasize = unpack_from(view, start)[0]
            start += size
            target = start + datasize
            if end < target:
                if target <= io.DEFAULT_BUFFER_SIZE:
                    end = yield view, end, target
                    data = view[start:target].tobytes()
                    start = target
                else:
                    cur = end-start
                    if datasize < io.DEFAULT_BUFFER_SIZE:
                        view[:cur] = view[start:end]
                        end = yield view, cur, datasize
                        data = view[:datasize].tobytes()
                        start = datasize
                    else:
                        tmp = memoryview(bytearray(datasize))
                        tmp[:cur] = view[start:end]
                        end = yield tmp, cur, datasize
                        data = tmp
                        start = end = 0
            else:
                data = view[start:target].tobytes()
                start = target
            self.rq.push(data)
