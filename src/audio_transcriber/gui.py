# gui.py
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from pathlib import Path

from dotenv import load_dotenv, set_key

from audio_transcriber.config import (
    API_URL, MODEL, CHUNK_MINUTES, DELAY_SECONDS, MAX_RETRIES
)
from audio_transcriber.transcriber import SmartTranscriber

ENV_PATH = ".env"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("🎙️ Audio Transcriber — Avalai")
        self.geometry("720x640")
        self.resizable(True, True)
        self.configure(padx=16, pady=16)

        self.selected_file: str | None = None
        self._build_ui()
        self._load_token()

    # ──────────────────────────────────────────
    def _build_ui(self):

        # ─── توکن ───────────────────────────
        token_frame = ttk.LabelFrame(self, text="🔑  توکن API")
        token_frame.pack(fill="x", pady=(0, 10))

        self.token_var = tk.StringVar()
        self.token_entry = ttk.Entry(
            token_frame, textvariable=self.token_var,
            show="•", width=55
        )
        self.token_entry.pack(
            side="left", padx=(8, 4), pady=8, fill="x", expand=True
        )

        self.show_var = tk.BooleanVar()
        ttk.Checkbutton(
            token_frame, text="نمایش",
            variable=self.show_var, command=self._toggle_show
        ).pack(side="left", padx=4)

        ttk.Button(
            token_frame, text="💾 ذخیره در .env",
            command=self._save_token
        ).pack(side="left", padx=(4, 8))

        # ─── انتخاب فایل ────────────────────
        file_frame = ttk.LabelFrame(self, text="🎵  فایل صوتی")
        file_frame.pack(fill="x", pady=(0, 10))

        self.file_label = ttk.Label(
            file_frame, text="فایلی انتخاب نشده", foreground="gray"
        )
        self.file_label.pack(
            side="left", padx=(8, 4), pady=8, fill="x", expand=True
        )

        ttk.Button(
            file_frame, text="📂 انتخاب فایل",
            command=self._pick_file
        ).pack(side="left", padx=(4, 8))

        # ─── دکمه شروع ──────────────────────
        self.start_btn = ttk.Button(
            self, text="▶️   شروع تبدیل صوت به متن",
            command=self._start
        )
        self.start_btn.pack(fill="x", ipady=6, pady=(0, 8))

        # ─── پیشرفت ──────────────────────────
        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 4))

        self.status_var = tk.StringVar(value="آماده")
        ttk.Label(
            self, textvariable=self.status_var, anchor="w"
        ).pack(fill="x", pady=(0, 6))

        # ─── خروجی ───────────────────────────
        out_frame = ttk.LabelFrame(self, text="📝  متن خروجی")
        out_frame.pack(fill="both", expand=True)

        self.output = scrolledtext.ScrolledText(
            out_frame, wrap="word",
            font=("Tahoma", 11), relief="flat"
        )
        self.output.pack(fill="both", expand=True, padx=6, pady=6)
        self.output.tag_configure("rtl", justify="right")

        # ─── دکمه‌های پایین ──────────────────
        btn_row = ttk.Frame(self)
        btn_row.pack(fill="x", pady=(8, 0))

        ttk.Button(btn_row, text="📋 کپی",
                   command=self._copy).pack(side="left", padx=2)
        ttk.Button(btn_row, text="💾 ذخیره .txt",
                   command=self._save_txt).pack(side="left", padx=2)
        ttk.Button(btn_row, text="🗑️ پاک کردن",
                   command=self._clear).pack(side="left", padx=2)

    # ──────────────────────────────────────────
    def _load_token(self):
        """توکن ذخیره‌شده را از .env می‌خواند."""
        if os.path.exists(ENV_PATH):
            load_dotenv(ENV_PATH, override=True)
            token = os.getenv("API_KEY", "")
            if token:
                self.token_var.set(token)

    def _save_token(self):
        token = self.token_var.get().strip()
        if not token:
            messagebox.showwarning("خطا", "توکن خالی است!")
            return
        Path(ENV_PATH).touch(exist_ok=True)
        set_key(ENV_PATH, "API_KEY", token)
        self.status_var.set("توکن ذخیره شد ✅")

    def _toggle_show(self):
        self.token_entry.config(
            show="" if self.show_var.get() else "•"
        )

    def _pick_file(self):
        path = filedialog.askopenfilename(
            title="انتخاب فایل صوتی",
            filetypes=[
                ("Audio files", "*.mp3 *.wav *.m4a *.ogg *.flac"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.selected_file = path
            self.file_label.config(
                text=Path(path).name, foreground="black"
            )

    # ──────────────────────────────────────────
    def _start(self):
        token = self.token_var.get().strip()
        if not token:
            messagebox.showwarning("خطا", "ابتدا توکن را وارد کنید!")
            return
        if not self.selected_file:
            messagebox.showwarning("خطا", "ابتدا یک فایل انتخاب کنید!")
            return

        self.start_btn.config(state="disabled")
        self.progress.start(10)
        self.status_var.set("در حال پردازش... ⏳")
        self.output.delete("1.0", "end")

        threading.Thread(
            target=self._worker, args=(token,), daemon=True
        ).start()

    def _worker(self, token: str):
        def on_progress(current, total, message):
            self.after(0, self.status_var.set, message)

        try:
            transcriber = SmartTranscriber(
                api_key          = token,
                url              = API_URL,
                model            = MODEL,
                chunk_minutes    = CHUNK_MINUTES,
                delay            = DELAY_SECONDS,
                max_retries      = MAX_RETRIES,
                progress_callback= on_progress,
            )
            text = transcriber.transcribe(self.selected_file)
            self.after(0, self._on_success, text)

        except Exception as e:
            self.after(0, self._on_error, str(e))

    def _on_success(self, text: str):
        self.progress.stop()
        self.start_btn.config(state="normal")
        self.status_var.set("تمام شد ✅")
        self.output.insert("1.0", text, "rtl")

    def _on_error(self, err: str):
        self.progress.stop()
        self.start_btn.config(state="normal")
        self.status_var.set("خطا ❌")
        messagebox.showerror("خطا", err)

    # ──────────────────────────────────────────
    def _copy(self):
        text = self.output.get("1.0", "end").strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.status_var.set("در کلیپ‌بورد کپی شد 📋")

    def _save_txt(self):
        text = self.output.get("1.0", "end").strip()
        if not text:
            messagebox.showinfo("خالی", "متنی برای ذخیره وجود ندارد.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text file", "*.txt")],
        )
        if path:
            Path(path).write_text(text, encoding="utf-8")
            self.status_var.set(f"ذخیره شد: {Path(path).name} 💾")

    def _clear(self):
        self.output.delete("1.0", "end")
        self.status_var.set("پاک شد")


# ══════════════════════════════════════════════
def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()