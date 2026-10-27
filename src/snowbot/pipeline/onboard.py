"""Render stage onboard packs from Jinja templates."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from snowbot.memory.layout import MemoryLayout


def _template_env() -> Environment:
    roles = resources.files("snowbot.templates.roles")
    # resources path may not be filesystem on all Python versions — extract root
    root = Path(str(roles))
    if not root.is_dir():
        pkg = Path(__file__).resolve().parent.parent / "templates" / "roles"
        root = pkg
    return Environment(
        loader=FileSystemLoader(str(root)),
        autoescape=select_autoescape(enabled_extensions=()),
    )


def render_onboard_pack(
    layout: MemoryLayout,
    *,
    stage: str,
    task: str | None = None,
    dry_run: bool = False,
) -> str:
    """Render role templates for a stage and write under ``.snowbot/memory/onboard/``."""
    layout.ensure_structure()
    env = _template_env()
    context = {
        "stage": stage,
        "task": task or "",
        "memory_dir": layout.memory_dir.as_posix(),
        "vision_path": layout.vision.as_posix(),
        "playbook_path": layout.playbook.as_posix(),
        "lessons_index": layout.lessons_index.as_posix(),
    }
    outputs: list[str] = []
    onboard_dir = layout.memory_dir / "onboard"
    if not dry_run:
        onboard_dir.mkdir(parents=True, exist_ok=True)

    role_templates = (
        "validator.md.j2",
        "pm.md.j2",
        "dev.md.j2",
        "reviewer.md.j2",
        "refiner.md.j2",
    )
    for name in role_templates:
        try:
            template = env.get_template(name)
        except Exception:
            continue
        rendered = template.render(**context)
        outputs.append(rendered)
        if not dry_run:
            dest = onboard_dir / name.replace(".md.j2", ".md")
            dest.write_text(rendered, encoding="utf-8")

    adapters_root = Path(__file__).resolve().parent.parent / "templates" / "adapters"
    adapter_env = Environment(
        loader=FileSystemLoader(str(adapters_root)),
        autoescape=select_autoescape(enabled_extensions=()),
    )
    for adapter_name in ("cursor_memory.md.j2", "local_memory.md.j2"):
        try:
            rendered = adapter_env.get_template(adapter_name).render(**context)
        except Exception:
            continue
        outputs.append(rendered)
        if not dry_run:
            dest = onboard_dir / adapter_name.replace(".md.j2", ".md")
            dest.write_text(rendered, encoding="utf-8")

    return "\n\n---\n\n".join(outputs)
