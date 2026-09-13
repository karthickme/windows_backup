"""CustomTkinter desktop UI: Sources, Destination, Schedule, Activity."""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk

from folderbackup.cloud.factory import create_backend
from folderbackup.config.secrets import Secrets, credentials_present, load_secrets, save_secrets
from folderbackup.config.settings import (
    AppSettings,
    load_settings,
    save_settings,
    validate_settings,
)
from folderbackup.core.catalog import Catalog
from folderbackup.core.logging_setup import setup_logging
from folderbackup.core.runner import run_from_disk
from folderbackup.paths import catalog_path, config_path, ensure_app_dirs
from folderbackup.schedule.aps import AppScheduler
from folderbackup.schedule import win_task

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


def _exts_to_text(values: list[str]) -> str:
    return ",".join(values)


def _parse_mb(text: str) -> float | None:
    text = text.strip()
    if not text:
        return None
    return float(text)


class FolderBackupApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ensure_app_dirs()
        setup_logging(also_console=False)
        self.title("Folder Backup")
        self.geometry("920x680")
        self.minsize(820, 600)

        self.settings = load_settings()
        self.secrets = load_secrets()
        self._backup_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._scheduler = AppScheduler(self._scheduled_run)
        self._tray_icon = None
        self._closing = False

        self._build()
        self._load_into_form()
        self._refresh_activity()
        self._apply_schedule()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(400, self._start_tray)

    def _build(self) -> None:
        header = ctk.CTkFrame(self)
        header.pack(fill="x", padx=12, pady=(12, 0))
        ctk.CTkLabel(header, text="Folder Backup", font=ctk.CTkFont(size=20, weight="bold")).pack(
            side="left", padx=8, pady=8
        )
        self.status_label = ctk.CTkLabel(header, text="Idle")
        self.status_label.pack(side="right", padx=8)

        btns = ctk.CTkFrame(self)
        btns.pack(fill="x", padx=12, pady=8)
        ctk.CTkButton(btns, text="Save settings", command=self._save).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="Backup now", command=lambda: self._start_backup(False)).pack(
            side="left", padx=4
        )
        ctk.CTkButton(btns, text="Dry run", command=lambda: self._start_backup(True)).pack(
            side="left", padx=4
        )
        self.cancel_btn = ctk.CTkButton(btns, text="Cancel", command=self._cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=4)

        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.tabs.add("Sources")
        self.tabs.add("Destination")
        self.tabs.add("Schedule")
        self.tabs.add("Activity")
        self._build_sources()
        self._build_destination()
        self._build_schedule()
        self._build_activity()

    def _build_sources(self) -> None:
        tab = self.tabs.tab("Sources")
        ctk.CTkLabel(tab, text="Folders to back up").pack(anchor="w", padx=8, pady=(8, 4))
        self.folder_list = ctk.CTkTextbox(tab, height=140)
        self.folder_list.pack(fill="x", padx=8)

        row = ctk.CTkFrame(tab)
        row.pack(fill="x", padx=8, pady=6)
        ctk.CTkButton(row, text="Add folder", command=self._add_folder).pack(side="left", padx=4)
        ctk.CTkButton(row, text="Remove last", command=self._remove_last_folder).pack(side="left", padx=4)

        grid = ctk.CTkFrame(tab)
        grid.pack(fill="x", padx=8, pady=8)
        ctk.CTkLabel(grid, text="Include extensions (empty = all)").grid(row=0, column=0, sticky="w", pady=4)
        self.include_ext = ctk.CTkEntry(grid, placeholder_text=".docx,.pdf,.jpg")
        self.include_ext.grid(row=0, column=1, sticky="ew", padx=8, pady=4)
        ctk.CTkLabel(grid, text="Exclude extensions (wins)").grid(row=1, column=0, sticky="w", pady=4)
        self.exclude_ext = ctk.CTkEntry(grid, placeholder_text=".tmp,.iso,.exe")
        self.exclude_ext.grid(row=1, column=1, sticky="ew", padx=8, pady=4)
        ctk.CTkLabel(grid, text="Min size (MB)").grid(row=2, column=0, sticky="w", pady=4)
        self.min_size = ctk.CTkEntry(grid, placeholder_text="blank = none")
        self.min_size.grid(row=2, column=1, sticky="ew", padx=8, pady=4)
        ctk.CTkLabel(grid, text="Max size (MB)").grid(row=3, column=0, sticky="w", pady=4)
        self.max_size = ctk.CTkEntry(grid, placeholder_text="blank = none")
        self.max_size.grid(row=3, column=1, sticky="ew", padx=8, pady=4)
        grid.columnconfigure(1, weight=1)

        flags = ctk.CTkFrame(tab)
        flags.pack(fill="x", padx=8, pady=8)
        self.skip_hidden = ctk.CTkCheckBox(flags, text="Skip hidden files")
        self.skip_hidden.pack(anchor="w", pady=2)
        self.skip_system = ctk.CTkCheckBox(flags, text="Skip system files")
        self.skip_system.pack(anchor="w", pady=2)
        self.skip_online = ctk.CTkCheckBox(flags, text="Skip OneDrive online-only placeholders")
        self.skip_online.pack(anchor="w", pady=2)
        self.follow_junc = ctk.CTkCheckBox(flags, text="Follow directory junctions / reparse points")
        self.follow_junc.pack(anchor="w", pady=2)
        self.builtin_ex = ctk.CTkCheckBox(flags, text="Skip .git, node_modules, __pycache__, .venv, $Recycle.Bin")
        self.builtin_ex.pack(anchor="w", pady=2)
        self.workers = ctk.CTkEntry(flags, placeholder_text="4")
        ctk.CTkLabel(flags, text="Upload workers").pack(anchor="w", pady=(8, 0))
        self.workers.pack(anchor="w")

    def _build_destination(self) -> None:
        tab = self.tabs.tab("Destination")
        ctk.CTkLabel(tab, text="Exactly one cloud destination is active.").pack(anchor="w", padx=8, pady=8)
        self.provider = tk.StringVar(value="s3")
        radios = ctk.CTkFrame(tab)
        radios.pack(fill="x", padx=8)
        for label, value in (("Amazon S3", "s3"), ("Google Cloud Storage", "gcs"), ("Azure Blob", "azure")):
            ctk.CTkRadioButton(
                radios, text=label, variable=self.provider, value=value, command=self._toggle_provider_fields
            ).pack(side="left", padx=8, pady=6)

        grid = ctk.CTkFrame(tab)
        grid.pack(fill="x", padx=8, pady=8)
        self._dest_entries: dict[str, ctk.CTkEntry] = {}

        def add(key: str, label: str, row: int, show: str = "") -> None:
            ctk.CTkLabel(grid, text=label).grid(row=row, column=0, sticky="w", pady=4)
            entry = ctk.CTkEntry(grid, show=show, width=420)
            entry.grid(row=row, column=1, sticky="ew", padx=8, pady=4)
            self._dest_entries[key] = entry

        add("bucket", "Bucket / container", 0)
        add("prefix", "Object prefix", 1)
        add("region", "Region (S3)", 2)
        add("endpoint", "S3 endpoint (optional compatible)", 3)
        add("aws_profile", "AWS profile name (optional)", 4)
        add("s3_key", "S3 access key ID", 5)
        add("s3_secret", "S3 secret access key", 6, show="*")
        add("gcs_path", "GCS service-account JSON path", 7)
        add("azure_account", "Azure storage account name", 8)
        add("azure_key", "Azure account key", 9, show="*")
        add("azure_conn", "Azure connection string", 10, show="*")
        grid.columnconfigure(1, weight=1)

        ctk.CTkButton(tab, text="Test connection", command=self._test_connection).pack(anchor="w", padx=8, pady=8)
        self.test_result = ctk.CTkLabel(tab, text="", wraplength=780, justify="left")
        self.test_result.pack(anchor="w", padx=8)
        note = (
            "Secrets are stored in Windows Credential Manager, not in config.yaml. "
            "Deletes on this PC are never mirrored to the cloud."
        )
        ctk.CTkLabel(tab, text=note, wraplength=780, justify="left").pack(anchor="w", padx=8, pady=12)

    def _build_schedule(self) -> None:
        tab = self.tabs.tab("Schedule")
        self.sched_enabled = ctk.CTkCheckBox(tab, text="Enable in-app schedule (while this window/tray is running)")
        self.sched_enabled.pack(anchor="w", padx=8, pady=8)
        self.interval = ctk.CTkOptionMenu(tab, values=["hourly", "daily", "weekly"])
        ctk.CTkLabel(tab, text="Interval").pack(anchor="w", padx=8)
        self.interval.pack(anchor="w", padx=8, pady=4)
        ctk.CTkLabel(tab, text="Clock time (daily/weekly, HH:MM)").pack(anchor="w", padx=8)
        self.sched_time = ctk.CTkEntry(tab, placeholder_text="02:00")
        self.sched_time.pack(anchor="w", padx=8, pady=4)
        ctk.CTkLabel(tab, text="Weekday (weekly)").pack(anchor="w", padx=8)
        self.weekday = ctk.CTkOptionMenu(tab, values=["mon", "tue", "wed", "thu", "fri", "sat", "sun"])
        self.weekday.pack(anchor="w", padx=8, pady=4)
        self.run_on_logon = ctk.CTkCheckBox(tab, text="Also run at Windows logon (scheduled task)")
        self.run_on_logon.pack(anchor="w", padx=8, pady=8)

        row = ctk.CTkFrame(tab)
        row.pack(fill="x", padx=8, pady=8)
        ctk.CTkButton(row, text="Register Windows Task", command=self._register_task).pack(side="left", padx=4)
        ctk.CTkButton(row, text="Unregister Windows Task", command=self._unregister_task).pack(side="left", padx=4)
        self.next_run_label = ctk.CTkLabel(tab, text="Next in-app run: —")
        self.next_run_label.pack(anchor="w", padx=8, pady=8)
        self.task_label = ctk.CTkLabel(tab, text="", wraplength=780, justify="left")
        self.task_label.pack(anchor="w", padx=8)
        self._refresh_task_status()

    def _build_activity(self) -> None:
        tab = self.tabs.tab("Activity")
        self.progress = ctk.CTkProgressBar(tab)
        self.progress.pack(fill="x", padx=8, pady=8)
        self.progress.set(0)
        self.progress_label = ctk.CTkLabel(tab, text="No run in progress")
        self.progress_label.pack(anchor="w", padx=8)
        self.log_box = ctk.CTkTextbox(tab, height=280)
        self.log_box.pack(fill="both", expand=True, padx=8, pady=8)
        self.runs_box = ctk.CTkTextbox(tab, height=120)
        self.runs_box.pack(fill="x", padx=8, pady=(0, 8))
        ctk.CTkLabel(
            tab,
            text=f"Config: {config_path()}",
            wraplength=780,
            justify="left",
        ).pack(anchor="w", padx=8, pady=(0, 8))

    def _toggle_provider_fields(self) -> None:
        prov = self.provider.get()
        groups = {
            "s3": {"region", "endpoint", "aws_profile", "s3_key", "s3_secret"},
            "gcs": {"gcs_path"},
            "azure": {"azure_account", "azure_key", "azure_conn"},
        }
        always = {"bucket", "prefix"}
        for key, entry in self._dest_entries.items():
            if key in always or key in groups.get(prov, ()):
                entry.configure(state="normal")
            else:
                entry.configure(state="disabled")

    def _folder_lines(self) -> list[str]:
        text = self.folder_list.get("1.0", "end").strip()
        return [ln.strip() for ln in text.splitlines() if ln.strip()]

    def _add_folder(self) -> None:
        chosen = filedialog.askdirectory(title="Choose a folder to back up")
        if not chosen:
            return
        current = self._folder_lines()
        if chosen not in current:
            current.append(chosen)
        self.folder_list.delete("1.0", "end")
        self.folder_list.insert("1.0", "\n".join(current))

    def _remove_last_folder(self) -> None:
        current = self._folder_lines()
        if current:
            current.pop()
        self.folder_list.delete("1.0", "end")
        self.folder_list.insert("1.0", "\n".join(current))

    def _load_into_form(self) -> None:
        s = self.settings
        self.folder_list.delete("1.0", "end")
        self.folder_list.insert("1.0", "\n".join(s.folders))
        self.include_ext.delete(0, "end")
        self.include_ext.insert(0, _exts_to_text(s.filters.include_extensions))
        self.exclude_ext.delete(0, "end")
        self.exclude_ext.insert(0, _exts_to_text(s.filters.exclude_extensions))
        if s.filters.min_size_mb is not None:
            self.min_size.delete(0, "end")
            self.min_size.insert(0, str(s.filters.min_size_mb))
        if s.filters.max_size_mb is not None:
            self.max_size.delete(0, "end")
            self.max_size.insert(0, str(s.filters.max_size_mb))
        self._set_check(self.skip_hidden, s.filters.skip_hidden)
        self._set_check(self.skip_system, s.filters.skip_system)
        self._set_check(self.skip_online, s.filters.skip_online_only)
        self._set_check(self.follow_junc, s.filters.follow_junctions)
        self._set_check(self.builtin_ex, s.filters.use_builtin_excludes)
        self.workers.delete(0, "end")
        self.workers.insert(0, str(s.engine.workers))

        c = s.cloud
        self.provider.set(c.provider)
        mapping = {
            "bucket": c.bucket,
            "prefix": c.prefix,
            "region": c.region,
            "endpoint": c.endpoint,
            "aws_profile": c.aws_profile,
            "gcs_path": c.gcs_credentials_path,
            "azure_account": c.azure_account_name,
            "s3_key": self.secrets.s3_access_key_id,
            "s3_secret": self.secrets.s3_secret_access_key,
            "azure_key": self.secrets.azure_account_key,
            "azure_conn": self.secrets.azure_connection_string,
        }
        for key, value in mapping.items():
            self._dest_entries[key].delete(0, "end")
            self._dest_entries[key].insert(0, value or "")
        self._toggle_provider_fields()

        self._set_check(self.sched_enabled, s.schedule.enabled)
        self.interval.set(s.schedule.interval)
        self.sched_time.delete(0, "end")
        self.sched_time.insert(0, s.schedule.time)
        self.weekday.set(s.schedule.weekday)
        self._set_check(self.run_on_logon, s.schedule.run_on_logon)

    def _set_check(self, widget: ctk.CTkCheckBox, value: bool) -> None:
        if value:
            widget.select()
        else:
            widget.deselect()

    def _collect(self) -> tuple[AppSettings, Secrets] | None:
        try:
            min_mb = _parse_mb(self.min_size.get())
            max_mb = _parse_mb(self.max_size.get())
            workers = int(self.workers.get().strip() or "4")
        except ValueError:
            messagebox.showerror("Invalid input", "Size and workers must be numeric.")
            return None
        from folderbackup.config.settings import CloudSettings, EngineSettings, FilterSettings, ScheduleSettings
        from folderbackup.core.filters import parse_ext_list

        settings = AppSettings(
            folders=self._folder_lines(),
            filters=FilterSettings(
                include_extensions=parse_ext_list(self.include_ext.get()),
                exclude_extensions=parse_ext_list(self.exclude_ext.get()),
                min_size_mb=min_mb,
                max_size_mb=max_mb,
                skip_hidden=bool(self.skip_hidden.get()),
                skip_system=bool(self.skip_system.get()),
                skip_online_only=bool(self.skip_online.get()),
                follow_junctions=bool(self.follow_junc.get()),
                use_builtin_excludes=bool(self.builtin_ex.get()),
            ),
            cloud=CloudSettings(
                provider=self.provider.get(),
                bucket=self._dest_entries["bucket"].get().strip(),
                prefix=self._dest_entries["prefix"].get().strip(),
                region=self._dest_entries["region"].get().strip(),
                endpoint=self._dest_entries["endpoint"].get().strip(),
                aws_profile=self._dest_entries["aws_profile"].get().strip(),
                gcs_credentials_path=self._dest_entries["gcs_path"].get().strip(),
                azure_account_name=self._dest_entries["azure_account"].get().strip(),
            ),
            schedule=ScheduleSettings(
                enabled=bool(self.sched_enabled.get()),
                interval=self.interval.get(),
                time=self.sched_time.get().strip() or "02:00",
                weekday=self.weekday.get(),
                run_on_logon=bool(self.run_on_logon.get()),
            ),
            engine=EngineSettings(workers=workers),
        )
        secrets = Secrets(
            s3_access_key_id=self._dest_entries["s3_key"].get().strip(),
            s3_secret_access_key=self._dest_entries["s3_secret"].get().strip(),
            azure_connection_string=self._dest_entries["azure_conn"].get().strip(),
            azure_account_key=self._dest_entries["azure_key"].get().strip(),
        )
        return settings, secrets

    def _save(self) -> bool:
        collected = self._collect()
        if not collected:
            return False
        settings, secrets = collected
        errors = validate_settings(settings, require_cloud=True)
        if not credentials_present(
            settings.cloud.provider,
            secrets,
            aws_profile=settings.cloud.aws_profile,
            gcs_path=settings.cloud.gcs_credentials_path,
            azure_account=settings.cloud.azure_account_name,
        ) and settings.cloud.provider != "gcs":
            errors.append("Cloud credentials are missing for the selected provider.")
        if settings.cloud.provider == "azure":
            if not secrets.azure_connection_string and not (
                settings.cloud.azure_account_name and secrets.azure_account_key
            ):
                errors.append("Azure needs a connection string or account name + key.")
        if errors:
            messagebox.showerror("Cannot save", "\n".join(errors))
            return False
        save_settings(settings)
        save_secrets(secrets)
        self.settings = settings
        self.secrets = secrets
        self._apply_schedule()
        self.status_label.configure(text="Settings saved")
        self._append_log("Settings saved (secrets in Credential Manager).")
        return True

    def _apply_schedule(self) -> None:
        nxt = self._scheduler.apply(self.settings.schedule)
        if nxt:
            self.next_run_label.configure(text=f"Next in-app run: {nxt}")
        else:
            self.next_run_label.configure(text="Next in-app run: —")

    def _scheduled_run(self) -> None:
        self.after(0, lambda: self._start_backup(False, from_schedule=True))

    def _start_backup(self, dry_run: bool, from_schedule: bool = False) -> None:
        if self._backup_thread and self._backup_thread.is_alive():
            if not from_schedule:
                messagebox.showinfo("Busy", "A backup is already running.")
            return
        if not from_schedule:
            if not self._save():
                return
        self._stop.clear()
        self.cancel_btn.configure(state="normal")
        self.progress.set(0.05)
        self.status_label.configure(text="Running…" if not dry_run else "Dry run…")
        self.progress_label.configure(text="Backup in progress")
        self.tabs.set("Activity")

        def work() -> None:
            result = run_from_disk(
                dry_run=dry_run,
                settings=self.settings,
                secrets=self.secrets,
                progress=lambda msg: self.after(0, lambda m=msg: self._append_log(m)),
                stop_event=self._stop,
            )
            self.after(0, lambda: self._backup_done(result))

        self._backup_thread = threading.Thread(target=work, daemon=True)
        self._backup_thread.start()

    def _cancel(self) -> None:
        self._stop.set()
        self._append_log("Cancel requested…")

    def _backup_done(self, result: Any) -> None:
        self.cancel_btn.configure(state="disabled")
        self.progress.set(1)
        self.status_label.configure(text=f"Last run: {result.status}")
        self.progress_label.configure(
            text=(
                f"{result.status}: uploaded {result.files_uploaded}, "
                f"skipped {result.files_skipped}, failed {result.files_failed}, "
                f"{result.bytes_uploaded} bytes"
            )
        )
        if result.error:
            self._append_log(f"Error: {result.error}")
        self._refresh_activity()

    def _test_connection(self) -> None:
        collected = self._collect()
        if not collected:
            return
        settings, secrets = collected
        if not settings.cloud.bucket:
            messagebox.showerror("Missing bucket", "Enter a bucket or container name.")
            return

        def work() -> None:
            try:
                backend = create_backend(settings, secrets)
                result = backend.test_connection()
                self.after(0, lambda: self.test_result.configure(text=result.message))
            except Exception as exc:
                self.after(0, lambda: self.test_result.configure(text=str(exc)))

        threading.Thread(target=work, daemon=True).start()
        self.test_result.configure(text="Testing…")

    def _register_task(self) -> None:
        if not self._save():
            return
        msg = win_task.register(
            interval=self.settings.schedule.interval,
            time=self.settings.schedule.time,
            weekday=self.settings.schedule.weekday,
            run_on_logon=self.settings.schedule.run_on_logon,
        )
        self.task_label.configure(text=msg)
        self._refresh_task_status()

    def _unregister_task(self) -> None:
        msg = win_task.unregister()
        self.task_label.configure(text=msg)
        self._refresh_task_status()

    def _refresh_task_status(self) -> None:
        status = win_task.get_status()
        self.task_label.configure(
            text=(
                f"Windows task registered: {status.registered}; "
                f"logon task: {status.logon_registered}. {status.detail}"
            )
        )

    def _append_log(self, message: str) -> None:
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")

    def _refresh_activity(self) -> None:
        cat = Catalog(catalog_path())
        try:
            runs = cat.latest_runs(12)
        finally:
            cat.close()
        self.runs_box.delete("1.0", "end")
        if not runs:
            self.runs_box.insert("1.0", "No runs yet.")
            return
        lines = []
        for run in runs:
            lines.append(
                f"#{run.id} {run.status} scanned={run.files_scanned} "
                f"uploaded={run.files_uploaded} skipped={run.files_skipped} "
                f"failed={run.files_failed} bytes={run.bytes_uploaded} "
                f"{'dry-run ' if run.dry_run else ''}{run.started_at}"
            )
        self.runs_box.insert("1.0", "\n".join(lines))

    def _start_tray(self) -> None:
        try:
            import pystray
            from PIL import Image, ImageDraw
        except Exception:
            return

        image = Image.new("RGB", (64, 64), "#1f6aa5")
        draw = ImageDraw.Draw(image)
        draw.rectangle((12, 20, 52, 48), fill="white")

        def show(_icon=None, _item=None) -> None:
            self.after(0, self._restore)

        def backup_now(_icon=None, _item=None) -> None:
            self.after(0, lambda: self._start_backup(False))

        def quit_app(_icon=None, _item=None) -> None:
            self.after(0, self._quit_fully)

        menu = pystray.Menu(
            pystray.MenuItem("Open", show, default=True),
            pystray.MenuItem("Backup now", backup_now),
            pystray.MenuItem("Quit", quit_app),
        )
        icon = pystray.Icon("FolderBackup", image, "Folder Backup", menu)
        self._tray_icon = icon
        threading.Thread(target=icon.run, daemon=True).start()

    def _restore(self) -> None:
        self.deiconify()
        self.after(50, self.lift)

    def _on_close(self) -> None:
        if self._tray_icon is not None and not self._closing:
            self.withdraw()
            self.status_label.configure(text="Running in tray")
            return
        self._quit_fully()

    def _quit_fully(self) -> None:
        self._closing = True
        self._stop.set()
        try:
            self._scheduler.shutdown()
        except Exception:
            pass
        if self._tray_icon is not None:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
        self.destroy()


def launch() -> None:
    if sys.platform == "win32":
        try:
            from ctypes import windll

            windll.kernel32.SetDllDirectoryW(None)
        except Exception:
            pass
    app = FolderBackupApp()
    app.mainloop()
