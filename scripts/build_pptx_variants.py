"""Genere plusieurs variantes stylistiques de la presentation.

Reutilise scripts/build_pptx.py et remplace dynamiquement la palette pour
chaque variante. Tous les .pptx ont exactement la meme structure (15
slides, schemas identiques), seule la palette change.

Usage :
    python scripts/build_pptx_variants.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from pptx.dml.color import RGBColor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_pptx as bp  # noqa: E402


# =====================================================================
# Palettes - chaque dict surcharge les constantes globales de build_pptx
# Les cles correspondent EXACTEMENT aux noms de constantes (BG, INDIGO...).
# =====================================================================

# --- Variante 1 : Modern data-eng ------------------------------------
# Fond blanc pur, accent teal sature, beaucoup d'air.
MODERN = dict(
    BG=RGBColor(0xFF, 0xFF, 0xFF),
    CARD=RGBColor(0xFA, 0xFA, 0xFA),
    BORDER=RGBColor(0xE2, 0xE8, 0xF0),
    TEXT=RGBColor(0x0F, 0x17, 0x2A),       # slate-900
    MUTED=RGBColor(0x47, 0x55, 0x69),       # slate-600
    FAINT=RGBColor(0x94, 0xA3, 0xB8),       # slate-400
    INDIGO=RGBColor(0x0E, 0x7C, 0x7B),      # teal-700 (accent principal)
    INDIGO_700=RGBColor(0x11, 0x5E, 0x59),  # teal-800
    INDIGO_500=RGBColor(0x14, 0xB8, 0xA6),  # teal-500
    INDIGO_300=RGBColor(0x5E, 0xEA, 0xD4),  # teal-300
    INDIGO_TINT=RGBColor(0xF0, 0xFD, 0xFA),  # teal-50
    GREEN=RGBColor(0x16, 0xA3, 0x4A),
    AMBER=RGBColor(0xCA, 0x8A, 0x04),
)

# --- Variante 2 : Tech blueprint -------------------------------------
# Fond ivoire, accent bleu marine + orange en secondaire.
BLUEPRINT = dict(
    BG=RGBColor(0xFB, 0xF8, 0xF1),
    CARD=RGBColor(0xFF, 0xFD, 0xF5),
    BORDER=RGBColor(0xD6, 0xD3, 0xC4),
    TEXT=RGBColor(0x1F, 0x29, 0x37),
    MUTED=RGBColor(0x57, 0x53, 0x4E),
    FAINT=RGBColor(0x8A, 0x82, 0x6B),
    INDIGO=RGBColor(0x1E, 0x40, 0xAF),     # blue-800
    INDIGO_700=RGBColor(0x1E, 0x3A, 0x8A),  # blue-900
    INDIGO_500=RGBColor(0x25, 0x63, 0xEB),  # blue-600
    INDIGO_300=RGBColor(0x93, 0xC5, 0xFD),  # blue-300
    INDIGO_TINT=RGBColor(0xDB, 0xEA, 0xFE),  # blue-100
    GREEN=RGBColor(0x15, 0x80, 0x3D),
    AMBER=RGBColor(0xEA, 0x58, 0x0C),       # orange en accent secondaire
)

# --- Variante 3 : Editorial mono -------------------------------------
# Fond papier creme, accent rouge vif, contrastes magazine.
EDITORIAL = dict(
    BG=RGBColor(0xF5, 0xF2, 0xEB),
    CARD=RGBColor(0xFF, 0xFD, 0xF8),
    BORDER=RGBColor(0xD4, 0xCF, 0xC0),
    TEXT=RGBColor(0x11, 0x11, 0x11),
    MUTED=RGBColor(0x4A, 0x44, 0x40),
    FAINT=RGBColor(0x8B, 0x82, 0x77),
    INDIGO=RGBColor(0xDC, 0x26, 0x26),     # red-600
    INDIGO_700=RGBColor(0x7F, 0x1D, 0x1D),  # red-900
    INDIGO_500=RGBColor(0xEF, 0x44, 0x44),  # red-500
    INDIGO_300=RGBColor(0xFC, 0xA5, 0xA5),  # red-300
    INDIGO_TINT=RGBColor(0xFE, 0xE2, 0xE2),  # red-100
    GREEN=RGBColor(0x16, 0x7C, 0x3C),
    AMBER=RGBColor(0xB4, 0x53, 0x09),
)

# --- Variante 4 : Mistral dark ---------------------------------------
# Dark theme moderne avec accent orange Mistral.
MISTRAL_DARK = dict(
    BG=RGBColor(0x0F, 0x14, 0x19),         # bleu nuit profond
    CARD=RGBColor(0x1E, 0x29, 0x3B),       # slate-800
    BORDER=RGBColor(0x33, 0x41, 0x55),     # slate-700
    TEXT=RGBColor(0xF8, 0xFA, 0xFC),       # slate-50
    MUTED=RGBColor(0xCB, 0xD5, 0xE1),      # slate-300
    FAINT=RGBColor(0x94, 0xA3, 0xB8),      # slate-400
    INDIGO=RGBColor(0xF9, 0x73, 0x16),     # orange-500 (Mistral)
    INDIGO_700=RGBColor(0xC2, 0x41, 0x0C),  # orange-700
    INDIGO_500=RGBColor(0xFB, 0x92, 0x3C),  # orange-400
    INDIGO_300=RGBColor(0xFD, 0xBA, 0x74),  # orange-300
    INDIGO_TINT=RGBColor(0x44, 0x29, 0x1A),  # orange dilue sur fond sombre
    GREEN=RGBColor(0x4A, 0xDE, 0x80),       # green-400 (visible sur dark)
    AMBER=RGBColor(0xFB, 0xBF, 0x24),       # amber-400
)

THEMES = {
    "modern": MODERN,
    "blueprint": BLUEPRINT,
    "editorial": EDITORIAL,
    "mistral_dark": MISTRAL_DARK,
}


# =====================================================================
# Application
# =====================================================================

# On sauvegarde la palette academic d'origine pour restauration apres coup.
_ACADEMIC_BACKUP = {
    k: getattr(bp, k) for k in MODERN.keys()
}


def apply_palette(palette: dict) -> None:
    """Remplace dans le module build_pptx les constantes de palette."""
    for key, value in palette.items():
        setattr(bp, key, value)


def restore_academic() -> None:
    """Remet les valeurs Academic clean d'origine."""
    for key, value in _ACADEMIC_BACKUP.items():
        setattr(bp, key, value)


def main() -> int:
    docs = ROOT / "docs"
    docs.mkdir(parents=True, exist_ok=True)

    for name, palette in THEMES.items():
        apply_palette(palette)
        out = docs / f"presentation_{name}.pptx"
        bp.build(out)

    # On restaure proprement la palette d'origine au cas ou un autre script
    # importerait build_pptx apres celui-ci.
    restore_academic()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
