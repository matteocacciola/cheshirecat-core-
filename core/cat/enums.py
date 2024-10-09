from enum import Enum as BaseEnum, EnumMeta


class MetaEnum(EnumMeta):
    """
    Enables the use of the `in` operator for enums.
    For example:
    if el not in Elements:
        raise ValueError("invalid element")
    """

    def __contains__(cls, item):
        try:
            cls(item)  # pylint: disable=E1120
        except ValueError:
            return False
        return True


class Enum(BaseEnum, metaclass=MetaEnum):
    def __str__(self):
        return self.value