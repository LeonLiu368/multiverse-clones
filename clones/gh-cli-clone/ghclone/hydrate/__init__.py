"""Hydration: GitHub repo -> ghc/Forgejo repo.

Engine A (`migrate`): Forgejo native GitHub downloader, one API call. Implemented.
Engine B (`snapshot` + `apply`): freeze GitHub to a local artifact, then replay
offline into Forgejo. Scaffolded here; see docs/HYDRATION.md for the spec.
"""
