from tei2pdf.tasks.base import BaseTask
from tei2pdf.style_resolver import StyleResolver
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import re


pdfmetrics.registerFont(TTFont("DejaVu", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))



def fit_text_to_box(c, text, box_width, box_height,
                    font_name="Helvetica",
                    max_font_size=20,
                    min_font_size=3):
    """
    Returns the largest font size that fits inside the box.
    """

    font_size = max_font_size

    while font_size >= min_font_size:
        text_width = pdfmetrics.stringWidth(text, font_name, font_size)
        text_height = font_size  # approx baseline height

        if text_width <= box_width and text_height <= box_height:
            return font_size

        font_size -= 0.5

    return min_font_size

def get_lb_text(lb):
    """
    Returns all text between this <lb> and the next <lb>,
    including inline elements like <pc>.
    """

    parts = []

    # text directly after <lb/>
    if lb.tail:
        parts.append(lb.tail)

    # iterate over following siblings
    for sib in lb.itersiblings():
        # stop at next <lb>
        if sib.tag.endswith("lb"):
            break

        # element text
        if sib.text:
            parts.append(sib.text)

        # element tail
        if sib.tail:
            parts.append(sib.tail)

    return "".join(parts).strip()


def is_no_text_after_element(elem):
    current = elem
    next = current.getnext()
    while next is not None:
      if next.text and next.text.strip():
        return False
      elif next.tail and next.tail.strip():
        return False
      else:
        next = next.getnext()
    return True

def is_element_preceding(elem, tag):
    current = elem

    while current is not None:
        parent = current.getparent()
        if parent is None:
            return False

        # 1. Check immediate previous sibling
        prev = current.getprevious()
        while prev is not None:
            # If there's text immediately after previous element → stop
            if prev.tail and prev.tail.strip():
                return False
            elif prev.tag.endswith(tag): # found preceding element with the tag
                return True
            elif prev.text and prev.text.strip(): # skipping <p> with text content
                return False
            else:
                prev = prev.getprevious()

        # 2. No previous sibling → check parent text (text before first child)
        if parent.text and parent.text.strip():
            return False

        # 3. Move up to parent and continue
        current = parent

    return False

default_config = {}

class TextTask(BaseTask):
    def __init__(self, config):
        super().__init__({**default_config, **config})

    def run_at_position(self, canvas, surface, position, shared_context):
        xpos, ypos = position
        w=shared_context["page_width"]
        h=shared_context["page_height"]
        
        print(f"[Text] pos={position}")
        
        line_zones = {}
        for zone in surface.findall(".//{http://www.tei-c.org/ns/1.0}zone[@type='line']"):
          zid = zone.attrib.get("{http://www.w3.org/XML/1998/namespace}id")
          if not all(zone.get(a) for a in ("ulx", "uly", "lrx", "lry")):
            continue
          line_zones[zid] = {
            "ulx": float(zone.get("ulx")),
            "uly": float(zone.get("uly")),
            "lrx": float(zone.get("lrx")),
            "lry": float(zone.get("lry")),
          }
        ln = 0
        for lb in shared_context["root"].findall(".//{http://www.tei-c.org/ns/1.0}lb"):
          facs = lb.get("facs")
          if not facs:
              continue
          facs_id = facs.lstrip("#")
          # Only print if zone belongs to this surface
          if facs_id not in line_zones:
              continue
          ln += 1
          text = get_lb_text(lb)
          lb_id = lb.attrib.get("{http://www.w3.org/XML/1998/namespace}id")
          if not text:
              continue
          zone = line_zones[facs_id]

          ulx = zone["ulx"]
          uly = zone["uly"]
          lrx = zone["lrx"]
          lry = zone["lry"]

          width = lrx - ulx
          height = lry - uly

          # Optional: scale font to line height
          font_size = fit_text_to_box(canvas, text, width, height, font_name="DejaVu", max_font_size=height, min_font_size=3)
          canvas.setFont("DejaVu", font_size)
          ## canvas.setFillColor(colors.black)

          text_width = pdfmetrics.stringWidth(text, "DejaVu", font_size)
          # Center horizontally
          x = ulx + (width - text_width) / 2
          # Vertically center baseline
          y = uly + (height - font_size) / 2 + font_size
          
          """
          # beginning of paragraph
          if lb.getnext() and lb.getnext().tag.endswith("p"):
            ##canvas.setFillColor(colors.green)
            canvas.rect(*self.transform_position((ulx, uly), xpos, ypos, w, h), 6, uly-lry, stroke=0, fill=1)

          # end of paragraph
          if is_no_text_after_element(lb) and lb.getparent().tag.endswith("p"):
            ##canvas.setFillColor(colors.orange)
            canvas.rect(*self.transform_position((lrx, lry), xpos, ypos, w, h), 6, uly-lry, stroke=0, fill=1)  
          """
          # Draw text
          shared_context["styles"].apply(canvas, {"text"})
          canvas.drawString(*self.transform_position((x, y), xpos, ypos, w, h), text)
          """
          # Draw line ID for debugging
          canvas.setFont("DejaVu", font_size * 0.6)
          ##canvas.setFillColor(colors.red)
          idx = re.sub(r'[pclb]','','.'.join(lb_id.split('.')[1:]))
          canvas.drawString(x+w*xpos, y+h*ypos, f"({ln}){idx}")
          
          canvas.setDash()
          if is_element_preceding(lb,'pb'):
            print(f"LB {lb_id} is preceded by page break")
            ##canvas.setFillColor(colors.purple)
            canvas.rect(ulx-9+w*xpos, h*ypos - uly, 6, uly-lry, stroke=0, fill=1)
          if is_element_preceding(lb,'cb'):
            print(f"LB {lb_id} is preceded by column break")
            ##canvas.setFillColor(colors.cyan)
            canvas.rect(ulx-3+w*xpos, h*ypos - uly, 6, uly-lry, stroke=0, fill=1)
          """
