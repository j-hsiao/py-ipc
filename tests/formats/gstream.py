
from jhsiao.ipc.formats.gstream import (
    gchunk,
    gline,
    gchunkpkl
)

def test_gchunk():
    import io
    import struct
    with io.BytesIO() as dummy:
        messages = [b'hello', b'world', b'hello world']
        for msg in messages:
            dummy.write(struct.pack('<Q', len(msg)))
            dummy.write(msg)
        out = []
        r = gchunk.GChunkReader(dummy, out)
        dummy.seek(0)
        it = r._iter()
        buf = next(it)
        while buf is not None:
            amt = dummy.readinto(buf[:3])
            if amt:
                buf = it.send(amt)
            else:
                break
        assert out == messages
        out = []
        dummy.seek(0)
        r = gchunk.GChunkReader(dummy, out, True, buffersize=9)
        result = r.read()
        while result is None or result >= 0:
            result = r.read()
        assert out == messages

def test_gchunkpkl():
    import pickle
    import io
    import struct
    s = struct.Struct('<Q')
    with io.BytesIO() as dummy:
        messages = [(1,2), 3.14, 'hello world']
        for msg in messages:
            data = pickle.dumps(msg)
            dummy.write(s.pack(len(data)))
            dummy.write(data)
        dummy.seek(0)
        out = []
        r = gchunkpkl.GChunkPklReader(dummy, out, True, buffersize=s.size)
        result = r.read()
        while result is None or result >= 0:
            result = r.read()
        assert out == messages

def test_gline():
    import io
    with io.BytesIO() as dummy:
        messages = [b'hello\n', b'world\n', b'hello world\n', b'the end but no newline']
        dummy.writelines(messages)
        dummy.seek(0)
        out = []
        r = gline.GLineReader(dummy, out, True, buffersize=3)
        result = r.read()
        while result is None or result >= 0:
            result = r.read()
        assert out == messages
