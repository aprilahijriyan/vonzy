import copy
import collections.abc

class AttribDict(dict, collections.abc.MutableMapping):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

    # def copy(self):
    #     return copy.deepcopy(self)
