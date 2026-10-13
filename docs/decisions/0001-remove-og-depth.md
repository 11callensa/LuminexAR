# 0001 — Remove OG_depth

- **Status:** Accepted
- **Date:** 2026-10-13

## Context

`LuminexScripts/Depth_Camera/OG_depth/` was the first depth pipeline: Python scripts that
captured ToF frames, estimated normals, segmented surfaces and sent them to Godot
(`surface_visualiser.py`). `CAPE_depth` (C++, CAPE plane extraction) replaced it and is what
`game_manager.gd` launches today. The only remaining reference was a commented-out launch line.

## Decision

Delete `OG_depth/` from the tree. Legacy code lives in git history, not alongside the code
that replaced it.

## Recovering it

The last commit containing it is tagged `legacy/og-depth`:

```bash
git show legacy/og-depth:LuminexScripts/Depth_Camera/OG_depth/surface_visualiser.py
git checkout legacy/og-depth -- LuminexScripts/Depth_Camera/OG_depth
```

## Consequences

- One depth pipeline to maintain and document.
- The pattern for future removals: tag, delete, record here.
