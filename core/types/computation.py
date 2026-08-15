"""``ComputationConfig``: the frozen, in-memory shape of ``data/computation.toml``
(AD-18) -- the one home for every astronomical tuning value.

These types are pure data: no I/O, no defaults guessed here, no logic beyond
the dataclass machinery itself. Living in ``core/types/`` rather than
``shell/`` lets core functions type-hint on ``ComputationConfig`` as an
argument without importing anything from ``shell/`` (AD-1). ``shell/computation.py``
is the only place that constructs one, by reading and validating the file.

Grouped by TOML table -- an orbs value, a house-system value, a bodies value,
a rulers value, a harmonic value -- rather than flattened onto one dataclass,
mirroring the file's own structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType

__all__ = [
    "Bodies",
    "ComputationConfig",
    "HarmonicRule",
    "HouseSystem",
    "Orbs",
    "Rulers",
]


@dataclass(frozen=True)
class Orbs:
    """The two configured aspect orbs. Range validation happens once, at load
    time, in ``shell/computation.py`` -- by the time a value reaches here it
    has already been confirmed within its permitted range."""

    natal: Decimal
    transit: Decimal


@dataclass(frozen=True)
class HouseSystem:
    """The house system computation uses. Placidus is the only value defined
    anywhere in the planning artifacts, but nothing here hardcodes that --
    the file is still the one home for the value."""

    name: str


@dataclass(frozen=True)
class Bodies:
    """The transiting-body sets from PRD FR-9. Deliberately excludes the
    transiting Moon everywhere; it enters the Report only through Lunations."""

    fast: tuple[str, ...]
    slow: tuple[str, ...]


@dataclass(frozen=True)
class Rulers:
    """Traditional and modern house-ruler tables, one entry per zodiac sign.

    ``MappingProxyType``, not a plain ``dict`` -- a frozen dataclass only
    stops reassigning the *field*; without this, the dict object it points at
    would still be mutable in place.
    """

    traditional: MappingProxyType[str, str]
    modern: MappingProxyType[str, str]


@dataclass(frozen=True)
class HarmonicRule:
    """The FR-13 harmonic/disharmonic classification table.

    Trine and sextile are always harmonic; square and opposition are always
    disharmonic. Conjunction is classified by which body is transiting rather
    than by aspect type: a body named in neither conjunction list is neutral
    on conjunction -- present in neither day list, never forced to a value.
    """

    harmonic_aspects: tuple[str, ...]
    disharmonic_aspects: tuple[str, ...]
    harmonic_conjunction_bodies: tuple[str, ...]
    disharmonic_conjunction_bodies: tuple[str, ...]


@dataclass(frozen=True)
class ComputationConfig:
    """The full, validated contents of ``data/computation.toml``.

    Passed explicitly wherever it is needed -- never read ambiently from a
    module global, the environment, or a file at call time (AD-18). This
    story loads and validates the value; nothing consumes it yet.
    """

    version: int
    content_hash: str
    orbs: Orbs
    house_system: HouseSystem
    bodies: Bodies
    rulers: Rulers
    harmonic: HarmonicRule
