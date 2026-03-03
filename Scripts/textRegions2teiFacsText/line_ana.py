from enum import Enum, auto
from typing import NamedTuple

class LineStartCat(Enum):
    UNKNOWN = auto()
    START = auto()
    START_NE = auto()
    MID = auto()
    PREV_HYPHEN = auto()

class LineEndCat(Enum):
    UNKNOWN = auto()
    END = auto()
    MID = auto()
    HYPHEN = auto()

class TriState(Enum):
    UNKNOWN = auto()
    NO = auto()
    YES = auto()


Y = TriState.YES
N = TriState.NO
U = TriState.UNKNOWN

def tri(v):
    if v is True:
        return TriState.YES
    if v is False:
        return TriState.NO
    return TriState.UNKNOWN


class LineAna(NamedTuple):
    parStart: TriState = TriState.UNKNOWN
    parEnd: TriState = TriState.UNKNOWN
    lineStart: LineStartCat = LineStartCat.UNKNOWN
    lineEnd: LineEndCat = LineEndCat.UNKNOWN

    # --- helper methods for updating fields ---
    def with_parStart(self, value: TriState):
        return self._replace(parStart=value)
    def with_parStart(self, value: bool):
        return self._replace(parStart=tri(value))

    def with_parEnd(self, value: TriState):
        return self._replace(parEnd=value)
    def with_parEnd(self, value: bool):
        return self._replace(parEnd=tri(value))

    def with_lineStart(self, value: LineStartCat):
        return self._replace(lineStart=value)

    def with_lineEnd(self, value: LineEndCat):
        return self._replace(lineEnd=value)

    def annotate_line_start(self, ch, prevLine={}, prevCh={}):
        ana = LineStartCat.MID
        if ch.get("upper",None) and self.parStart == Y:
          ana = LineStartCat.START
        elif ch.get("upper",None) and prevCh.get("punct",None):
          ana = LineStartCat.START
        elif ch.get("upper",None):
          ana = LineStartCat.START_NE
        elif prevCh.get("hyphen",None) and self.parStart == N:
          ana = LineStartCat.PREV_HYPHEN
        elif self.parStart == Y:
          ana = LineStartCat.START
        return self.with_lineStart(ana)

    def annotate_line_end(self, ch, nextLine={}, nextCh={}):
        ana = LineEndCat.MID
        if self.parEnd == Y:
          ana = LineEndCat.END
        elif ch.get("hyphen",False) and self.parEnd == N:
          ana = LineEndCat.HYPHEN
        elif ch.get("hyphen",False) and nextLine.parStart == N:
          ana = LineEndCat.HYPHEN
        elif ch.get("punct",False) and self.parEnd == Y:
          ana = LineEndCat.END
        elif ch.get("punct",False) and nextLine.parStart == Y:
          ana = LineEndCat.END
        elif nextCh.get("upper",False) and self.parEnd == Y:
          ana = LineEndCat.END
        elif nextCh.get("upper",False) and nextLine.parStart == Y:
          ana = LineEndCat.END
        return self.with_lineEnd(ana)