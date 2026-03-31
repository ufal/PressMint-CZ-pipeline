from reportlab.lib import colors


def resolve_color(value):
    if isinstance(value, str):
        # Named color (colors.red, colors.black, ...)
        if hasattr(colors, value):
            return getattr(colors, value)

        # Hex color "#RRGGBB"
        if value.startswith("#") and len(value) == 7:
            r = int(value[1:3], 16) / 255
            g = int(value[3:5], 16) / 255
            b = int(value[5:7], 16) / 255
            return colors.Color(r, g, b)

        raise ValueError(f"Unknown color: {value}")

    return value


def normalize_style(style):
    """Convert color strings to ReportLab color objects."""
    style = dict(style)

    if "color" in style:
        style["color"] = resolve_color(style["color"])

    if "fill" in style:
        style["fill"] = resolve_color(style["fill"])

    return style



class StyleResolver:
    def __init__(self, styles_config):
        """
        styles_config example:

        styles:
          zone_base:
            pattern: [zone]
            width: 1
            color: black
        """

        self.rules = []

        for index, (name, rule) in enumerate(styles_config.items()):
            pattern = set(rule.get("pattern", []))

            props = {
                k: v for k, v in rule.items()
                if k != "pattern"
            }

            self.rules.append({
                "name": name,
                "pattern": pattern,
                "props": props,
                "specificity": len(pattern),
                "order": index,  # preserves YAML order
            })

    def resolve(self, features):
        """
        features: iterable of tokens, e.g.
        {"zone", "column", "polygon", "linked"}
        """

        features = set(features)
        matched_rules = []

        # 1. match rules
        for rule in self.rules:
            if rule["pattern"].issubset(features):
                matched_rules.append(rule)

        # 2. sort by specificity, then by order
        matched_rules.sort(key=lambda r: (r["specificity"], r["order"]))

        # 3. merge styles
        style = {}
        for rule in matched_rules:
            style.update(rule["props"])

        return style

    def resolve_full(self, features, local_style=None):
        """
        Full pipeline:
        - resolve global styles
        - apply local overrides
        - normalize colors
        """

        base_style = self.resolve(features)

        if local_style:
            base_style.update(local_style)

        return normalize_style(base_style)

    def apply(self, canvas, features={}):
        style = self.resolve(features)
    
        # ---- stroke color ----
        if "color" in style:
            color = resolve_color(style["color"])
            canvas.setStrokeColor(color)
    
        # ---- fill color ----
        if "fill" in style:
            fill = resolve_color(style["fill"])
            canvas.setFillColor(fill)
    
        # ---- line width ----
        if "width" in style:
            canvas.setLineWidth(style["width"])
    
        # ---- dash pattern ----
        if "dash" in style:
            dash = style["dash"]
    
            if dash in (None, "solid"):
                canvas.setDash()  # reset
            elif isinstance(dash, (list, tuple)):
                canvas.setDash(dash)
            elif dash == "dashed":
                canvas.setDash([6, 3])
            elif dash == "dotted":
                canvas.setDash([1, 2])
            else:
                raise ValueError(f"Unknown dash style: {dash}")
    
        # ---- transparency ----
        if "alpha" in style:
            alpha = style["alpha"]
    
            # ReportLab uses separate stroke/fill alpha
            canvas.setStrokeAlpha(alpha)
            canvas.setFillAlpha(alpha)