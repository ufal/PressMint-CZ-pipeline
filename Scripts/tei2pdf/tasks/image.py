from pathlib import Path
from PIL import Image
import io
from reportlab.lib.utils import ImageReader
from tei2pdf.image import get_cached_image
from tei2pdf.tasks.base import BaseTask

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}


class ImageTask(BaseTask):
    def run_at_position(self, canvas, surface, position, shared_context):
        x, y = position

        max_res = self.config.get("max_resolution", 1500)

        print(f"[Image] pos={position}, res={max_res}")

        # draw image onto canvas
        graphic = surface.find("{http://www.tei-c.org/ns/1.0}graphic")
        if graphic is not None:
          self.draw_image(canvas,
                          graphic, 
                          shared_context["tei_id"], 
                          shared_context["surface_id"], 
                          shared_context["cache_dir"],
                          x, y,
                          shared_context["page_width"], shared_context["page_height"], 
                          max_dim=max_res)

    def draw_image(self, canvas, graphic, tei_id, surface_id, cache_dir, xshift, yshift, width, height, max_dim):
      url = graphic.get("url") 
      if url and Path(url).suffix.lower() in IMAGE_EXTENSIONS:
        cached_image = get_cached_image(url, cache_dir, tei_id, surface_id)
        img = Image.open(cached_image)
        ratio = min(max_dim / width, max_dim / height, 1)
        new_size = (int(width * ratio), int(height * ratio))
        img = img.resize(new_size, Image.LANCZOS)
        #img = img.convert("L")  # grayscale
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=80, optimize=True, progressive=True)
        buffer.seek(0)
        canvas.drawImage(ImageReader(buffer), 0 + xshift*width, 0 + yshift*height, width=width, height=height)

