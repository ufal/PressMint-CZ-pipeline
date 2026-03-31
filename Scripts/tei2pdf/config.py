import yaml
import copy

def build_templates(templates_raw):
    resolved = {}

    for name, tpl in templates_raw.items():
        tpl = copy.deepcopy(tpl)

        if "template" in tpl:
            parent_name = tpl["template"]

            if parent_name not in resolved:
              raise ValueError(
                f"Template '{name}' must reference a previously defined template "
                f"(got '{parent_name}')"
              )
            parent = resolved[parent_name]
            tpl = {**parent, **tpl}
            del tpl["template"]

        resolved[name] = tpl

    return resolved


def load_config(path, profile_override=None):
    with open(path) as f:
        raw = yaml.safe_load(f)
    profile_name = get_active_profile_name(raw, profile_override)
    templates = build_templates(raw["templates"])
    profile = raw["profiles"][profile_name]

    tasks = []

    for task in profile["tasks"]:
        if "template" in task:
            base = templates[task["template"]]
            override = {k: v for k, v in task.items() if k != "template"}
            merged = {**base, **override}
        else:
            merged = task.copy()

        tasks.append(merged)

    return tasks, raw.get("styles",{})

def get_active_profile_name(config, profile_override=None):
    if profile_override:
        return profile_override

    if "active_profile" in config:
        return config["active_profile"]

    raise ValueError(
        "No profile specified. Use --profile or define active_profile in YAML."
    )

