"""Benchmarks on resource structure: dict vs linked list

100,000 resources
---
add
    :   min    mean     max
dict: 0.01635 0.02225 0.02823
llst: 0.01909 0.01947 0.02085
--------------
remove forward
    :   min    mean     max
dict: 0.03101 0.03494 0.04892
llst: 0.02834 0.03027 0.03424
---------------
remove reversed
    :   min    mean     max
dict: 0.03308 0.03663 0.04517
llst: 0.02868 0.02994 0.03195
-------
iterate
    :   min    mean     max
dict: 0.10184 0.10524 0.11086
llst: 0.24873 0.25631 0.26792


dict is faster for insertion but slower for deletion.
(maybe because of setattr?)
linked list is faster for item removal.
However, for traversal, dict is much faster than linked list.
Since traversal is probably the most commonly performed
operation, final decision should probably be to just use
a dict.
"""
from jhsiao.tests import bench


setup = '''
things = [[i, None, None] for i in range({})]
dgen = iter(things)
lgen = iter(things)

class tst(object):
    def __init__(self):
        self.d = {{}}
        self.l = None
t = tst()

data = [dict(), None]

def add_dict():
    thing = next(dgen)
    t.d[thing[0]] = thing

def add_llst():
    thing = next(lgen)
    first = thing[2] = t.l
    thing[1] = None
    if first is not None:
        first[1] = thing
    t.l = thing

def add_dictl():
    thing = next(dgen)
    data[0][thing[0]] = thing

def add_llstl():
    thing = next(lgen)
    first = thing[2] = data[1]
    thing[1] = None
    if first is not None:
        first[1] = thing
    data[1] = thing
'''


p = bench.parser()
args = p.parse_args()
bench.run(
    title='add',
    dict='add_dict()',
    llst='add_llst()',
    dictl='add_dictl()',
    llstl='add_llstl()',
    setup=setup.format(args.number),
    args=args
)

setup = '''
import random
things = [[i, None, None] for i in range({number})]

class tst(object):
    def __init__(self):
        self.d = {{}}
        self.l = None
t = tst()

def add_dict():
    thing = next(dgen)
    t.d[thing[0]] = thing

def add_llst():
    thing = next(lgen)
    thing[2] = t.l
    thing[1] = None
    if t.l is not None:
        t.l[1] = thing
    t.l = thing

dgen = {order}(things)
lgen = {order}(things)
for _ in things:
    add_dict()
    add_llst()
random.shuffle(things)
dgen = {order}(things)
lgen = {order}(things)

def rm_dict():
    thing = next(dgen)
    t.d.pop(thing[0])

def rm_llst():
    thing = next(lgen)
    pre = thing[1]
    post = thing[2]
    if pre is None:
        t.l = post
    else:
        pre[2] = post
    if post is not None:
        post[1] = pre
'''

bench.run(
    title='remove forward',
    dict='rm_dict()',
    llst='rm_llst()',
    setup=setup.format(number=args.number, order='iter'),
    args=args
)

bench.run(
    title='remove reversed',
    dict='rm_dict()',
    llst='rm_llst()',
    setup=setup.format(number=args.number, order='reversed'),
    args=args
)

setup=setup.format(number=args.number, order='reversed')
raw = args.number
args.number = 100
bench.run(
    title='iterate',
    dict='''
for thing in t.d.values():
    pass
''',
    llst='''
item = t.l
while item is not None:
    item = item[2]
''',
    setup=setup,
    args=args,
)
args.number = raw
