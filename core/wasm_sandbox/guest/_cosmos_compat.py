"""WASI-safe replacements for CPython descriptors broken by py2wasm #13."""


class staticmethod:
    def __init__(self, function):
        self.function = function

    def __get__(self, instance, owner=None):
        return self.function


class classmethod:
    def __init__(self, function):
        self.function = function

    def __get__(self, instance, owner=None):
        if owner is None:
            owner = type(instance)

        def bound(*args, **kwargs):
            return self.function(owner, *args, **kwargs)

        return bound


class property:
    def __init__(self, getter=None, setter=None, deleter=None, doc=None):
        self.fget = getter
        self.fset = setter
        self.fdel = deleter
        self.__doc__ = doc

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        if self.fget is None:
            raise AttributeError("unreadable attribute")
        return self.fget(instance)

    def __set__(self, instance, value):
        if self.fset is None:
            raise AttributeError("cannot set attribute")
        self.fset(instance, value)

    def __delete__(self, instance):
        if self.fdel is None:
            raise AttributeError("cannot delete attribute")
        self.fdel(instance)

    def getter(self, function):
        return property(function, self.fset, self.fdel, self.__doc__)

    def setter(self, function):
        return property(self.fget, function, self.fdel, self.__doc__)

    def deleter(self, function):
        return property(self.fget, self.fset, function, self.__doc__)
