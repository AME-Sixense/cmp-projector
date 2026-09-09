import asyncio
import os
import re
import shutil
import yaml
from pathlib import Path

from textual.app import App, ComposeResult, RenderableType
from textual.widgets import Static, ListView, ListItem, RichLog
from textual.containers import Container, Center

from rich.progress import Progress, BarColumn

from core import __version__
from core.pipeline import EXPORTERS

CONFIG_FILE = Path(__file__).resolve().parent / "config.yaml"
pulse_color_1 = "#4a90e2"
pulse_color_2 = "#b7d1f8"


# ---------- config.yaml "outputs" editing (targeted text edit, comment-safe) ----------


def _find_project_block(text: str, project_name: str) -> tuple[int, int]:
    """Return the (start, end) character offsets of one project's YAML block,
    from its "- project: "<name>"" line up to just before the next "- project:"
    line (or end of file)."""
    start_pattern = re.compile(r'^(\s*)-\s*project:\s*"' + re.escape(project_name) + r'"\s*$', re.MULTILINE)
    m = start_pattern.search(text)
    if not m:
        raise ValueError(f"Could not find project '{project_name}' in config.yaml")

    next_pattern = re.compile(r'^\s*-\s*project:\s*"', re.MULTILINE)
    next_m = next_pattern.search(text, m.end())
    end = next_m.start() if next_m else len(text)
    return m.start(), end


def update_config_outputs(config_path: Path, project_name: str, outputs: list[str], make_backup: bool) -> None:
    """Rewrite just one project's "outputs: [...]" line in config.yaml, leaving
    every other line, comment, and formatting choice in the file untouched.

    make_backup controls whether the pre-write file is copied to
    config.yaml.bak first (overwriting any previous backup) — callers should
    only pass True once per session, on that session's first write; see
    ProjectSelectorApp._config_backed_up_this_session."""
    text = config_path.read_text(encoding="utf-8")
    start, end = _find_project_block(text, project_name)
    block = text[start:end]

    outputs_str = "[" + ", ".join(f'"{o}"' for o in outputs) + "]"

    new_block, n = re.subn(
        r'^(\s*outputs:\s*)\[[^\]]*\]',
        lambda m: m.group(1) + outputs_str,
        block,
        count=1,
        flags=re.MULTILINE,
    )
    if n == 0:
        # No existing "outputs:" line for this project — insert one right
        # after its "- project:" line, matching the file's existing convention.
        new_block, n = re.subn(
            r'(^\s*-\s*project:\s*"' + re.escape(project_name) + r'"\s*\n)',
            lambda m: m.group(1) + f"    outputs: {outputs_str}\n",
            block,
            count=1,
            flags=re.MULTILINE,
        )
        if n == 0:
            raise ValueError(f"Could not update outputs for project '{project_name}'")

    new_text = text[:start] + new_block + text[end:]

    if make_backup:
        backup_path = config_path.with_name(config_path.name + ".bak")
        shutil.copy2(config_path, backup_path)
    config_path.write_text(new_text, encoding="utf-8")


# ---------- Output-options list rows ----------


class OptionListItem(ListItem):
    """A row in the output-options ListView: either a toggleable choice (an
    exporter, or "save to config") or the final "Run" action. Reuses the same
    ListView/ListItem widgets (and styling) as the project list, so this
    screen navigates and looks the same way — arrow keys move the highlight,
    Enter activates the highlighted row."""

    def __init__(self, kind: str, label: str, *, key: str | None = None, checked: bool = False, **kwargs):
        self.kind = kind  # "exporter", "save", or "run"
        self.key = key  # exporter name, only set when kind == "exporter"
        self.checked = checked
        self._label_text = label
        self._static = Static(self._current_label(), markup=False)
        super().__init__(self._static, **kwargs)

    def _current_label(self) -> str:
        if self.kind == "run":
            return f"▶ {self._label_text}"
        mark = "[x]" if self.checked else "[ ]"
        return f"{mark} {self._label_text}"

    def toggle(self) -> None:
        if self.kind == "run":
            return
        self.checked = not self.checked
        self._static.update(self._current_label())


# ---------- Rich-based interval updater widgets (from the blog) ----------


class IntervalUpdater(Static):
    _renderable_object: RenderableType

    def update_rendering(self) -> None:
        self.update(self._renderable_object)

    def on_mount(self) -> None:
        # ~60 FPS refresh of the Rich renderable
        self.set_interval(1 / 60, self.update_rendering)


class IndeterminateProgressBar(IntervalUpdater):
    """Indeterminate progress bar widget based on rich.progress.Progress."""

    def __init__(self, color: str = pulse_color_2, **kwargs) -> None:
        super().__init__("", **kwargs)

        # BarColumn compatible with your Rich version
        bar_column = BarColumn(
            bar_width=None,         # use available width
            style=color,
            complete_style=color,
            finished_style=color,
            pulse_style=pulse_color_1
        )

        progress = Progress(bar_column, expand=True)
        progress.add_task("", total=None)  # total=None => indeterminate
        self._renderable_object = progress


# ---------- Main TUI app ----------


class ProjectSelectorApp(App):
    """A Textual TUI for selecting and running CMP projects."""

    CSS_PATH = "assets/style.css"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.projects: list[str] = []
        self.config: dict = {}
        self.pending_project: str | None = None
        self.current_screen = "project_list"  # "project_list", "output_options", or "console_output"
        self._running_task: asyncio.Task | None = None
        # Tracks whether config.yaml has been backed up yet this session (this
        # process's lifetime). Only the first save of a session takes a
        # backup; every save after that just overwrites config.yaml directly.
        self._config_backed_up_this_session = False

    # ---------- Config ----------

    def load_config(self) -> None:
        if not CONFIG_FILE.exists():
            self.exit("Config file not found!")
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            try:
                config = yaml.safe_load(f)
            except yaml.YAMLError as e:
                self.exit(f"Error parsing config file: {e}")
        self.config = config
        self.projects = [p["project"] for p in config.get("projects", [])]
        if not self.projects:
            self.exit("No projects found in the config file!")

    def get_project_config(self, project_name: str) -> dict:
        return next(p for p in self.config["projects"] if p["project"] == project_name)

    # ---------- Layout ----------

    def compose(self) -> ComposeResult:
        self.load_config()

        # HEADER (NOT scrollable)
        yield Static(f"CMP PROJECTOR v{__version__}", id="header")

        # TITLE
        yield Static("Select a Project:", id="title")

        # ===== PROJECT LIST VIEW =====
        with Center(id="project_center"):
            yield Container(
                ListView(
                    *[ListItem(Static(project)) for project in self.projects],
                    id="project_list",
                ),
                id="project_box",
            )

        # ===== OUTPUT OPTIONS VIEW =====
        with Center(id="options_center"):
            yield Container(
                ListView(id="options_list"),
                id="options_box",
            )

        # ===== CONSOLE VIEW =====
        with Center(id="console_center"):
            with Container(id="console_box"):
                # Scrollable console output
                yield RichLog(id="console_scroll", wrap=True, highlight=False, markup=False)
                # Rich pulsing bar
                yield IndeterminateProgressBar(color=pulse_color_2, id="progress_bar")

        # ===== FOOTER =====
        yield Static("^q to Quit", id="footer")

    # ---------- Lifecycle ----------

    def on_mount(self) -> None:
        self.load_config()

        # prevent whole screen from scrolling; keeps layout stable
        self.screen.can_scroll = False

        # Start on project list view
        self.query_one("#project_center").display = True
        self.query_one("#options_center").display = False
        self.query_one("#console_center").display = False

        # Hide bar initially
        self.query_one("#progress_bar").display = False

        footer = self.query_one("#footer", Static)
        footer.update("^q to Quit")

        def _focus_list() -> None:
            try:
                self.query_one("#project_list").focus()
            except Exception as e:
                self.console.log(f"Error focusing project_list: {e}")

        self.call_after_refresh(_focus_list)

    # ---------- View helpers ----------

    def show_project_view(self) -> None:
        """Show the project selection view."""
        self.current_screen = "project_list"

        self.query_one("#project_center").display = True
        self.query_one("#options_center").display = False
        self.query_one("#console_center").display = False
        self.query_one("#progress_bar").display = False  # hide bar

        footer = self.query_one("#footer", Static)
        footer.update("^q to Quit")

        title = self.query_one("#title", Static)
        title.update("Select a Project:")

        def _focus_list() -> None:
            try:
                self.query_one("#project_list").focus()
            except Exception as e:
                self.console.log(f"Error focusing project_list: {e}")

        self.call_after_refresh(_focus_list)

    async def show_output_options_view(self, project_name: str) -> None:
        """Show the per-run export-selection view for the chosen project."""
        self.current_screen = "output_options"
        self.pending_project = project_name

        self.query_one("#project_center").display = False
        self.query_one("#options_center").display = True
        self.query_one("#console_center").display = False

        footer = self.query_one("#footer", Static)
        footer.update("↑/↓ to navigate, Enter to toggle/run, Esc to go back")

        title = self.query_one("#title", Static)
        title.update(f"Select outputs for {project_name}:")

        current_outputs = self.get_project_config(project_name).get("outputs", ["kmz"])

        options_list = self.query_one("#options_list", ListView)
        await options_list.clear()
        items = [
            OptionListItem("exporter", name, key=name, checked=(name in current_outputs))
            for name in EXPORTERS
        ]
        items.append(OptionListItem("save", "Save to config.yaml"))
        items.append(OptionListItem("run", "Run"))
        await options_list.extend(items)
        options_list.index = 0

        def _focus_list() -> None:
            try:
                self.query_one("#options_list").focus()
            except Exception as e:
                self.console.log(f"Error focusing options_list: {e}")

        self.call_after_refresh(_focus_list)

    def show_console_view(self) -> None:
        """Show the console output view."""
        self.current_screen = "console_output"

        self.query_one("#project_center").display = False
        self.query_one("#options_center").display = False
        self.query_one("#console_center").display = True
        self.query_one("#progress_bar").display = True  # show bar

        footer = self.query_one("#footer", Static)
        footer.update("ENTER for main menu")

        title = self.query_one("#title", Static)
        title.update("Console Output:")

    # ---------- Async subprocess streaming ----------

    async def stream_project_output(self, selected_project: str, outputs: list[str]) -> None:
        """Run cli.py and stream its output into the console view."""

        console_log = self.query_one("#console_scroll", RichLog)
        console_log.clear()

        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"

        process = await asyncio.create_subprocess_exec(
            "python",
            "-u",
            "cli.py",
            selected_project,
            "--outputs",
            ",".join(outputs),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
            cwd=CONFIG_FILE.parent,
        )

        assert process.stdout is not None

        # Stream text as it arrives
        async for raw_line in process.stdout:
            line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
            console_log.write(line)
            await asyncio.sleep(0)

        await process.wait()

        # Process done: hide the bar
        self.query_one("#progress_bar").display = False

        self._running_task = None

    # ---------- Input handling ----------

    async def on_key(self, event) -> None:
        """Handle key presses."""

        # Ctrl+Q to quit
        if event.key == "q" and event.ctrl:
            self.exit()

        if self.current_screen == "project_list":
            if event.key == "enter":
                list_view = self.query_one("#project_list", ListView)
                selected_index = list_view.index
                if selected_index is None:
                    return

                selected_project = self.projects[selected_index]
                await self.show_output_options_view(selected_project)

        elif self.current_screen == "output_options":
            if event.key == "escape":
                self.show_project_view()

        elif self.current_screen == "console_output":
            if event.key == "enter":
                self.show_project_view()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle Enter/click on a row of the output-options list."""
        if event.list_view.id != "options_list":
            return  # not this screen's list (e.g. the project list)

        item = event.item
        if not isinstance(item, OptionListItem):
            return

        if item.kind == "run":
            self._start_run()
        else:
            item.toggle()

    def _start_run(self) -> None:
        if self.pending_project is None:
            return

        items = [
            child for child in self.query_one("#options_list", ListView).children
            if isinstance(child, OptionListItem)
        ]
        selected_outputs = [item.key for item in items if item.kind == "exporter" and item.checked]
        save_to_config = any(item.kind == "save" and item.checked for item in items)

        if save_to_config:
            update_config_outputs(
                CONFIG_FILE,
                self.pending_project,
                selected_outputs,
                make_backup=not self._config_backed_up_this_session,
            )
            self._config_backed_up_this_session = True

        project_to_run = self.pending_project

        self.show_console_view()

        if self._running_task is not None and not self._running_task.done():
            self._running_task.cancel()

        self._running_task = asyncio.create_task(
            self.stream_project_output(project_to_run, selected_outputs)
        )


if __name__ == "__main__":
    app = ProjectSelectorApp()
    app.run()
