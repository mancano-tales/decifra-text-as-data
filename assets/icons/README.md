# Decifra Brand Icons & Candidate Marks

This directory contains candidate visual identity assets and icon marks for the **Decifra** text-as-data application (web client, Tauri/desktop packaging, documentation, and academic publications).

---

## Conceptual Foundation

Decifra bridges unstructured natural language with structured, verifiable scientific data. Its visual identity draws directly from two foundational historical metaphors:

1. **The Rosetta Stone (1799 / 1822)**:
   The universal archetype of text decipherment. Just as the Rosetta Stone aligned three parallel registers (hieroglyphs, demotic, and ancient Greek as the known key), Decifra aligns unstructured corpus text with structured LLM extractions, validated against an auditable human gold standard (Cohen's kappa).

2. **The Sacred Ibis (*Threskiornis aethiopicus*) & Thoth**:
   In ancient Egyptian theology, Thoth (*Djehuti*) is the patron deity of scribes, measurement, cataloging, and empirical truth (*Ma'at*). Scribes viewed the ibis's slender down-curved beak as the living counterpart to the reed pen (*calamus*) used to transcribe records onto papyrus.

---

## Asset Inventory

All assets in this directory are provided with **true alpha transparency** (no bounding box, clean anti-aliased contours) ready for both light and dark backgrounds.

**Current official mark (2026-09-08, author's call)**: `decifra_ibis_standing_hieroglyph_stele.png` (dark)
and `decifra_ibis_standing_hieroglyph_stele_white.png` (dark-mode), wired into `frontend/public/favicon.{png,svg}`,
`frontend/public/brand-mark.png`, and their `site/assets/` mirrors. This is the **third** mark promoted to
"official" in two days — first the Rosetta Stele Flat Base emblem below, then briefly a Squircle mark (promoted
and reverted same day after failing a 16px legibility test), now this one. **Nothing has been deleted**: every
prior candidate stays in this directory and in git history as a record of the decision path; only the files
actually wired into the app (`frontend/public/`, `site/assets/`) get overwritten with each promotion, same as
before.

| File | Description | Recommended Usage |
| :--- | :--- | :--- |
| `decifra_ibis_standing_hieroglyph_stele.png` | **Current Official Mark**: Full standing sacred ibis (legs, wing detail) beside a Rosetta stele rendered with a woven/hieroglyph-like dash texture instead of plain data bars — the ibis-and-inscribed-stone metaphor drawn literally. | Unified application brand icon: browser favicon, web app header, Tauri desktop icon, Quarto site logo, splash/hero use. Known trade-off, accepted by the author: at 16-32px favicon scale the fine texture and legs are not individually legible. |
| `decifra_ibis_standing_hieroglyph_stele_white.png` | Inverted white silhouette of the current official mark. | Dark-mode favicon/header equivalent. |
| `rosetta_stele_flat_base_transparent.png` | **Former official mark (2026-09-07 to 2026-09-08)**: Solid Rosetta stele with clean flat base, ibis silhouette, and horizontal text data strata in negative space. | Superseded; kept as candidate/history. Still viable for contexts wanting the more abstracted (less illustrative) stele treatment. |
| `ibis_head_s_curve_transparent.png` | Minimalist S-curve bust and curved beak of the sacred ibis (dark stroke). | Primary candidate for browser favicon (16px/32px) and minimal header glyph. |
| `ibis_head_s_curve_white_transparent.png` | Inverted white S-curve ibis bust for dark mode backgrounds. | Dark-mode favicon, dark UI headers, and terminal CLI badges. |
| `ibis_standing_monoline_transparent.png` | Standing sacred ibis in clean vector line art with filled head/beak and contoured body. | Documentation diagrams, hero illustrations, and about dialogs. |
| `ibis_standing_monoline_white_transparent.png` | Inverted white standing sacred ibis line art for dark backgrounds. | Dark-mode documentation diagrams and hero sections. |
| `rosetta_decifra_logo_transparente.png` | Complete mark: Fractured Rosetta stele, ibis profile, horizontal text strata, and "DECIFRA" wordmark. | Application splash screen, repository banner, documentation header. |
| `rosetta_decifra_emblema_transparente.png` | Isolated emblem: The fractured stele and ibis profile without lower typography. | Desktop app icon (Tauri / OS dock), primary avatar, favicon candidate. |
| `ibis_canon_preto_transparente.png` | Full-body sacred ibis in strict Egyptian hieroglyphic canon (Gardiner G26) atop lotus standard (dark stroke). | Academic papers, methodological reports, presentation slides. |
| `ibis_canon_branco_transparente.png` | Inverted white silhouette of the canonical ibis for dark backgrounds. | Dark-mode interface headers, terminal/CLI splash banners. |
| `ibis_monoline_transparent.png` | Contemporary Scandinavian/Swiss monoline continuous-line mark (dark line). | Web UI navigation bar, inline indicators, clean vector mark. |
| `ibis_monoline_white_transparent.png` | Inverted white continuous-line monoline mark. | Dark-mode navigation bar and dark theme UI elements. |

---

## Technical Specifications

- **Format**: PNG with 32-bit RGBA (alpha channel transparency).
- **Color Palettes**:
  - Dark strokes: Deep Slate (`#0F172A`) / Carbon Black (`#09090B`).
  - Light strokes: Pure White (`#FFFFFF`) / Off-White (`#F8FAFC`).
- **Compatibility**: High DPI / Retina ready (minimum 500px resolution, down-scalable to 16px).
