"""Implement poller interface using select.select."""
import select

from . import poller

class SelectPoller(poller.Poller):
    def __init__(self, rgen, wgen):
        super(SelectPoller, self).__init__(rgen, wgen)
