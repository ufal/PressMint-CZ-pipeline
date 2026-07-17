from pathlib import Path
import requests
from io import BytesIO

headers = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0 Safari/537.36"
    )
}

def get_cached_image(url: str,
                     cache_root: Path | None,
                     tei_id: str,
                     surface_id: str) -> Path | BytesIO:
    """
    Cache IIIF image using:
        cache_root / tei_xml_id / surface_xml_id + extension
    """

    if cache_root is None:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return BytesIO(response.content)

    # Extract extension safely
    ext = Path(url.split("?")[0]).suffix.lower()
    if not ext:
        ext = ".jpg"

    # Create directory: cache/<tei_xml_id>/
    target_dir = cache_root / tei_id
    target_dir.mkdir(parents=True, exist_ok=True)

    # Filename: surface_xml_id + extension
    filename = surface_id + ext
    cached_path = target_dir / filename

    if not cached_path.exists():
        print(f"Downloading: {url}")
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        cached_path.write_bytes(response.content)
    else:
        print(f"Using cached: {cached_path}")

    return cached_path