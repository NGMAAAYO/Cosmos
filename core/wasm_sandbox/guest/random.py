"""Deterministic per-entity random facade backed by the Cosmos host ABI."""

from _cosmos import call as _call


_FLOAT_SCALE = 1 << 53
_ERROR = -(1 << 63)


def _index(limit):
    limit = int(limit)
    if limit <= 0:
        raise ValueError("empty range for random selection")
    result = int(_call(52, limit))
    if result == _ERROR:
        raise RuntimeError("game random API call failed")
    return result


def random():
    return _index(_FLOAT_SCALE) / _FLOAT_SCALE


def uniform(a, b):
    return float(a) + (float(b) - float(a)) * random()


def choice(sequence):
    if not sequence:
        raise IndexError("cannot choose from an empty sequence")
    return sequence[_index(len(sequence))]


def randrange(start, stop=None, step=1):
    if stop is None:
        start, stop = 0, start
    start, stop, step = int(start), int(stop), int(step)
    if step == 0:
        raise ValueError("zero step for randrange")
    width = stop - start
    count = (abs(width) + abs(step) - 1) // abs(step)
    if count <= 0 or (width > 0) != (step > 0):
        raise ValueError("empty range for randrange")
    return start + step * _index(count)


def randint(a, b):
    return randrange(int(a), int(b) + 1)


def shuffle(values):
    for index in range(len(values) - 1, 0, -1):
        other = _index(index + 1)
        values[index], values[other] = values[other], values[index]


def seed(value=None):
    # The host derives and owns the per-entity seed.  Player code cannot reset
    # it into a shared/global generator.
    return None
