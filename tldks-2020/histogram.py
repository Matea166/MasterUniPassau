import bisect
import collections
import copy
import decimal

from . import bucket
from . import null


class Histogram:
    def __init__(self, m, n):
        self.m = m
        self.n = n
        self.buckets = []
        self.null_frac = decimal.Decimal(0)

    def __copy__(self):
        hist = Histogram(self.m, self.n)
        hist.buckets = [copy.copy(b) for b in self.buckets]
        hist.null_frac = self.null_frac
        return hist

    def __len__(self):
        return len(self.buckets)

    def __getitem__(self, idx):
        if isinstance(idx, slice):
            h = Histogram(self.m, self.n)
            h.buckets = self.buckets[idx]
            return h
        return self.buckets[idx]

    def __mul__(self, other):
        """Multiply two histograms (Decimal-safe)."""
        hist = copy.copy(self)

        for i, b in enumerate(hist.buckets):
            if b.cardinality == 1:
                p = other.p(b.left)
                p = decimal.Decimal(str(p))
            else:
                _, buckets = other.find_buckets(b.left, b.right)
                if not buckets:
                    p = decimal.Decimal(0)
                else:
                    total = sum(bb.frequency for bb in buckets)
                    p = total / decimal.Decimal(len(buckets))

            hist.buckets[i].frequency *= p

        return hist

    def fit(self, values):
        if not values:
            raise ValueError("values is empty")

        counter = collections.Counter(values)

        try:
            self.null_frac = decimal.Decimal(counter.pop(null.Null()))
        except KeyError:
            self.null_frac = decimal.Decimal(0)

        self.buckets = []
        for val, cnt in counter.most_common(self.m):
            self.buckets.append(bucket.Bucket(val, val, cnt, 1))
            counter.pop(val)

        if self.n > 0:
            height = (
                len(values)
                - sum(b.frequency for b in self.buckets)
                - self.null_frac
            ) / self.n

            current = None
            for val, cnt in sorted(counter.items()):
                if current is None:
                    current = bucket.Bucket(val, val, cnt, 1)
                else:
                    current += bucket.Bucket(val, val, cnt, 1)

                if current.frequency >= height:
                    self.buckets.append(current)
                    current = None

            if current is not None:
                self.buckets.append(current)

        total = decimal.Decimal(len(values))
        for b in self.buckets:
            b.frequency /= total

        self.null_frac /= total
        self.buckets.sort(key=lambda b: b.left)

        return self

    def find_buckets(self, left, right):
        idxs, buckets = [], []
        for i, b in enumerate(self.buckets):
            if b.left <= right and b.right >= left:
                idxs.append(i)
                buckets.append(b)
        return idxs, buckets

    def find_bucket(self, val):
        if not self.buckets:
            return -1, None

        if val < self.buckets[0].left or val > self.buckets[-1].right:
            return -1, None

        i = bisect.bisect_left([b.left for b in self.buckets], val)
        i = min(i, len(self.buckets) - 1)

        b = self.buckets[i]
        if b.left <= val <= b.right:
            return i, b

        return -1, None

    def p(self, val):
        """Return P(val)."""
        if val is None:
            return self.null_frac

        _, b = self.find_bucket(val)
        if b is None:
            return decimal.Decimal(0)

        return b.frequency / b.cardinality

    def __repr__(self):
        return "\n".join(str(b) for b in self.buckets)
