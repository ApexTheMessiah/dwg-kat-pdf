"""DWG -> one PDF (cover + one page per floor / kat) + warning list of rooms without a data outlet.

Usage:  python dwg_kat_pdf.py "plan.dwg"
        python dwg_kat_pdf.py --test           (self-check)
Needs:  pip install ezdxf matplotlib pypdf python-docx, and ODA File Converter installed (for .dwg; .dxf works without it).
Output: a folder per drawing, OUT_DIR/<name>/, holding "<name>.pdf" (cover sheet, then one page per floor)
        and "<name> - eksik data.txt".
Also:   ports_of("plan.dwg") writes only the port report (A/B/C/D, AP and PD outlets per floor); it also takes a PDF
        plotted from AutoCAD (pdf_ports, needs pypdf), not the PDFs made here;
        port_docx([those reports], "Port Raporu.docx") puts them in one Word report (needs python-docx).
"""
import glob, re, sys
from collections import Counter
from pathlib import Path

OUT_DIR = Path.home() / "Downloads" / "DWG Kat PDF" / "pdf"  # every drawing (school) gets its own folder here
# Drawing conventions (layer / block names). Change here if another project uses other names.
PORT_DIR = OUT_DIR.parent / "port pdf"  # every port report (.txt per drawing, Port Raporu.docx) goes here
COVER_LAYER = "Kapak"         # cover sheet (school info, counts, legend) -> "<name> - KAPAK.pdf"
NOT_WALL_LAYERS = {"Merdiven", COVER_LAYER}  # lines on every other layer count as walls (drawings mix DUVAR, 0, Ölçü)
DOOR_LAYER = "Kapı"           # door blocks; their LINE closes the door gap
ROOM_TEXT_LAYERS = {"Yazı", "DUVAR"}  # room names (some drawings put them on the wall layer)
OUTLET_LAYER = "data"         # data outlet blocks
OUTLET_LABEL_LAYER = "Yazı-Uc"  # outlet names (A-40, B-40 ...)
NEAR = 60                     # an outlet this close outside a room's wall is named in the warning
EXTRA_OUTLET_BLOCKS = {"planlanan data"}   # PD (proje dışı) outlet also counts
AP_BLOCK = "access point"
# "... - ZEMİN  KAT", "... - 1.KAT", "ZEMİN KAT", "1. KAT PLANI", "ZEMİN KAT KAT PLANI"
FLOOR_TITLE = re.compile(r"(\S+\s*KAT)(?:\s+KAT)?(?:\s+PLANI)?\s*$")
# A-40, AP-02, PD (proje dışı, has no number); PDF text glues labels to their neighbours ("ODASIAP-02")
# Some drawings write "A - 12"; with the spaces the letter must start a word ("BLOK - 1" is not a label).
# A cabinet is a letter, or a floor digit and a letter ("2A - 24").
PORT = re.compile(r"(AP|[1-9]?[A-Z])-(\d+)|(?<![A-ZÇĞİÖŞÜ])(AP|[1-9]?[A-Z]) - (\d+)|(?<![A-Z])(PD)(?![A-Z])")
# Rooms whose name contains one of these never need an outlet.
SKIP = ["WC", "BİNA ÇIKIŞ", "TOPLANMA ALANI", "OKUL BAHÇESİ", "MERDİVEN", "KORİDOR",
        "MESCİT", "ENERJİ ODASI", "KANTİN", "SİSTEM ODASI", "YEMEKHANE",
        "BEDEN EĞİTİMİ SALONU", "KAZAN DAİRESİ", "DEPO", "SIĞINAK", "MUTFAK NİŞİ", "SOYUNMA",
        "ELK. ODASI", "ASANSÖR", "MÜDÜR", "ÇAY OCAĞI"]  # DEPO also covers SU DEPOSU; MÜDÜR covers MÜDÜR YARDIMCISI


def ray(segs, x, y, d):
    """Distance from (x, y) to the nearest segment hit going L/R/D/U, or None if nothing is hit."""
    best = None
    for x1, y1, x2, y2 in segs:
        if d in "LR":
            if y1 == y2 or not min(y1, y2) <= y <= max(y1, y2):
                continue
            dist = x1 + (y - y1) * (x2 - x1) / (y2 - y1) - x
        else:
            if x1 == x2 or not min(x1, x2) <= x <= max(x1, x2):
                continue
            dist = y1 + (x - x1) * (y2 - y1) / (x2 - x1) - y
        if d in "LD":
            dist = -dist
        if dist > 1 and (best is None or dist < best):
            best = dist
    return best


def room_box(segs, x, y):
    # shortcut: a room is the rectangle found by looking L/R/D/U from its name text, so rooms with no
    # name on ROOM_TEXT_LAYER are never checked and L-shaped rooms may be misjudged; polygonize walls if that bites.
    r = [ray(segs, x, y, d) for d in "LRDU"]
    return None if None in r else (x - r[0], x + r[1], y - r[2], y + r[3])


def inside(box, x, y):
    return box[0] <= x <= box[1] and box[2] <= y <= box[3]


def port_report(pages, cover=0):
    """pages: [(floor name or None, page text without the AP ports, access point symbols on the page, the port names
    written beside them)], cover: outlet total written on the cover sheet (0 = unknown)
    -> {"lines": the text report (outlet counts per page by letter, then repeated / skipped numbers), and the same as
    data for port_docx: "floors" [(name, counts, AP ports)], "total" counts, "cover", "dup" / "gap" numbers}."""
    count = port_sum

    def row(name, n, ap_ports=()):
        # "ZEMİN KAT: 15A 10B  (AP 2: B-01 B-02)"; a cabinet named with a digit is written "30×1A"
        cols = " ".join(f"{n[k]}{'×' * (len(k) > 1)}{k}" for k in cabinets(n)) or "0"
        extra = [f"{k} {n[k]}" for k in ("AP", "PD") if n[k]]
        if ap_ports:
            extra[0] += ": " + " ".join(ap_ports)
        return f"{name}: {cols}" + (f"  ({'; '.join(extra)})" if extra else "")
    lines, total, nums, floors, dup, gap = [], Counter(), {}, [], [], []
    for i, (name, text, aps, ap_ports) in enumerate(pages, 1):
        n = Counter()
        for k, number in map(port_label, PORT.finditer(text)):
            n[k] += 1
            if number:
                nums.setdefault(k, Counter())[number] += 1
        n["AP"] = aps or n["AP"]  # symbols drawn; "AP-01" labels only when no symbol was recognised
        n += Counter()  # drop zero counts
        total += n
        if n or name:  # a page with no title and no outlets is a cover
            floors.append((name or f"Sayfa {i}", n, ap_ports))
            lines.append(row(*floors[-1]))
    lines.append(row("TOPLAM", total) + f"  = {count(total)} uç")
    if cover:
        lines.append(f"{'BİLGİ' if cover == count(total) else 'UYARI'} kapakta toplam uç: {cover}, sayılan: {count(total)}")
    for k, c in sorted(nums.items()):
        twice = [f"{k}-{i:02d}" for i in sorted(c) if c[i] > 1]
        gaps = [f"{k}-{i:02d}" for i in range(1, max(c)) if i not in c]
        lines += [f"UYARI {k}: {what} -> {', '.join(v)}" for what, v in (("tekrar eden", twice), ("atlanan", gaps)) if v]
        dup += twice
        gap += gaps
    return {"lines": lines, "floors": floors, "total": total, "cover": cover, "dup": dup, "gap": gap}


def port_label(m):
    """(cabinet or "AP" or "PD", number or None) of a PORT match."""
    return (m.group(1) or m.group(3) or "PD", int(m.group(2) or m.group(4) or 0) or None)


def cabinets(n):
    """The cabinets in a count (not AP / PD), A before 1A before B."""
    return sorted((k for k in n if k not in ("AP", "PD")), key=lambda k: (k[-1], len(k), k))


def port_sum(n):
    """Outlets in a count: the cabinets' ones, not AP / PD."""
    return sum(n[k] for k in cabinets(n))


def port_docx(reports, dst):
    """Word report of several pdf_ports() results: how to read it, a summary table, then a table per school."""
    from datetime import date
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor
    INK, MUTED, HEAD, BAND, WARN, OK = "1F2937", "6B7280", "E5EDF5", "F6F8FA", "B42318", "1A7F37"
    WIDTH = 17.0  # cm of text on A4 with 2 cm margins

    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.left_margin = sec.right_margin = sec.top_margin = sec.bottom_margin = Cm(2)
    for name, size, before, after in (("Normal", 11, 0, 6), ("Title", 24, 0, 4), ("Heading 1", 16, 18, 8), ("Heading 2", 12.5, 14, 6)):
        st = doc.styles[name]
        st.font.name, st.font.size, st.font.bold = "Calibri", Pt(size), name != "Normal"
        st.font.color.rgb = RGBColor.from_string(INK)
        for a in ("w:ascii", "w:hAnsi", "w:eastAsia"):  # the built-in heading styles carry their own theme font
            st.element.get_or_add_rPr().get_or_add_rFonts().set(qn(a), "Calibri")
        st.paragraph_format.space_before, st.paragraph_format.space_after = Pt(before), Pt(after)
        st.paragraph_format.keep_with_next = name != "Normal"

    def para(parts, size=10, before=0, after=3):  # parts: [(text, bold, colour)]
        p = doc.add_paragraph()
        p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(before), Pt(after)
        for text, bold, colour in parts:
            r = p.add_run(text)
            r.bold, r.font.size = bold, Pt(size)
            r.font.color.rgb = RGBColor.from_string(colour)

    def el(parent, tag, **attrs):
        e = OxmlElement(tag)
        for k, v in attrs.items():
            e.set(qn("w:" + k), v)
        parent.append(e)
        return e

    def table(header, rows, widths, left=(0,), colours={}, size=10, total_row=False):
        t = doc.add_table(rows=1 + len(rows), cols=len(header))
        t.alignment, t.autofit = WD_TABLE_ALIGNMENT.CENTER, False
        borders = el(t._tbl.tblPr, "w:tblBorders")
        for edge in ("top", "bottom", "insideH"):
            el(borders, "w:" + edge, val="single", sz="4", color="D0D7DE")
        for ri, cells in enumerate([header] + rows):
            tr_pr = t.rows[ri]._tr.get_or_add_trPr()
            el(tr_pr, "w:cantSplit", val="true")
            if ri == 0:
                el(tr_pr, "w:tblHeader", val="true")  # repeat the header row on every page
            last = total_row and ri == len(rows)
            for ci, text in enumerate(cells):
                c = t.rows[ri].cells[ci]
                c.width = Cm(widths[ci])
                p = c.paragraphs[0]
                p.paragraph_format.space_before = p.paragraph_format.space_after = Pt(2)
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT if ci in left else WD_ALIGN_PARAGRAPH.CENTER
                r = p.add_run(text)
                r.font.size, r.bold = Pt(size), ri == 0 or last or (ri - 1, ci) in colours
                if (ri - 1, ci) in colours:
                    r.font.color.rgb = RGBColor.from_string(colours[(ri - 1, ci)])
                if ri == 0 or last:
                    el(c._tc.get_or_add_tcPr(), "w:shd", val="clear", color="auto", fill=HEAD if ri == 0 else BAND)

    def num(v):
        return str(v) if v else "–"

    same = sum(r["cover"] == port_sum(r["total"]) for r in reports)
    doc.add_paragraph("Kat Bazında Data Ucu Raporu", style="Title")
    para([(f"{len(reports)} okul  ·  {date.today():%d.%m.%Y}  ·  Kaynak: okulların DATA çizimleri", False, MUTED)], 11, after=14)
    para([(f"Bu rapor, her okulun çiziminde her katta hangi kabinete (A, B, C …) kaç data ucu bağlı olduğunu gösterir. "
           f"Toplam {sum(port_sum(r['total']) for r in reports)} uç ve {sum(r['total']['AP'] for r in reports)} access point "
           f"sayıldı. Sayılan toplam, {len(reports)} okulun {same} tanesinde kapaktaki “Toplam Uç Sayısı” ile aynı.", False, INK)],
         11, after=6)
    doc.add_paragraph("Nasıl okunur", style="Heading 1")
    for label, text in (
            ("A, B, C …", "Uç etiketinin harfi (A-12 → A). Sütundaki sayı, o katta o harfe ait uç adedidir."),
            ("Toplam", "O kattaki harfli uçların toplamı. AP ve PD bu toplama girmez."),
            ("AP", "O katta çizili access point sembolü sayısı."),
            ("AP'nin portu", "Access point'in yanına yazılmış port adı. Bu port 1 uç + 1 AP sayılır; aynı ad ayrıca bir "
                             "prizde de yazıyorsa uç yine 1 sayılır."),
            ("PD", "Proje dışı data ucu."),
            ("Kapak", "Çizimin kapak sayfasında yazan “Toplam Uç Sayısı”. Sayılanla farklıysa kırmızı yazılır.")):
        para([(label + ": ", True, INK), (text, False, INK)], 10.5)

    doc.add_paragraph("Özet", style="Heading 1")
    rows, colours = [], {}
    for i, r in enumerate(reports):
        diff = port_sum(r["total"]) - r["cover"]
        if r["cover"]:
            colours[(i, 5)] = WARN if diff else OK
        rows.append([r["name"], str(port_sum(r["total"])), num(r["total"]["AP"]), num(r["total"]["PD"]), num(r["cover"]),
                     "–" if not r["cover"] else f"{diff:+d}" if diff else "Aynı"])
    table(["Okul", "Uç", "AP", "PD", "Kapak", "Fark"], rows, [9.8, 1.5, 1.3, 1.3, 1.6, 1.5], colours=colours, size=9.5)
    para([("Fark = sayılan − kapak. “Aynı” olanlarda çizim ile kapak tutarlı.", False, MUTED)], 9, before=4)

    doc.add_paragraph("Okul okul döküm", style="Heading 1")
    for r in reports:
        doc.add_paragraph(r["name"], style="Heading 2")
        letters = cabinets(r["total"])
        ap, pd = r["total"]["AP"], r["total"]["PD"]
        header = ["Kat"] + letters + ["Toplam"] + (["AP", "AP'nin portu"] if ap else []) + (["PD"] if pd else [])
        rows = []
        for name, n, ap_ports in r["floors"] + [("TOPLAM", r["total"], ())]:
            row = [name] + [num(n[k]) for k in letters] + [str(port_sum(n))]
            row += [num(n["AP"]), " ".join(ap_ports) or ("" if n["AP"] else "–")] if ap else []
            rows.append(row + ([num(n["PD"])] if pd else []))
        fixed = 3.2 + 1.7 + (4.6 if ap else 0) + (1.2 if pd else 0)
        widths = [3.2] + [min(1.4, (WIDTH - fixed) / max(len(letters), 1))] * len(letters) + [1.7] \
            + ([1.2, 3.4] if ap else []) + ([1.2] if pd else [])
        table(header, rows, widths, left=(0, len(letters) + 3) if ap else (0,), total_row=True)
        if r["cover"]:
            diff = port_sum(r["total"]) - r["cover"]
            para([("Kapak: ", True, INK), (f"{r['cover']} uç yazıyor, {port_sum(r['total'])} sayıldı — "
                                           + (f"fark {diff:+d}." if diff else "aynı."), False, WARN if diff else OK)], before=6)
        if r.get("why"):  # only the DWG count can look for reasons
            para([("Farkın olası nedenleri:", True, INK)], before=4)
            for w in r["why"]:
                para([("•  " + w, False, INK)])
        names = [f[0] for f in r["floors"]]
        if len(set(names)) < len(names):
            para([("Not: ", True, INK), ("Aynı kat adı birden fazla geçiyor; bu çizim birden çok blok içeriyor, satırlar "
                                         "çizimdeki sırayla.", False, INK)])
        for label, v in (("Birden fazla yerde yazan numaralar: ", r["dup"]), ("Çizimde olmayan (atlanan) numaralar: ", r["gap"])):
            if v:
                para([(label, True, INK), (", ".join(v), False, INK)])
    doc.save(dst)


def glyph_text(s):
    """AutoCAD plots some TrueType text as glyph numbers, not characters: Latin is the character code - 29."""
    # shortcut: only the Turkish capitals seen so far are mapped (Arial / Times New Roman); add more here if names look wrong
    s = s.translate(str.maketrans("øhùödg", "İÜŞĞÇÖ"))
    return "".join(chr(ord(c) + 29) if ord(c) < 0x60 and c != "\n" else c for c in s)


AP_FILL = (0.0, 1.0, 0.0)  # the access point symbol is drawn as green filled pieces; outlets are blue triangles
AP_PIECES = 34             # pieces per access point symbol when the PDF has no cover legend to count them on


def _mul(a, b):  # PDF matrix a followed by b
    return (a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3], a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
            a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5])


def pdf_fills(page, reader):
    """[(rgb, x, y)]: colour and centre of every colour-filled shape on the page (outlet triangles, AP symbol pieces)."""
    from pypdf.generic import ContentStream
    ctm, fill, stack, pts, out = (1, 0, 0, 1, 0, 0), None, [], [], []
    for a, op in ContentStream(page.get_contents(), reader).operations:
        op = op.decode() if isinstance(op, bytes) else op
        if op == "q":
            stack.append((ctm, fill))
        elif op == "Q" and stack:
            ctm, fill = stack.pop()
        elif op == "cm":
            ctm = _mul([float(v) for v in a], ctm)
        elif op == "rg":
            fill = tuple(round(float(v), 2) for v in a)
        elif op in ("m", "l"):
            pts.append((float(a[0]), float(a[1])))
        elif op in ("f", "F", "f*", "B", "B*", "b", "b*", "S", "s", "n"):
            if pts and op not in ("S", "s", "n") and fill and any(fill):  # filled, not black
                x, y = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
                out.append((fill, x * ctm[0] + y * ctm[2] + ctm[4], x * ctm[1] + y * ctm[3] + ctm[5]))
            pts = []
    return out


def pdf_ports(path):
    """Count the outlet labels on each page of a PDF plotted from AutoCAD; write PORT_DIR/"<name> - port raporu.txt"
    and return the report (see port_report, plus "name"). RuntimeError, and no file, when nothing can be read."""
    from pypdf import PdfReader
    path = Path(path)
    reader = PdfReader(path)

    pages, cover = [], 0  # cover: "TOPLAM UÇ SAYISI" written on the cover sheet(s)
    ap_pieces = 0         # green pieces in one access point symbol: the cover's legend shows exactly one
    for i, p in enumerate(reader.pages, 1):
        chunks = []  # (text height, text, x, y, writing direction x, y)
        fills = pdf_fills(p, reader)
        near_ap = {}  # index in chunks -> (x, y) of a port label whose nearest symbol is an access point

        def visit(t, cm, tm, font, size):
            if font and font.get("/Encoding") == "/Identity-H" and "/ToUnicode" not in font:
                t = glyph_text(t)
            m = PORT.search(t)
            if m and port_label(m)[1] and port_label(m)[0] != "AP" and fills:
                a = _mul(tm, cm)  # middle of the label on the page: start + half its length along the writing direction
                half = len(t.strip()) * 0.28 * size
                x, y = a[4] + a[0] * half, a[5] + a[1] * half
                if min(fills, key=lambda f: (f[1] - x) ** 2 + (f[2] - y) ** 2)[0] == AP_FILL:
                    near_ap[len(chunks)] = (x, y)
            a = _mul(tm, cm)  # where the text is on the page, and its writing direction (pages can be plotted rotated)
            scale = (a[0] ** 2 + a[1] ** 2) ** 0.5 or 1
            chunks.append((size * scale, t, a[4], a[5], a[0] / scale, a[1] / scale))
        p.extract_text(visitor_text=visit)
        titles = [(c[0], m.group(1)) for c in chunks if (m := FLOOR_TITLE.search(c[1]))]
        name = " ".join(max(titles)[1].rsplit("-", 1)[-1].split()) if titles else None  # biggest title; "LİSESİ-3.KAT"
        green = [f for f in fills if f[0] == AP_FILL]
        if not name:
            ap_pieces = ap_pieces or len(green)
        aps = round(len(green) / (ap_pieces or AP_PIECES)) if name else 0
        ap_ports = {}  # index in chunks -> port name written beside an access point: it is the AP's port, not an outlet
        for j in range(aps):  # a symbol's pieces are drawn one after another; each symbol takes its nearest label
            piece = green[j * len(green) // aps:(j + 1) * len(green) // aps]
            x, y = sum(f[1] for f in piece) / len(piece), sum(f[2] for f in piece) / len(piece)
            free = [k for k in near_ap if k not in ap_ports]
            if free:
                k = min(free, key=lambda k: (near_ap[k][0] - x) ** 2 + (near_ap[k][1] - y) ** 2)
                ap_ports[k] = "%s-%02d" % port_label(PORT.search(chunks[k][1]))
        # An AP's port is one outlet and one AP; when the same name is also written at an outlet on this floor,
        # count that outlet only once.
        at_outlet = {"%s-%02d" % port_label(m) for k, c in enumerate(chunks) if k not in ap_ports
                     for m in PORT.finditer(c[1]) if port_label(m)[1]}
        text = "\n".join(c[1] for k, c in enumerate(chunks) if ap_ports.get(k) not in at_outlet)
        pages.append((name, text, aps, list(ap_ports.values())))
        for size, t, x, y, dx, dy in chunks:
            if "TOPLAM UÇ SAYISI" in t:  # its value is the nearest number further along the same line of writing
                right = [((x2 - x) * dx + (y2 - y) * dy, t2) for _, t2, x2, y2, _, _ in chunks if t2.strip().isdigit()
                         and (x2 - x) * dx + (y2 - y) * dy > 0 and abs((x2 - x) * dy - (y2 - y) * dx) < size * 0.6]
                cover += int(min(right)[1]) if right else 0
    report = port_report(pages, cover) | {"name": path.stem}
    if not report["total"]:  # nothing read: a "0 uç" report would replace the one made from the DWG (same file name)
        raise RuntimeError("no outlet labels can be read in this PDF, so nothing was written. "
                           "Pick the DWG instead (the PDFs Run makes have their text drawn as lines).")
    save_ports(report)
    return report


def save_ports(report):
    """Write a port report to PORT_DIR/"<name> - port raporu.txt" and return that path."""
    PORT_DIR.mkdir(parents=True, exist_ok=True)
    txt = PORT_DIR / f"{report['name']} - port raporu.txt"
    txt.write_text("\n".join(report["lines"]) + "\n", encoding="utf-8")
    return txt


def ports_of(path):
    """Only the port report, saved: of a drawing (.dwg / .dxf, counted in the drawing, no PDF is drawn) or of a PDF
    plotted from AutoCAD (see pdf_ports)."""
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        return pdf_ports(path)
    doc = load(path)
    floors = analyse(doc)[0]
    if not floors:
        raise RuntimeError("no floor titles / page frames in this drawing, so there is no port report for it.")
    report = dwg_ports(doc, floors) | {"name": path.stem}
    save_ports(report)
    return report


def load(path):
    import ezdxf
    if path.suffix.lower() == ".dxf":
        return ezdxf.readfile(path)
    from ezdxf.addons import odafc
    exe = sorted(glob.glob(r"C:\Program Files\ODA\ODAFileConverter*\ODAFileConverter.exe"))
    if not exe:
        raise RuntimeError("ODA File Converter not found under C:\\Program Files\\ODA. Install it, or give a .dxf file.")
    ezdxf.options.set("odafc-addon", "win_exec_path", exe[-1])
    return odafc.readfile(str(path))


def segments(msp):
    walls = [e for e in msp.query("LINE LWPOLYLINE") if e.dxf.layer not in NOT_WALL_LAYERS]
    walls += [v for d in msp.query(f'INSERT[layer=="{DOOR_LAYER}"]') for v in d.virtual_entities() if v.dxftype() == "LINE"]
    segs = []
    for e in walls:
        if e.dxftype() == "LINE":
            pts = [e.dxf.start, e.dxf.end]
        else:
            pts = list(e.vertices_in_wcs())
            if e.closed:
                pts.append(pts[0])
        segs += [(a.x, a.y, b.x, b.y) for a, b in zip(pts, pts[1:])]
    return segs


def text_of(t):
    s = t.plain_text() if t.dxftype() == "MTEXT" else t.dxf.text
    return " ".join(s.split())


def analyse(doc):
    from ezdxf import bbox
    msp = doc.modelspace()
    texts = [(t, text_of(t), bbox.extents([t]).center) for t in msp.query("TEXT MTEXT")]  # floor titles sit on any layer

    floors = {}  # frame box -> name (a frame with two title texts is still one floor)
    frames = [bbox.extents([p]) for p in msp.query("LWPOLYLINE") if p.closed]
    xs, ys = [], []  # edges of the page frames around floor titles (some drawings have a double frame)
    for t, s, c in texts:
        m = FLOOR_TITLE.search(s)
        if not m:
            continue
        hits = [f for f in frames if inside((f.extmin.x, f.extmax.x, f.extmin.y, f.extmax.y), c.x, c.y)]
        if hits:
            xs += [v for f in hits for v in (f.extmin.x, f.extmax.x)]
            ys += [v for f in hits for v in (f.extmin.y, f.extmax.y)]
            f = max(hits, key=lambda f: f.size.x * f.size.y)
            floors[(f.extmin.x, f.extmax.x, f.extmin.y, f.extmax.y)] = m.group(1)
    floors = [(name, frame) for frame, name in sorted(floors.items())]  # left to right as drawn

    labels = [(text_of(t), bbox.extents([t]).center) for t in msp.query(f'TEXT MTEXT[layer=="{OUTLET_LABEL_LAYER}"]')]
    outlets = []  # (point, label)
    for e in msp.query("INSERT"):
        if e.dxf.layer == OUTLET_LAYER or e.dxf.name in EXTRA_OUTLET_BLOCKS:
            tri = [v for v in e.virtual_entities() if v.dxftype() == "SOLID"]
            p = bbox.extents(tri or [e]).center  # triangle sits on the room side of the wall
            near = min(labels, key=lambda l: l[1].distance(p), default=("?", p))
            outlets.append((p, near[0]))

    segs = segments(msp)
    report = []  # (floor, rooms_missing, texts_not_enclosed)
    for fname, frame in floors:
        rooms, loose = {}, []
        for t, s, c in texts:
            if t.dxf.layer not in ROOM_TEXT_LAYERS or not inside(frame, c.x, c.y) or FLOOR_TITLE.search(s):
                continue
            box = room_box(segs, c.x, c.y)
            if box is None:
                loose.append(s)
                continue
            if any(abs(v - e) < 2 for v in box[:2] for e in xs) or any(abs(v - e) < 2 for v in box[2:] for e in ys):
                continue  # reaches the page frame, so it's outside the building (school name, GİRİŞ ...)
            rooms.setdefault(tuple(round(v) for v in box), []).append((-c.y, s))
        named = {box: " ".join(s for _, s in sorted(parts)) for box, parts in rooms.items()}  # top line first
        checked = [b for b, n in named.items() if not any(k in n.upper() for k in SKIP)]
        free = [(p, l) for p, l in outlets if not any(inside(b, p.x, p.y) for b in named)]  # in no room at all
        missing = []
        for box in checked:
            if not any(inside(box, p.x, p.y) for p, _ in outlets):
                grown = (box[0] - NEAR, box[1] + NEAR, box[2] - NEAR, box[3] + NEAR)
                near = sorted(l for p, l in free if inside(grown, p.x, p.y))
                missing.append((named[box], box, near))
        counts = sorted((n, sum(inside(b, p.x, p.y) for p, _ in outlets)) for b, n in named.items())
        report.append((fname, sorted(missing), loose, counts))  # counts: every named room with its outlet count
    return floors, report


def dwg_ports(doc, floors):
    """The port report (see port_report) counted in the drawing itself: the outlet labels inside each floor frame."""
    from ezdxf import bbox
    msp = doc.modelspace()
    texts = [(text_of(t), bbox.extents([t]).center) for t in msp.query("TEXT MTEXT")]
    # on any layer; "AP-01" and "PD" name symbols, which are counted as blocks below
    labels = [(m, c) for s, c in texts if (m := PORT.fullmatch(s)) and port_label(m)[0] not in ("AP", "PD")]
    marks = [(bbox.extents([e]).center, e.dxf.name) for e in msp.query("INSERT")  # outlet, PD and AP symbols
             if e.dxf.layer == OUTLET_LAYER or e.dxf.name in EXTRA_OUTLET_BLOCKS | {AP_BLOCK}]
    pages, odd, twice, bad = [], [], [], []  # twice: AP ports not counted again; bad: names not written like "A-12"
    for name, frame in floors:
        here = [(m, c) for m, c in labels if inside(frame, c.x, c.y)]
        syms = [(p, n) for p, n in marks if inside(frame, p.x, p.y)]
        aps = [p for p, n in syms if n == AP_BLOCK]
        at_ap = [bool(syms) and min(syms, key=lambda s: s[0].distance(c))[1] == AP_BLOCK for _, c in here]
        at_outlet = {m.group() for (m, _), a in zip(here, at_ap) if not a}
        free = [(m, c) for (m, c), a in zip(here, at_ap) if a]
        ap_ports = []
        for p in aps:  # every access point takes the nearest label written at an access point
            if free:
                m, c = min(free, key=lambda l: l[1].distance(p))
                free.remove((m, c))
                ap_ports.append("%s-%02d" % port_label(m))
        # the access point's port is an outlet too, unless the same name is also written at an outlet of this floor
        text = "\n".join([m.group() for (m, _), a in zip(here, at_ap) if not (a and m.group() in at_outlet)]
                         + ["PD"] * sum(n in EXTRA_OUTLET_BLOCKS for _, n in syms))
        twice += [m.group() for (m, _), a in zip(here, at_ap) if a and m.group() in at_outlet]
        bad += [s for s, c in texts if inside(frame, c.x, c.y) and re.fullmatch(r"[1-9]?[A-Z] ?\d+", s)]  # "A06"
        pages.append((" ".join(name.split()), text, len(aps), sorted(ap_ports)))
        outs = [p for p, n in syms if n not in EXTRA_OUTLET_BLOCKS | {AP_BLOCK}]
        # A label beside an access point still labels an outlet when the AP is plugged into one: it is that outlet's nearest label.
        own = {min(range(len(here)), key=lambda i: here[i][1].distance(p)) for p in outs} if here else set()
        n = len(outs), sum(not a or i in own for i, a in enumerate(at_ap))
        if n[0] != n[1]:  # an outlet without a name, a name without an outlet, or a name written unlike "A-12"
            odd.append(f"UYARI {pages[-1][0]}: {n[0]} uç sembolü var, yanlarında {n[1]} etiket yazıyor")

    def written(key):  # the numbers written right of every cover line with key, added up (one cover per block)
        total = 0
        for s, c in texts:
            if key in s:
                right = [(c2.x - c.x, int(s2)) for s2, c2 in texts if s2.isdigit() and c2.x > c.x and abs(c2.y - c.y) < 5]
                total += int(re.search(r"\d+$", s).group()) if s[-1].isdigit() else min(right, default=(0, 0))[1]
        return total

    report = port_report(pages, written("TOPLAM UÇ SAYISI"))
    report["lines"] += odd
    diff, why = report["cover"] - port_sum(report["total"]), []
    if report["cover"] and diff:  # what in the drawing could explain the cover's other total; (+n) = towards the cover
        sign = "+" if diff > 0 else "−"
        lost, pd, found = written("BULUNAMAYAN UÇ"), report["total"]["PD"], 0
        for n, what in ((len(bad), f"etiket “A-12” biçiminde yazılmamış ({', '.join(bad)}); bunlar sayılmadı"),
                        (len(twice), f"access point'in yanında port numarası yazıyor ({', '.join(twice)}) ve aynı numara bir "
                                     "prizde de var; kapak bunları ayrıca uç saymış olabilir"),
                        (pd, "proje dışı uç çizili; kapak bunları toplam uca katmış olabilir"),
                        (lost, "bulunamayan uç kapakta yazıyor; çizimde yoklar ama toplama katılmış olabilir")):
            if 0 < n <= diff:  # a number bigger than the difference cannot be what the cover added
                why.append(f"{n} {what} (+{n}).")
                found += n
        if 0 < found < diff:
            why.append(f"Geriye kalan {diff - found} uç için çizimde açıklama yok; kapaktaki sayı güncellenmemiş olabilir.")
        if report["dup"]:
            why.append(f"Aynı numara birden fazla prizde yazıyor ({', '.join(report['dup'])}); biri yanlış yazılmış olabilir.")
        why += [o.removeprefix("UYARI ") + "." for o in odd if not bad]
        if not why:
            why.append("Her katta sembol ve etiket sayısı eşit, çizimde farkı açıklayan bir şey yok; kapaktaki sayı "
                       "güncellenmemiş ya da elle yanlış girilmiş olabilir.")
        why.append(f"Kapak, çizimden {abs(diff)} uç {'fazla' if diff > 0 else 'az'} ({sign}{abs(diff)}); kesin neden için "
                   "sahadaki uç listesiyle karşılaştırın.")
        report["lines"] += ["OLASI NEDEN: " + w for w in why]
    return report | {"why": why}


def write_pdf(doc, floors, pdf, title=None):
    """One page per (name, frame) in floors, in that order; title is printed at the top of every page."""
    import logging
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.config import BackgroundPolicy, Configuration
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

    logging.getLogger("matplotlib").setLevel(logging.ERROR)  # "Ignoring fixed x limits" noise from equal aspect
    fig = plt.figure()
    ax = fig.add_axes([0.03, 0.03, 0.94, 0.94])  # margin: printers cannot print to the paper edge
    if title:
        fig.text(0.5, 0.94, title, ha="center", fontsize=22, weight="bold")
    cfg = Configuration(background_policy=BackgroundPolicy.WHITE)  # white CAD lines print black
    Frontend(RenderContext(doc), MatplotlibBackend(ax), config=cfg).draw_layout(doc.modelspace())
    with PdfPages(pdf) as pages:
        for _, (x0, x1, y0, y1) in floors:
            landscape = (x1 - x0) >= (y1 - y0)
            W, H = (16.54, 11.69) if landscape else (11.69, 16.54)  # A3
            fig.set_size_inches(W, H)
            # the axes get the frame's own shape, or a neighbouring floor shows in the spare width
            s = min(0.94 * W / (x1 - x0), 0.94 * H / (y1 - y0))
            w, h = s * (x1 - x0) / W, s * (y1 - y0) / H
            ax.set_position([(1 - w) / 2, (1 - h) / 2, w, h])
            ax.set_xlim(x0, x1)
            ax.set_ylim(y0, y1)
            pages.savefig(fig)
    plt.close(fig)
    from pypdf import PdfWriter
    out = PdfWriter(clone_from=str(pdf))
    a4(out)
    out.write(str(pdf))


def a4(writer):  # pages are drawn at A3 so line and text sizes keep their look, then shrunk to print on A4
    for p in writer.pages:
        land = p.mediabox.width > p.mediabox.height
        p.scale_to(*((841.89, 595.28) if land else (595.28, 841.89)))
        p.compress_content_streams()  # scaling leaves them unpacked, three times the size


def floor_order(name):  # BODRUM, ZEMİN, then 1., 2., 3. ...
    return "BODRUM" not in name.upper(), "ZEM" not in name.upper(), name


def cover_pdf(title, counts):
    """The standard cover table for bare drawings (they have none) as PDF bytes; counts: {floor: [outlets, APs]}.
    Only what the drawings show is filled in; the other rows stay empty for the user to complete."""
    import io
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(16.54, 11.69))  # A3 landscape, like the floor pages
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set(xlim=(0, 1), ylim=(0, 1))
    ax.axis("off")
    font = {"family": "Times New Roman", "va": "center"}
    x0, x1, mid, top, h = 0.135, 0.865, 0.535, 0.99, 0.041

    def line(xa, ya, xb, yb):
        ax.plot([xa, xb], [ya, yb], color="black", lw=1)

    for xa, ya, xb, yb in [(x0, 0.01, x0, top), (x1, 0.01, x1, top), (x0, top, x1, top), (x0, 0.01, x1, 0.01),
                           (x0, top - 0.055, x1, top - 0.055), (mid, 0.01, mid, top - 0.055)]:
        line(xa, ya, xb, yb)
    ax.text(x0 + 0.012, top - 0.028, "OKUL ADI:", size=22, **font)
    total = [sum(c[i] for c in counts.values()) for i in (0, 1)]
    rows = [f"TOPLAM UÇ SAYISI: {total[0]}", "BULUNAMAYAN UÇ SAYISI:", "PROJE DIŞI UÇ SAYISI:", "DERSLİK SAYISI:",
            "LABORATUVAR SAYISI:", "BT SINIFI SAYISI:", "ÖĞRETMENLER ODASI SAYISI:", "Z KÜTÜPHANE SAYISI:",
            "KONFERANS SALONU SAYISI:", "MÜDÜR ODASI SAYISI:", "DİĞER BİRİMLER ODA SAYISI:",
            f"KAT SAYISI: {len(counts)}", f"AP SAYISI: {total[1]}"]
    y = top - 0.055
    for i, r in enumerate(rows):
        ax.text(x0 + 0.012, y - h / 2, r, size=22, **font)
        y -= h
        line(x0, y, mid, y)
        if i == 2:
            line(mid, y, x1, y)
    for i, r in enumerate(["ÇİZİM TARİHİ:", "CBS BİNA NUMARASI:", f"KURUM KODU: {title}"]):
        ax.text(mid + 0.006, top - 0.075 - i * 0.02, r, size=13, **font)
    ax.scatter([mid + 0.032], [0.775], marker="s", s=260, color="#00ff00")
    ax.text(mid + 0.062, 0.775, "DATA UCU", size=13, **font)
    ax.scatter([mid + 0.026], [0.735], marker="^", s=200, color="#00ff00")
    ax.text(mid + 0.034, 0.735, "AP", size=13, color="red", weight="bold", **font)
    ax.text(mid + 0.062, 0.735, "ACCESS POİNT", size=13, **font)
    tx0, tx1, tm, ty = x0 + 0.055, x0 + 0.345, x0 + 0.272, y - 0.035  # ETHERNET ANAHTAR table
    for i in range(6):
        line(tx0, ty - i * h, tx1, ty - i * h)
    for x, ya in [(tx0, ty), (tx1, ty), (tm, ty - h)]:
        line(x, ya, x, ty - 5 * h)
    ax.text(tx0 + 0.035, ty - h / 2, "ETHERNET ANAHTAR", size=22, **font)
    for i, r in enumerate(["24 POE SWITCH", "24 NON-POE SWITCH", "48 POE SWITCH", "48 NON-POE SWITCH"], 1):
        ax.text(tx0 + 0.014, ty - i * h - h / 2, r, size=22, **font)
    buf = io.BytesIO()
    fig.savefig(buf, format="pdf")
    plt.close(fig)
    return buf


def add_page(pdf, name, page_pdf, count, title):
    """Put the one-page page_pdf into pdf under the bookmark name (a page already bookmarked so is replaced)
    and redo the cover; count is this floor's [outlets, APs]."""
    import io, json
    from pypdf import PdfReader, PdfWriter
    pages, counts = {}, {}
    if pdf.exists():
        old = PdfReader(pdf)
        pages = {o.title: old.pages[old.get_destination_page_number(o)] for o in old.outline if o.title != "KAPAK"}
        counts = json.loads(old.metadata.get("/Floors", "{}"))  # the cover totals need every floor's count
    pages[name], counts[name] = PdfReader(page_pdf).pages[0], count
    out = PdfWriter()
    out.add_page(PdfReader(cover_pdf(title, counts)).pages[0])
    out.add_outline_item("KAPAK", 0)
    for i, n in enumerate(sorted(pages, key=floor_order), 1):
        out.add_page(pages[n])
        out.add_outline_item(n, i)
    out.add_metadata({"/Floors": json.dumps(counts)})
    a4(out)
    buf = io.BytesIO()  # the old file is still being read from
    out.write(buf)
    pdf.write_bytes(buf.getvalue())


def run(path):
    """Write OUT_DIR/<name>/ (PDF, warning list, port report); return (file names written, warning lines, that folder,
    the port report for port_docx or None for a bare drawing)."""
    path = Path(path)
    doc = load(path)
    floors, report = analyse(doc)
    from ezdxf import bbox
    lines, stem, bare = [], path.stem, not floors
    if bare:  # one bare floor per file, no title or page frame: the whole drawing is one page of the folder's PDF
        boxes = [b for e in doc.modelspace() if (b := bbox.extents([e])).has_data]
        texts = [b for e in doc.modelspace().query("TEXT MTEXT") if (b := bbox.extents([e])).has_data]
        if not boxes:
            raise RuntimeError("The drawing is empty.")
        c = bbox.extents([])  # grown from the texts over everything that touches it: a stray line far away stays out
        c.extend(v for b in texts or boxes for v in (b.extmin, b.extmax))
        while True:
            rest = [b for b in boxes if b.extmin.x > c.extmax.x + 20 or b.extmax.x < c.extmin.x - 20
                    or b.extmin.y > c.extmax.y + 20 or b.extmax.y < c.extmin.y - 20]
            if len(rest) == len(boxes):
                break
            c.extend(v for b in boxes if b not in rest for v in (b.extmin, b.extmax))
            boxes = rest
        ik = "IK_" * path.stem.upper().startswith("IK_")  # the IK_ set gets its own PDF, like the other schools
        stem = ik + path.resolve().parent.name  # the folder is named after the kurum kodu
        floors = [(path.stem[len(ik):], (c.extmin.x - 20, c.extmax.x + 20, c.extmin.y - 20, c.extmax.y + 20))]
        lines.append("BİLGİ: kat başlığı / sayfa çerçevesi yok; her çizim bir sayfa olarak basıldı, data ucu kontrolü yapılmadı.")
    c = bbox.extents(doc.modelspace().query(f'*[layer=="{COVER_LAYER}"]'))
    cover = [("KAPAK", (c.extmin.x - 20, c.extmax.x + 20, c.extmin.y - 20, c.extmax.y + 20))] if c.has_data else []
    for fname, missing, loose, _ in report:
        for m, _, near in missing:
            hint = f"  (duvarın hemen dışında: {', '.join(near)})" if near else ""
            lines.append(f"UYARI {' '.join(fname.split())}: data ucu yok -> {m}{hint}")
        lines += [f"BİLGİ {' '.join(fname.split())}: duvarla çevrili değil, kontrol edilmedi -> {s}" for s in loose]
    folder = OUT_DIR / stem
    folder.mkdir(parents=True, exist_ok=True)
    pdf = folder / f"{stem}.pdf"
    if bare:
        page = folder / "_page.pdf"
        write_pdf(doc, floors, page, f"{stem} - {floors[0][0]}" + " KAT" * ("KAT" not in floors[0][0].upper()))  # the drawing itself carries no title
        words = " ".join(text_of(t) for t in doc.modelspace().query("TEXT MTEXT")).split()
        count = [sum(bool(re.fullmatch(r"[A-Z]\d+", w)) for w in words), words.count("AP")]  # "A67", "AP"
        add_page(pdf, floors[0][0], page, count, stem)
        page.unlink()
        ports, names = None, []  # their counts are on the cover page made above
    else:
        write_pdf(doc, cover + floors, pdf)
        ports = dwg_ports(doc, floors) | {"name": stem}
        names = [str(save_ports(ports))]  # full path: it is not in the drawing's folder
    txt = folder / f"{stem} - eksik data.txt"
    txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [pdf.name, txt.name] + names, lines, folder, ports


def main(path):
    try:
        names, lines, folder, ports = run(path)
    except RuntimeError as e:
        sys.exit(str(e))
    print("Folder:", folder)
    for n in names:
        print("  ", n)
    print("\n".join(ports["lines"]) if ports else "")
    print("\n".join(lines) if lines else "Every room has a data outlet.")


def _selftest():
    # 1000x1000 room, door gap on the right wall (y 400..600) closed by a door line, slightly slanted left wall.
    segs = [(0, 0, 1000, 0), (1000, 1000, 0, 1000), (1, 0, 0, 1000),
            (1000, 0, 1000, 400), (1000, 600, 1000, 1000), (1000, 400, 1000, 600)]
    box = room_box(segs, 500, 500)
    assert box and abs(box[0] - 0.5) < 1e-6 and box[1:] == (1000, 0, 1000), box
    assert room_box(segs[:-1], 500, 500) is None  # open door gap -> not enclosed
    assert inside(box, 990, 10) and not inside(box, 1010, 10)
    assert [port_label(m) for m in PORT.finditer("A - 9\nBLOK - 1\nODASIAP-02\nPD\n2A - 24")] \
        == [("A", 9), ("AP", 2), ("PD", None), ("2A", 24)]
    assert cabinets(Counter({"B": 1, "1A": 2, "AP": 1, "A": 3})) == ["A", "1A", "B"]
    assert sorted(["2. KAT", "ZEMİN", "1. KAT", "BODRUM"], key=floor_order) == ["BODRUM", "ZEMİN", "1. KAT", "2. KAT"]
    titles = {"ÖRNEK ORTAOKULU- ZEMİN KAT KAT PLANI": "ZEMİN KAT", "OKUL - ZEMİN  KAT": "ZEMİN  KAT",
              "OKUL - 1.KAT": "1.KAT", "3. KAT PLANI": "3. KAT", "ZEMİN KAT PLANI": "ZEMİN KAT"}
    for s, want in titles.items():
        assert FLOOR_TITLE.search(s).group(1) == want, s
    assert not FLOOR_TITLE.search("KAT SAYISI:")
    got = port_report([(None, "KAPAK\n36", 0, []), (None, "A-01A-03\nC-01\nODASIAP-01 PD\nWC", 0, []),
                       ("1.KAT", "A-03 B-02\nPD", 2, ["B-02"]), ("BODRUM KAT", "DEPO", 0, [])], 6)
    assert port_sum(got["total"]) == 5 and got["dup"] == ["A-03"] and len(got["floors"]) == 3
    got = got["lines"]
    assert got == ["Sayfa 2: 2A 1C  (AP 1; PD 1)",
                   "1.KAT: 1A 1B  (AP 2: B-02; PD 1)",
                   "BODRUM KAT: 0",
                   "TOPLAM: 3A 1B 1C  (AP 3; PD 2)  = 5 uç",
                   "UYARI kapakta toplam uç: 6, sayılan: 5",
                   "UYARI A: tekrar eden -> A-03", "UYARI A: atlanan -> A-02", "UYARI B: atlanan -> B-01"], got
    assert glyph_text("/ø6(6ø\x03\x10\x03=(0ø1\x03.$7\n") == "LİSESİ - ZEMİN KAT\n" and glyph_text("\x14\x11.$7") == "1.KAT"
    # An access point plugged into an outlet: that outlet's label (A-01) is nearer to the AP, yet the outlet has its label.
    import ezdxf
    doc = ezdxf.new()
    msp = doc.modelspace()
    for b in ("priz", AP_BLOCK):
        doc.blocks.new(b).add_circle((0, 0), 5)
    for b, layer, at in (("priz", OUTLET_LAYER, (100, 100)), ("priz", OUTLET_LAYER, (500, 100)), (AP_BLOCK, "0", (140, 190))):
        msp.add_blockref(b, at, dxfattribs={"layer": layer})
    for s, at in (("A-01", (130, 150)), ("A-02", (500, 130))):
        msp.add_text(s, dxfattribs={"insert": at, "height": 10})
    got = dwg_ports(doc, [("1.KAT", (0, 1000, 0, 1000))])["lines"]
    assert got == ["1.KAT: 2A  (AP 1: A-01)", "TOPLAM: 2A  (AP 1)  = 2 uç"], got
    msp.add_blockref("priz", (800, 100), dxfattribs={"layer": OUTLET_LAYER})  # an outlet with no label is still reported
    got = dwg_ports(doc, [("1.KAT", (0, 1000, 0, 1000))])["lines"]
    assert got[-1] == "UYARI 1.KAT: 3 uç sembolü var, yanlarında 2 etiket yazıyor", got
    print("self-test ok")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    _selftest() if sys.argv[1] == "--test" else main(sys.argv[1])
