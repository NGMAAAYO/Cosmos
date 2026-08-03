"""Small dataclasses compatibility layer for accepted Cosmos strategies."""


class _Field:
    def __init__(self, default=None, default_factory=None):
        self.default = default
        self.default_factory = default_factory


def field(*, default=None, default_factory=None):
    return _Field(default, default_factory)


def dataclass(cls):
    names = list(getattr(cls, "__annotations__", {}))
    if not names:
        # MicroPython intentionally discards variable annotations.  Recover
        # dataclass fields from the concrete defaults that remain on the type.
        for name in dir(cls):
            if name.startswith("_"):
                continue
            value = getattr(cls, name)
            if isinstance(value, _Field) or not callable(value):
                names.append(name)

    def __init__(self, *args, **kwargs):
        if len(args) > len(names):
            raise TypeError("too many positional arguments")
        for index, name in enumerate(names):
            if index < len(args):
                value = args[index]
            elif name in kwargs:
                value = kwargs.pop(name)
            else:
                value = getattr(cls, name, None)
                if isinstance(value, _Field):
                    value = value.default_factory() if value.default_factory is not None else value.default
            setattr(self, name, value)
        if kwargs:
            raise TypeError("unexpected keyword argument")

    cls.__init__ = __init__
    return cls


__all__ = ["dataclass", "field"]
