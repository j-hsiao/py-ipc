from __future__ import print_function
import ast
import pickle
import time
import io
import sys

import numpy as np

from jhsiao.ipc import sserial as ss
from jhsiao.tests.profile import simpletest, simpleparser
from jhsiao.scope import Scope
from jhsiao.utils.fio import SeqWriter


pdump = pickle.dump
pload = pickle.load
with Scope('s') as s:
    def pkldump(thing, pf, sf, af, sdump):
        pf.seek(0)
        return pickle.dump(thing, pf)
    def ssdump(thing, pf, sf, af, sdump):
        sf.seek(0)
        return sdump(thing, sf)
    def astdump(thing, pf, sf, af, sdump):
        af.seek(0)
        return af.write(repr(thing).encode('utf-8'))
    dtests = dict(s.items())

with Scope('s') as s:
    def pklload(pf, sf, af, sload):
        pf.seek(0)
        return pickle.load(pf)
    def ssload(pf, sf, af, sload):
        sf.seek(0)
        return sload(sf)
    def astload(pf, sf, af, sload):
        af.seek(0)
        return ast.literal_eval(af.read().decode('utf-8'))

    ltests = dict(s.items())

def main():
    print('testing bstructs: ', end='')
    upstructs, ulstructs = ss.bstructs('BHLQ', '>', False)
    mupstructs, mulstructs = ss.bstructs('BHLQ', '>', True)
    for i in (0, 1, 255, 256, 65535, 65536, (1<<32)-1, 1<<32, (1<<64)-1):
        packer, idx = upstructs[i.bit_length()]
        data = packer.pack(i)
        assert ulstructs[idx].unpack(data)[0] == i
        packer, idx = mupstructs[i.bit_length()]
        data = packer.pack(idx, i)
        assert upstructs[0][0].unpack(data[:1])[0] == idx
        assert mulstructs[idx].unpack(data[1:])[0] == i

    ipstructs, ilstructs = ss.bstructs('bhlq', '>', False)
    for i in (
            -128, -129, -32768, -32769,
            -(1<<31), -(1<<31)-1,
            -(1<<63), -(1<<63)-1):
        try:
            packer, idx = ipstructs[(-1 - i).bit_length()+1]
        except IndexError:
            if ((-1-i).bit_length()+1) <= 64:
                print("fail to pack i.")
                return 1
            continue
        data = packer.pack(i)
        assert ilstructs[idx].unpack(data)[0] == i
    print('pass')

    print('testing fixed ints...')
    with io.BytesIO() as f:
        for tp, testvals, failvals in (
                (ss.Uint8, (0, 255), (256,)),
                (ss.Uint16, (0, 255, 256, 65535), (65536,)),
                (ss.Uint32, (0, 255, 256, 65535, 1<<16, (1<<32)-1), (1<<32,)),
                (ss.Uint64, (0, 255, 256, 65535, 1<<16, (1<<32)-1, (1<<64)-1), (1<<64,)),
                (ss.Int8, (0, 1, 127, -128), (128, -129)),
                (ss.Int16, (-(1<<15), (1<<15) - 1), (-(1<<15)-1, 1<<15)),
                (ss.Int32, (-(1<<31), (1<<31)-1), (-(1<<31)-1, 1<<31)),
                (ss.Int64, (-(1<<63), (1<<63)-1), (-(1<<63)-1, 1<<63))
            ):
            print('\ttesting', tp.__name__, end=': ')
            for x in testvals:
                f.seek(0)
                tp.dump(x, f)
                f.seek(0)
                assert tp.load(f) == x
            for x in failvals:
                try:
                    tp.dump(x, f)
                except Exception:
                    pass
                else:
                    print('expected fail on value', x)
                    return 1
            print('pass')
    return


    import argparse
    p = argparse.ArgumentParser(parents=[simpleparser])
    p.add_argument('item', help='thing to dump/load', default='"hello"', nargs='?')
    args = p.parse_args()

    s = ss.Serializer(size=ss.CompactNum)
    thing = ast.literal_eval(args.item)
    data = s.dumps(thing)
    print(repr(data))
    assert s.loads(data) == thing
    assert s.loads(s.dumps(s.Pre(data))) == thing

    altnum = np.uint32(42)
    altrestore = s.loads(s.dumps(altnum))
    assert altrestore == 42
    assert isinstance(altrestore, int)
    assert isinstance(altnum, np.uint32)

    pf = io.BytesIO()
    sf = io.BytesIO()
    af = io.BytesIO()

    simpletest(dtests, args, (thing, pf, sf, af, s.dump), checkmatch=None)
    simpletest(ltests, args, (pf, sf, af, s.load))

if __name__ == '__main__':
    sys.exit(main())
