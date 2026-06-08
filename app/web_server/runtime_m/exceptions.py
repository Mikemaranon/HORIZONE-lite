class RuntimeRequestError(ValueError):
    pass


class RuntimeResourceNotFoundError(LookupError):
    pass


class RuntimeConflictError(RuntimeError):
    pass
