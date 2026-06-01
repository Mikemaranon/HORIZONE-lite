class RequestError(ValueError):
    pass


class ResourceNotFoundError(LookupError):
    pass


class ConflictError(RuntimeError):
    pass
