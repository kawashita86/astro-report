"""Pure computation: no I/O, no clock, no network, no randomness, no environment.

``core/`` never imports from ``shell/``. The single declared exception to purity
is the ephemeris, which reads its vendored ``.se1`` files from disk inside
``core/ephemeris/`` (AD-1). A second exception is a spine amendment.
"""
