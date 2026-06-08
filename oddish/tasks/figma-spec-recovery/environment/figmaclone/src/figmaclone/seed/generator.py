"""Synthetic Figma file generator — deterministic given a seed.

Produces a canonical seed (see ``schema``) with a realistic design-system file: a
canvas of frames containing components, text, and rectangles with real Figma node
properties (``fills``, ``absoluteBoundingBox``, ``style``, ``cornerRadius``,
``layoutMode``/``itemSpacing``/``padding*``, ``characters``), plus components,
styles, comments and a version history. Same arguments → byte-identical seed, so
it is safe for reproducible fixtures and tasks.
"""

from __future__ import annotations

import random
from typing import Any

from ..ids import gen_file_key, make_node_id
from . import schema

_PALETTE = {
    "Primary/500": (0.114, 0.306, 0.847),   # #1D4ED8
    "Primary/600": (0.078, 0.247, 0.718),   # #143FB7
    "Neutral/900": (0.067, 0.075, 0.090),   # #111317
    "Neutral/500": (0.420, 0.447, 0.502),   # #6B7280
    "Neutral/0": (1.0, 1.0, 1.0),           # #FFFFFF
    "Surface/100": (0.953, 0.957, 0.965),   # #F3F4F6
}

_TYPE_RAMP = [
    ("Heading/LG", "Inter", "Bold", 24, 32),
    ("Heading/MD", "Inter", "SemiBold", 18, 28),
    ("Body/MD", "Inter", "Regular", 14, 20),
    ("Label/SM", "Inter", "Medium", 12, 16),
]

_FRAME_SPECS = [
    ("Buttons", ["Primary", "Secondary", "Ghost"]),
    ("Cards", ["PricingCard", "StatCard"]),
    ("Inputs", ["TextField", "Select"]),
]

_AUTHORS = [
    {"id": "U1", "handle": "maya.designer", "email": "maya@acme.example"},
    {"id": "U2", "handle": "devon.pm", "email": "devon@acme.example"},
    {"id": "U3", "handle": "sam.eng", "email": "sam@acme.example"},
]


def _rgba(rgb: tuple[float, float, float], a: float = 1.0) -> dict[str, Any]:
    r, g, b = rgb
    return {"r": round(r, 4), "g": round(g, 4), "b": round(b, 4), "a": a}


def _solid_fill(rgb: tuple[float, float, float], a: float = 1.0) -> dict[str, Any]:
    return {"blendMode": "NORMAL", "type": "SOLID", "color": _rgba(rgb, a)}


def _bbox(x: float, y: float, w: float, h: float) -> dict[str, Any]:
    return {"x": x, "y": y, "width": w, "height": h}


def generate(
    *,
    file_name: str = "Design System",
    seed: int = 0,
) -> dict[str, Any]:
    """Generate a deterministic synthetic design-system file as a canonical seed."""
    rng = random.Random(seed)
    file_key = gen_file_key(rng)

    styles: dict[str, Any] = {}
    components: dict[str, Any] = {}
    images: dict[str, Any] = {}

    minor = 1

    def nid() -> str:
        nonlocal minor
        node_id = make_node_id(1, minor)
        minor += 1
        return node_id

    # ---- styles (color + text) ----
    color_style_ids: dict[str, str] = {}
    for name, rgb in _PALETTE.items():
        sid = nid()
        color_style_ids[name] = sid
        styles[sid] = {
            "key": f"style{minor:04d}",
            "name": name,
            "styleType": "FILL",
            "description": f"{name} color token",
        }
    text_style_ids: dict[str, str] = {}
    for name, fam, weight, size, lh in _TYPE_RAMP:
        sid = nid()
        text_style_ids[name] = sid
        styles[sid] = {
            "key": f"style{minor:04d}",
            "name": name,
            "styleType": "TEXT",
            "description": f"{fam} {weight} {size}/{lh}",
        }

    # ---- canvas / frames / nodes ----
    frame_nodes: list[dict[str, Any]] = []
    y = 0.0
    for frame_name, comp_names in _FRAME_SPECS:
        frame_id = nid()
        children: list[dict[str, Any]] = []
        cx = 24.0
        for cname in comp_names:
            comp_id = nid()
            w, h = (160.0, 56.0) if frame_name != "Cards" else (280.0, 360.0)
            # the component frame itself (auto-layout)
            label_id = nid()
            label = {
                "id": label_id,
                "name": "Label",
                "type": "TEXT",
                "characters": cname,
                "style": {
                    "fontFamily": "Inter",
                    "fontWeight": 600,
                    "fontSize": 16 if frame_name != "Cards" else 24,
                    "lineHeightPx": 24 if frame_name != "Cards" else 32,
                    "letterSpacing": 0,
                    "textAlignHorizontal": "CENTER",
                },
                "fills": [_solid_fill(_PALETTE["Neutral/0"] if frame_name == "Buttons" else _PALETTE["Neutral/900"])],
                "absoluteBoundingBox": _bbox(cx + 16, y + 16, w - 32, 24),
            }
            comp = {
                "id": comp_id,
                "name": cname,
                "type": "COMPONENT",
                "layoutMode": "VERTICAL" if frame_name == "Cards" else "HORIZONTAL",
                "itemSpacing": 12 if frame_name == "Cards" else 8,
                "paddingLeft": 24 if frame_name == "Cards" else 16,
                "paddingRight": 24 if frame_name == "Cards" else 16,
                "paddingTop": 24 if frame_name == "Cards" else 12,
                "paddingBottom": 24 if frame_name == "Cards" else 12,
                "cornerRadius": 8,
                "primaryAxisAlignItems": "CENTER",
                "counterAxisAlignItems": "CENTER",
                "fills": [_solid_fill(
                    _PALETTE["Primary/500"] if (frame_name == "Buttons" and cname == "Primary")
                    else _PALETTE["Neutral/0"]
                )],
                "strokes": (
                    [] if frame_name == "Buttons" else [_solid_fill(_PALETTE["Surface/100"])]
                ),
                "absoluteBoundingBox": _bbox(cx, y, w, h),
                "children": [label],
            }
            children.append(comp)
            components[comp_id] = {
                "key": f"comp{comp_id.replace(':', '')}",
                "name": cname,
                "description": f"{cname} component in {frame_name}",
                "containing_frame": {"name": frame_name, "nodeId": frame_id},
            }
            images[comp_id] = f"/static/{file_key}/{comp_id.replace(':', '-')}.png"
            cx += w + 32

        frame = {
            "id": frame_id,
            "name": frame_name,
            "type": "FRAME",
            "layoutMode": "HORIZONTAL",
            "itemSpacing": 32,
            "paddingLeft": 24,
            "paddingTop": 24,
            "paddingRight": 24,
            "paddingBottom": 24,
            "cornerRadius": 0,
            "fills": [_solid_fill(_PALETTE["Surface/100"])],
            "absoluteBoundingBox": _bbox(0, y, 900, 420),
            "children": children,
        }
        frame_nodes.append(frame)
        images[frame_id] = f"/static/{file_key}/{frame_id.replace(':', '-')}.png"
        y += 480.0

    canvas = {
        "id": make_node_id(0, 1),
        "name": "Page 1",
        "type": "CANVAS",
        "backgroundColor": _rgba(_PALETTE["Neutral/0"]),
        "children": frame_nodes,
    }
    document = {"type": "DOCUMENT", "id": "0:0", "name": "Document", "children": [canvas]}

    # ---- comments ----
    comments = [
        {
            "id": "1",
            "message": "Primary button fill should use Primary/500 (#1D4ED8) per the token sheet.",
            "user": _AUTHORS[0],
            "client_meta": {"node_id": frame_nodes[0]["children"][0]["id"]},
            "created_at": "2026-04-12T09:15:00Z",
            "order_id": 1,
        },
        {
            "id": "2",
            "message": "Card padding is 24 on all sides, 12 gap between rows. Radius 8.",
            "user": _AUTHORS[1],
            "client_meta": {"node_id": frame_nodes[1]["children"][0]["id"]},
            "created_at": "2026-04-12T10:02:00Z",
            "order_id": 2,
        },
    ]

    versions = [
        {"id": "v2", "label": "Token cleanup", "description": "Renamed color tokens",
         "created_at": "2026-04-12T08:00:00Z", "user": _AUTHORS[0]},
        {"id": "v1", "label": "Initial system", "description": "First pass",
         "created_at": "2026-04-01T08:00:00Z", "user": _AUTHORS[0]},
    ]

    file_obj = {
        "key": file_key,
        "name": file_name,
        "version": "2",
        "lastModified": "2026-04-12T10:02:00Z",
        "thumbnailUrl": f"/static/{file_key}/thumb.png",
        "editorType": "figma",
        "role": "owner",
        "document": document,
        "components": components,
        "componentSets": {},
        "styles": styles,
        "images": images,
        "comments": comments,
        "versions": versions,
    }

    return schema.normalize({
        "team": {"id": "T1", "name": "Acme Design"},
        "projects": [{"id": "P1", "name": "Product Design", "files": [file_key]}],
        "files": [file_obj],
    })
