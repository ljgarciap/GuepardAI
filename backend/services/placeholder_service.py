def get_placeholder_image(visual_intent: str) -> dict:
    """
    PLACEHOLDER SERVICE v1.0.
    Returns a structured placeholder object when no brand asset meets the quality threshold.
    """
    return {
        "is_placeholder": True,
        "type": "placeholder",
        "description": f"Visual placeholder for: {visual_intent}",
        "local_path": "placeholder_bg.png", # Fallback string
        "text_overlay": f"STRATEGIC VISUAL:\n{visual_intent.upper()}"
    }
