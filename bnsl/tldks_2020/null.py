# This file is based on code from tldks-2020 by Max Halford.
# Original project licensed under the Apache License, Version 2.0.

class Null():
    """Missing values are a pain to work with. This class is here to remove
    some of the pain.
    """

    def __gt__(self, other):
        return False

    def __lt__(self, other):
        return False

    def __eq__(self, other):
        if isinstance(other, Null):
            return True
        return False

    def __hash__(self):
        return hash(None)
