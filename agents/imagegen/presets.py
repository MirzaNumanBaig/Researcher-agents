"""Style presets: the closing style sentence of the prompt plus default lighting hints. Add a preset by adding an entry here."""

PRESETS = {
    "candid_news_photo": {"label": "candid news photo (default)",
                          "style": "Candid editorial news photograph with natural film-like colour and subtle grain.",
                          "tail": "Natural skin texture with visible pores and small imperfections, a candid unposed moment, shot on a full-frame camera, fine film grain, true-to-life colour.",
                          "tail_short": "Natural skin texture with visible pores, candid unposed moment, full-frame camera, fine film grain, true-to-life colour."},
    "glossy_magazine": {"label": "glossy magazine",
                        "style": "Polished glossy magazine editorial photograph with clean high-key lighting, crisp detail and refined colour.",
                        "tail": "Polished magazine photograph, natural skin texture with visible pores, crisp detail, shot on a full-frame camera, true-to-life colour."},
    "cinematic_still": {"label": "cinematic still",
                        "style": "Cinematic widescreen frame with a teal and amber colour grade, shallow depth of field and a subtle anamorphic flare.",
                        "tail": "Cinematic still, natural skin texture with visible pores, teal and amber grade, shot on a full-frame camera, fine film grain."},
    "soft_illustration": {"label": "soft illustration",
                          "style": "Soft hand-painted editorial illustration with gentle brush texture, muted watercolour tones and clean simple shapes."},
}


def get(name):
    return PRESETS.get((name or "").strip().lower(), PRESETS["candid_news_photo"])
