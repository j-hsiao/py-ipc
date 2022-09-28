import ast
import pickle
import time
import io

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

if __name__ == '__main__':
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

    pf = io.BytesIO()
    sf = io.BytesIO()
    af = io.BytesIO()

    simpletest(dtests, args, (thing, pf, sf, af, s.dump), checkmatch=None)
    simpletest(ltests, args, (pf, sf, af, s.load))
