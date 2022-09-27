import ast
import pickle
import time
import io

from jhsiao.ipc import sserial as ss
from jhsiao.tests.profile import simpletest, simpleparser
from jhsiao.scope import Scope
from jhsiao.utils.fio import SeqWriter


with Scope('s') as s:
    def pkldump(thing, serializer, pf, sf):
        pf.seek(0)
        return pickle.dump(thing, pf)

    def ssdump(thing, serializer, pf, sf):
        sf.seek(0)
        return serializer.dump(thing, sf)

    def pklload(thing, serializer, pf, sf):
        pf.seek(0)
        return pickle.load(pf)

    def ssload(thing, serializer, pf, sf):
        sf.seek(0)
        return serializer.load(sf)

    tests = dict(s.items())

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(parents=[simpleparser])
    p.add_argument('item', help='thing to dump/load', default='"hello"', nargs='?')
    args = p.parse_args()

    s = ss.Serializer()
    simpletest(
        tests, args, (ast.literal_eval(args.item), s, io.BytesIO(), io.BytesIO()),
        checkmatch=None
    )
