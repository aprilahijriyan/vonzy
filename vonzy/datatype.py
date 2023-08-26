from addict import Dict


class AttrDict(Dict):
    def __missing__(self, key):
        raise KeyError(key)
