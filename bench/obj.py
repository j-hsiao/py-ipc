"""Object and attr access vs list, unpack or single...

results:
1. using object.attr is slower than list index
2. If len(lst) < 8:
    accessing 1 item: get it directly
    accessing >1: just unpack the whole thing is faster

"""

from jhsiao.tests import bench










p = bench.parser()
p.add_argument('-a', '--args', type=int, help='number of attrs', default=5)
args = p.parse_args()


def setup(args):
    base = '''
class Dummy(object):
    def __init__(self):
        for i in range({nargs}):
            setattr(self, 'arg{{}}'.format(i), i)

obj = Dummy()
lst = list(range({nargs}))'''
    setup = [base.format(nargs=args.args)]
    for i in range(args.args):
        setup.append('arg{} = {}'.format(i, i))
    return '\n'.join(setup)

tests = {
    'unpackall': '{} = lst'.format(', '.join(['arg{}'.format(i) for i in range(args.args)]))
}
indivlit = []
indivarg = []
indivatr = []
sliceupk = []
for accessed in range(0, args.args):
    indivlit.append('arg{i} = lst[{i}]'.format(i=accessed))
    indivarg.append('arg{i} = lst[arg{i}]'.format(i=accessed))
    indivatr.append('arg{i} = obj.arg{i}'.format(i=accessed))
    sliceupk.append('arg{i}'.format(i=accessed))
    tests['indivlit{}/{}'.format(accessed+1, args.args)] = '\n'.join(indivlit)
    tests['indivarg{}/{}'.format(accessed+1, args.args)] = '\n'.join(indivarg)
    tests['indivatr{}/{}'.format(accessed+1, args.args)] = '\n'.join(indivatr)
    tests['slc{}/{}'.format(accessed+1, args.args)] = '{} = lst[:{}]'.format(', '.join(sliceupk), accessed+1)

bench.run(
    title='access'.format(args.args),
    **tests,
    args=args,
    setup=setup(args)
)
