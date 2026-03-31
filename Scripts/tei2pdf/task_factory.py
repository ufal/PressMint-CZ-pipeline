###
from tei2pdf.tasks.base import BaseTask
from tei2pdf.tasks.image import ImageTask
from tei2pdf.tasks.zone import ZoneTask
#from tei2pdf.tasks.reading_order import ReadingOrderTask
from tei2pdf.tasks.text import TextTask
#from tei2pdf.tasks.debug_idx import DebugIDXTask
from tei2pdf.tasks.element import ElementTask



TASK_REGISTRY = {
    "image": ImageTask,
    "zone": ZoneTask,
#    "readingOrder": ReadingOrderTask,
    "text": TextTask,
#    "debugIDX": DebugIDXTask,
    "element": ElementTask
}

def create_task(task_config):
    name = task_config["name"]

    if name not in TASK_REGISTRY:
        raise ValueError(f"Unknown task: {name}")

    cls = TASK_REGISTRY[name]
    return cls(task_config)