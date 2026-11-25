"""Window for dwg_kat_pdf: pick one or more DWGs, Run, read the warnings. Start with pythonw (no console)."""
import os, sys, threading, tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

sys.path.insert(0, str(Path(__file__).parent))
import dwg_kat_pdf

if sys.argv[1:2] == ["--check"]:  # --check <drawing> <folder>: prove a built .exe works, without the window; result in check.txt
    out = Path(sys.argv[3])
    dwg_kat_pdf.OUT_DIR, dwg_kat_pdf.PORT_DIR = out / "pdf", out / "port pdf"
    try:
        dwg_kat_pdf._selftest()
        ports = dwg_kat_pdf.run(sys.argv[2])[3]
        dwg_kat_pdf.port_docx([ports], out / "Port Raporu.docx")
        (out / "check.txt").write_text("ok\n" + "\n".join(ports["lines"]), encoding="utf-8")
    except BaseException:
        import traceback
        (out / "check.txt").write_text(traceback.format_exc(), encoding="utf-8")
    sys.exit()

root = tk.Tk()
root.title("DWG → Kat PDF")
root.geometry("820x500")
SEP = " | "  # can't appear in a Windows path
path = tk.StringVar(value=SEP.join(sys.argv[1:]))  # DWGs dropped on the icon
progress, done = [], []  # filled by the worker thread, read on the Tk thread


def files():
    return [Path(s.strip().strip('"')) for s in path.get().split(SEP) if s.strip()]


def browse():
    ps = filedialog.askopenfilenames(title="Pick the drawings", filetypes=[("Drawings", "*.dwg *.dxf"), ("All files", "*.*")])
    if ps:
        path.set(SEP.join(ps))


def browse_folder():
    d = filedialog.askdirectory(title="Pick a folder of drawings")
    if d:  # subfolders too
        ps = sorted(str(p) for p in Path(d).rglob("*") if p.suffix.lower() in (".dwg", ".dxf") and p.is_file())
        # added to what is already picked: the Windows folder dialog takes one folder at a time
        path.set(SEP.join(dict.fromkeys([str(f) for f in files()] + ps)))
        if not ps:
            show([f"No .dwg / .dxf files in {d}"])


def port_report():
    ps = filedialog.askopenfilenames(title="Pick the drawings (or PDFs plotted from AutoCAD)",
                                     filetypes=[("Drawings, plotted PDFs", "*.dwg *.dxf *.pdf"), ("All files", "*.*")])
    if ps:
        start([Path(p) for p in ps], ports_only=True)


def show(lines):
    log.config(state="normal")
    log.delete("1.0", "end")
    for line in lines:
        log.insert("end", line + "\n", "warn" if line.startswith("UYARI") else "")
    log.config(state="disabled")


def start(fs=None, ports_only=False):  # Run: the picked drawings; Port report…: its own files, only the port report
    fs = fs or files()
    missing = [f.name for f in fs if not f.is_file()]
    if not fs or missing:
        show(["Pick one or more .dwg / .dxf files first."] + [f"Not found: {m}" for m in missing])
        return
    for b in (run_btn, port_btn):  # one job at a time: both write to the same log and Word report
        b.config(state="disabled")
    progress.clear()
    done.clear()

    def work():
        reports = []
        for i, f in enumerate(fs, 1):
            progress.append(f"[{i}/{len(fs)}] {f.name}")
            try:
                if ports_only:
                    ports = dwg_kat_pdf.ports_of(f)
                    progress.append(f"Saved: {dwg_kat_pdf.PORT_DIR / (ports['name'] + ' - port raporu.txt')}")
                else:
                    names, lines, folder, ports = dwg_kat_pdf.run(f)
                    progress.extend([f"Folder: {folder}"] + ["   " + n for n in names]
                                    + (lines or ["Every room has a data outlet."]))
                if ports:
                    reports.append(ports)
                    progress.extend(["Port raporu:"] + ports["lines"])
            except Exception as e:
                progress.append(f"Error: {e}")
            progress.append("")
        if reports:
            word = dwg_kat_pdf.PORT_DIR / "Port Raporu.docx"
            try:
                dwg_kat_pdf.port_docx(reports, word)
                progress.append(f"Word report: {word}")
            except Exception as e:  # most often: the file is open in Word
                progress.append(f"Error: Word report not written ({e})")
        done.append(True)

    threading.Thread(target=work, daemon=True).start()
    poll()


def poll():
    show(list(progress) + ([] if done else ["Working … (every drawing takes a little while)"]))
    if done:
        for b in (run_btn, port_btn):
            b.config(state="normal")
    else:
        root.after(500, poll)


def open_folder():
    if dwg_kat_pdf.OUT_DIR.is_dir():
        os.startfile(dwg_kat_pdf.OUT_DIR)


top = ttk.Frame(root, padding=8)
top.pack(fill="x")
ttk.Entry(top, textvariable=path).pack(side="left", fill="x", expand=True, padx=(0, 6))
ttk.Button(top, text="Browse…", command=browse).pack(side="left")
ttk.Button(top, text="Folder…", command=browse_folder).pack(side="left", padx=(6, 0))
run_btn = ttk.Button(top, text="Run", command=start)
run_btn.pack(side="left", padx=6)
ttk.Button(top, text="Open folder", command=open_folder).pack(side="left")
port_btn = ttk.Button(top, text="Port report…", command=port_report)
port_btn.pack(side="left", padx=(6, 0))
log = tk.Text(root, wrap="word", font=("Segoe UI", 10), state="disabled")
log.tag_config("warn", foreground="#c00000")
log.pack(fill="both", expand=True, padx=8, pady=(0, 8))
show(["Pick one or more DWGs with Browse… (Ctrl/Shift+click to select several), or a whole folder with Folder…, then press Run.",
      "Folder… takes every drawing in the folder and its subfolders: pick the parent folder to get them all,",
      "or press Folder… again to add another folder. Browse… starts a new list.",
      f"Each drawing gets its own folder under {dwg_kat_pdf.OUT_DIR}: one PDF (cover, then a page per floor)",
      "and the warning list. The port report (outlets per floor, counted in the drawing) goes to",
      f"{dwg_kat_pdf.PORT_DIR}: a .txt per drawing and one Word report (Port Raporu.docx) for the whole run.",
      "Port report… writes only that port report, without drawing the PDF: pick the DWGs (or PDFs plotted from AutoCAD).",
      "It cannot read the PDFs Run makes; pick their DWG instead."])
root.mainloop()
