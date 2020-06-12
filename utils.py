import pathlib
from functools import wraps
from fact_helper_file import get_file_type_from_path


def get_file_type(path):
    path = pathlib.Path(path)

    # Make sure symlinks aren't followed
    if path.is_symlink():
        return {"mime": "inode/symlink", "full": ""}

    return get_file_type_from_path(path)


def cached_property(func):
    """
    Decorator for class properties so they are computed once, and then
    stored as an attribute of the class
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        instance = args[0]
        property_name = "_{}_{}".format(instance.__class__, func.__name__)

        if not hasattr(instance, property_name):
            setattr(instance, property_name, func(*args, **kwargs))

        return getattr(instance, property_name)

    return wrapper
