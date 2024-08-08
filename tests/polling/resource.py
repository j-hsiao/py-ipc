import io
import struct

from jhsiao.ipc.polling.formats import presize
from jhsiao.ipc.polling import queue


class DummyFD(object):
    def __init__(self, data):
        self.f = io.BytesIO(data)
        self.writesize = 10
        self.written = io.BytesIO()
    def fileno(self):
        return 42
    def write(self, thing):
        written = thing[:self.writesize]
        return self.written.write(written)
    def readinto(self, buf):
        return self.f.readinto(buf)
    def close(self):
        pass
    def flush(self):
        pass

class DummyPoller():
    def __init__(self, thing):
        self.resources = {
            thing.fileno(): [
                thing.fileno(),
                thing,
                None, None, False, False]}

    def write_ready(self):
        pass

def test_resource(fnc):
    def run_test():
        resource, messages, formatted, rq = fnc()
        statechanged = set()
        try:
            wgen = resource.wprocess(statechanged)
            resource.write(messages[0])
            while not statechanged:
                next(wgen)
            statechanged.clear()
            for message in messages[1:]:
                resource.write(message)
            while not statechanged:
                next(wgen)
            assert resource.f.written.getvalue() == formatted
            rgen = resource.rprocess()
            view, current, target = next(rgen)

            # test smaller incremental reads
            while not len(rq):
                amt = resource.f.readinto(view[current:target])
                current += amt
                assert current == target
                view, current, target = rgen.send(current)

            # test larger reads that give extra data
            while 1:
                amt = resource.f.readinto(view[current:])
                if amt:
                    current += amt
                    if current >= target:
                        view, current, target = rgen.send(current)
                else:
                    break
        finally:
            resource.detach()
    return run_test


@test_resource
def test_presize(fmt):
    messages = [
        b'hello',
        b'world',
        b'hello world',
        b'whatever goodbye.'
    ]
    structfmt = struct.struct(fmt)
    formatted = bytearray(sum(map(len, messages)) + len(messages)*structfmt.size)
    pos = 0
    for message in messages:
        structfmt.pack_into(formatted, pos, len(message))
        pos += structfmt.size
        formatted[pos:pos+len(message)] = message
        pos += len(message)
    dummy = DummyFD()
    rq = queue.Queue()
    return presize.Presize(dummy, DummyPoller(dummy), rq, fmt), messages, formatted, rq
