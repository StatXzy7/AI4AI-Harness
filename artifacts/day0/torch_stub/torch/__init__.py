# Minimal torch stub: only what repro/common.py touches on the CPU analysis path
# (seed setting + cuda availability probes). NOT a real torch.
import sys


def manual_seed(seed):
    import random
    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed % (2**32))
    except ImportError:
        pass


class _Cuda:
    @staticmethod
    def is_available():
        return False

    @staticmethod
    def manual_seed_all(seed):
        pass


cuda = _Cuda()
bfloat16 = "bfloat16"
float16 = "float16"
float32 = "float32"


def __getattr__(name):
    # tolerate any other attribute access: returns a decorator factory that
    # passes functions through unchanged (handles @torch.no_grad() etc.)
    def _factory(*args, **kwargs):
        def deco(f):
            return f
        return deco
    return _factory
