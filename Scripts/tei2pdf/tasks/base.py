
class BaseTask:
    def __init__(self, config):
        print(f"Initializing task with config: {config}")
        self.config = config
        self.filter = list()

    def get_positions(self):
        positions = self.config.get("position")

        if positions is None:
            return [(0, 0)]

        # normalize single [x, y]
        if isinstance(positions[0], (int, float)):
            return [tuple(positions)]

        return [tuple(p) for p in positions]

    def get_style_tokens(self):
        return set(self.config.get("style_tokens", []))

    def get_local_style(self):
        return dict(self.config.get("style", {}))

    def match_features(self, element_features, shared_context):
        for filter in self.filter:
          if filter.issubset(element_features):
            return True
        return False

    def run(self, canvas, surface, shared_context):
        """Main entry point"""
        canvas.saveState()
        for pos in self.get_positions():
            self.run_at_position(canvas, surface, pos, shared_context)
        canvas.restoreState()


    def run_at_position(self, canvas, surface, position, shared_context):
        """Override in subclasses"""
        raise NotImplementedError
    
    def parse_points(self, points_str):
        points = []
        for part in points_str.split():
            x_str, y_str = part.split(",")
            points.append((float(x_str), float(y_str)))
        return points
    
    def transform_position(self, point, x, y, w, h):
      return (point[0]+x*w, h - point[1]-y*h)

    def draw_path(self, canvas, points, x, y, w, h, closed=False):
      if len(points) >= 2:
        path = canvas.beginPath()
        path.moveTo(*self.transform_position(points[0], x, y, w, h))

        for p in points[1:]:
            path.lineTo(*self.transform_position(p, x, y, w, h))
        if closed:
          path.close()
        canvas.drawPath(path, stroke=1, fill=0)