from pathlib import Path
import json, re, sys
from collections import defaultdict, OrderedDict

from ebooklib import epub
import markdown

from utils import smart_q, html_id, apply_glossary_links
from config_loader import load_config
from validator import validate_all_json_files

def build_bible_epub(
    root: Path,
    holy_dir: Path,
    generate_md: bool = False,
    generate_txt: bool = False,
):
    validate_all_json_files(holy_dir)
    if not holy_dir.exists():
        raise SystemExit("✗ `_HOLY_BIBLE` folder not found.")

    CFG      = load_config(root)
    TITLE    = CFG["meta"]["epub_title"]
    VERSION  = CFG["meta"]["version_number"]
    PUBDATE  = CFG["meta"]["publication_date"]
    EDITION  = CFG["meta"].get("bible_edition", "")
    EPUB_NAME= f"{TITLE.replace(' ', '_')}_{VERSION}_{PUBDATE}.epub"
    MD_NAME  = f"{TITLE.replace(' ', '_')}_{VERSION}_{PUBDATE}.md"
    TXT_NAME = f"{TITLE.replace(' ', '_')}_{VERSION}_{PUBDATE}.txt"

    FMT      = CFG["formatting"]
    FOOT     = CFG.get("footnotes", {})
    SMART_Q  = FMT.get("convert_smart_quotes", False)

    # Load glossary
    gloss_path = holy_dir / "Glossary.json"
    try:
        GLOSSARY = json.loads(gloss_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        GLOSSARY = {}

    # 1. Front-matter / intro pages
    intro_pages, intro_dir = _collect_intro_pages(holy_dir)

    # 2. Gather chapter JSONs
    books = _collect_bible_books(holy_dir, intro_dir)

    # 3. Build EPUB
    book, chap_map, txt_lines, md_lines = _assemble_epub(
        books=books,
        intro_pages=intro_pages,
        cfg=CFG,
        smart_quotes=SMART_Q,
        generate_md=generate_md,
        generate_txt=generate_txt,
        title=TITLE,
        version=VERSION,
        pubdate=PUBDATE,
        edition=EDITION,
        fmt=FMT,
        foot_cfg=FOOT,
        holy_dir=holy_dir,
        glossary=GLOSSARY,
    )

    epub.write_epub(EPUB_NAME, book)
    print("✓ EPUB created:", EPUB_NAME)
    _maybe_write_markdown(generate_md, md_lines, CFG, chap_map, MD_NAME)
    _maybe_write_txt(generate_txt, txt_lines, TXT_NAME)

def _collect_intro_pages(holy_dir: Path):
    intro_pages = []
    intro_dir   = holy_dir / "_0_Intro"
    if intro_dir.exists():
        for p in sorted(intro_dir.iterdir()):
            if p.suffix.lower() not in (".json", ".md"):
                continue
            if p.suffix.lower() == ".json":
                data      = json.loads(p.read_text(encoding="utf-8"))
                title     = data.get("title") or p.stem
                raw_md    = data.get("markdown") or data.get("content", "")
                raw_html  = data.get("html") or markdown.markdown(raw_md)
                order_val = data.get("order")
            else:
                md_text   = p.read_text(encoding="utf-8")
                m         = re.search(r"^#\s*(.+)", md_text, flags=re.MULTILINE)
                title     = m.group(1).strip() if m else p.stem.replace("_", " ").title()
                raw_html  = markdown.markdown(md_text)
                order_val = None
            if order_val is None:
                m         = re.match(r"(\d+)_", p.stem)
                order_val = int(m.group(1)) if m else 0
            intro_pages.append(
                {
                    "order": order_val,
                    "title": title,
                    "html":  raw_html,
                    "file_name": p.stem + ".xhtml",
                }
            )
        intro_pages.sort(key=lambda d: d["order"])
    return intro_pages, intro_dir

def _collect_bible_books(holy_dir: Path, intro_dir: Path):
    books = OrderedDict()
    for path in sorted(holy_dir.rglob("*.json"), key=lambda p: p.name):
        if intro_dir.exists() and path.parent == intro_dir:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if "book" not in data or "chapter" not in data:
            # Skip files like preface, glossary, or malformed JSONs
            continue
        key  = (data.get("testament", "ZZ"), data["book"])
        books.setdefault(key, []).append(data)
    for lst in books.values():
        lst.sort(key=lambda d: d["chapter"])
    books = OrderedDict(
        sorted(
            books.items(),
            key=lambda kv: (0 if kv[0][0].upper().startswith("OT") else 1, kv[0][1]),
        )
    )
    return books

def _assemble_epub(
    books,
    intro_pages,
    cfg,
    smart_quotes,
    generate_md,
    generate_txt,
    title,
    version,
    pubdate,
    edition,
    fmt,
    foot_cfg,
    holy_dir,
    *,
    glossary,
):
    txt_lines, md_lines = [], []
    chap_map = OrderedDict()

    book = epub.EpubBook()
    book.set_identifier("ttt-bible-full")
    book.set_title(title)
    book.set_language("en")

    for dc in ("creator", "publisher", "rights", "subject"):
        if dc in cfg["meta"]:
            book.add_metadata("DC", dc, str(cfg["meta"][dc]))

    STYLE = (
        f"body{{font-family:serif;font-size:{fmt['verse_font_size']};"
        f"line-height:{fmt['line_spacing']};margin:1em;}}"
        f"h1.title-page{{font-size:{fmt['epub_title_font_size']};text-align:center;"
        f"margin:0;font-weight:bold;}}"
        f"h1.book-title{{font-size:{fmt['book_title_font_size']};text-align:center;"
        f"margin:2em 0 .5em;font-weight:bold;}}"
        f"h1.chapter-title{{font-size:{fmt['chapter_title_font_size']};text-align:center;"
        f"margin:0 0 1em;}}"
        f"h2{{font-size:1.15em;margin:0;padding:0;page-break-after:avoid;}}"
        f"h2+p{{margin-top:0;}}"
        f"sup{{vertical-align:super;font-size:{fmt['superscript_font_size']};}}"
        f".title-wrapper{{display:flex;flex-direction:column;justify-content:center;"
        f"align-items:center;min-height:100vh;}}"
        f".edition-info{{font-size:{fmt.get('edition_info_font_size','1em')};text-align:center;"
        f"margin-top:1em;}}"
        f"div.footnotes p{{margin:.25em 0;font-size:{foot_cfg.get('footnote_font_size','0.8em')}}}"
        f"div.footnotes p strong{{font-size:{foot_cfg.get('footnotes_title_font_size','1em')}}}"
        f"a.glossary-word{{color:inherit;font-style:italic;text-decoration:none;}}"
    )

    nav_css = epub.EpubItem(
        uid="style", file_name="style/nav.css", media_type="text/css", content=STYLE
    )
    book.add_item(nav_css)

    spine = []

    cover_img = holy_dir / "cover.jpg"
    if cover_img.exists():
        book.set_cover("cover.jpg", cover_img.read_bytes())

    title_pg = epub.EpubHtml(title="Title", file_name="title.xhtml", lang="en")
    title_pg.content = (
        f"<div class='title-wrapper'><h1 class='title-page'>{title}</h1>"
        f"<p class='edition-info'>{edition} — Version {version} — {pubdate}</p></div>"
    )
    title_pg.add_item(nav_css)
    book.add_item(title_pg)
    spine.append(title_pg)

    toc_links_intro = []
    for pg in intro_pages:
        doc = epub.EpubHtml(
            title=pg["title"], file_name=pg["file_name"], lang="en"
        )
        doc.content = f"<h1 class='chapter-title'>{pg['title']}</h1>{pg['html']}"
        doc.add_item(nav_css)
        book.add_item(doc)
        spine.append(doc)
        toc_links_intro.append((pg["title"], doc))

    # --- Do NOT add glossary here ---

    if generate_txt:
        txt_lines.extend(
            [title.upper(), f"Edition: {edition} | Version: {version} | Date: {pubdate}", ""]
        )
    if generate_md:
        md_lines.extend(
            [
                f"# {title}",
                f"_Edition: {edition} · Version {version} · {pubdate}_",
                "",
            ]
        )
        if cfg.get("output", {}).get("include_toc_page", True):
            md_lines.extend(["## Table of Contents", ""])
            for lbl, _ in toc_links_intro:
                md_lines.append(f"- {lbl}")

    for (_, bk), chapters in books.items():
        for ch in chapters:
            html = _render_chapter(
                chapter_data=ch,
                book_name=bk,
                smart_quotes_on=smart_quotes,
                generate_md=generate_md,
                generate_txt=generate_txt,
                md_lines=md_lines,
                txt_lines=txt_lines,
                foot_cfg=foot_cfg,
                glossary=glossary,
            )
            file_name = f"{bk}_{ch['chapter']}.xhtml"
            doc = epub.EpubHtml(
                title=f"{bk} {ch['chapter']}", file_name=file_name, lang="en"
            )
            doc.content = html
            doc.add_item(nav_css)
            book.add_item(doc)
            spine.append(doc)
            chap_map.setdefault(bk, []).append((ch["chapter"], doc))

    toc_doc = _build_epub_toc(toc_links_intro, chap_map, nav_css)
    book.add_item(toc_doc)
    spine.insert(1, toc_doc)

    nav_items = [
        epub.Link(pg.file_name, lbl, html_id(lbl)) for lbl, pg in toc_links_intro
    ]
    for bk, lst in chap_map.items():
        nav_items.extend(
            epub.Link(doc.file_name, f"{bk} {num}", html_id(f"{bk} {num}"))
            for num, doc in lst
        )

    # ---- ADD GLOSSARY AT END -----
    gloss_doc = None
    if glossary:
        gloss_html = "<h1 class='chapter-title'>Glossary</h1><dl>"
        for term, defi in sorted(glossary.items(), key=lambda t: t[0].lower()):
            gloss_html += (
                f'<dt id="{term.lower()}"><b>{term}</b></dt>'
                f'<dd>{defi}</dd>'
            )
        gloss_html += "</dl>"
        gloss_doc = epub.EpubHtml(
            title="Glossary", file_name="glossary.xhtml", lang="en"
        )
        gloss_doc.content = gloss_html
        gloss_doc.add_item(nav_css)
        book.add_item(gloss_doc)
        spine.append(gloss_doc)
        nav_items.append(epub.Link("glossary.xhtml", "Glossary", "glossary"))

    book.toc   = tuple(nav_items)
    book.spine = spine

    book.add_item(epub.EpubNav())
    book.add_item(epub.EpubNcx())

    return book, chap_map, txt_lines, md_lines

def _render_chapter(
    chapter_data,
    book_name,
    smart_quotes_on,
    generate_md,
    generate_txt,
    md_lines,
    txt_lines,
    foot_cfg,
    *,
    glossary,
):
    c_num = chapter_data["chapter"]
    html  = ""

    if c_num == 1:
        html += f"<h1 class='book-title'>{book_name}</h1>"
        if generate_md:
            md_lines.append(f"\n# {book_name}\n")

    html += f"<h1 class='chapter-title'>Chapter {c_num}</h1>"
    if generate_md:
        md_lines.append(f"## Chapter {c_num}\n")
    if generate_txt:
        txt_lines.append(f"{book_name.upper()} Chapter {c_num}")

    fn_map = defaultdict(list)
    idx = 0
    for fn in chapter_data.get("footnotes", []):
        content = fn.get("content", "").strip()
        if not content or content.lower() == "nan":
            continue
        verse  = fn["verse"]
        letter = fn.get("letter") or chr(ord("a") + idx)
        idx   += 1
        fn["ltr"] = letter
        fn_map[verse].append(fn)

    for sec in chapter_data["sections"]:
        hl = sec.get("headline", "").strip()
        if hl:
            html += f"<h2>{hl}</h2>"
            if generate_md:
                md_lines.append(f"### {hl}\n")
            if generate_txt:
                txt_lines.append("")
                txt_lines.append(hl)

        verse_run = ""
        for v in sec["verses"]:
            number = v["verse"]
            txt    = smart_q(v["text"], smart_quotes_on)
            txt = apply_glossary_links(txt, glossary)
            if number in fn_map:
                for fn in fn_map[number]:
                    aid = html_id(f"{book_name}-{c_num}-{number}-{fn['ltr']}")
                    txt += f"&#8239;<sup><a href='#{aid}'>{fn['ltr']}</a></sup>"
            #verse_run += (
            #    f"<a id='v-{book_name}-{c_num}-{number}'></a>{txt}&#8239;"
            #    f"<b><sup>{number}</sup></b> "
            #)
            verse_run += (
                f"<a id='v-{book_name}-{c_num}-{number}'></a><b><sup>{number}</sup></b>&#8239;"
                f"{txt} "
            )

            
            if generate_txt:
                txt_lines.append(f"{number}. {v['text']}")
            if generate_md:
                md_lines.append(f"**{number}** {txt}")
        html += f"<p>{verse_run.strip()}</p>"

    if fn_map:
        html += (
            f"<div class='footnotes'><p><strong>"
            f"{foot_cfg.get('footnotes_title', 'Translation Notes')}:</strong></p>"
        )
        if generate_md:
            md_lines.append("\n#### Translation Notes\n")
        for vn in sorted(fn_map):
            for fn in fn_map[vn]:
                aid  = html_id(f"{book_name}-{c_num}-{vn}-{fn['ltr']}")
                back = f"v-{book_name}-{c_num}-{vn}"
                html += (
                    f"<p id='{aid}'><b>{book_name} {c_num}:{vn}</b> - "
                    f"{fn['ltr']}. {fn['content']} "
                    f"<a href='#{back}'>[back]</a></p>"
                )
                if generate_md:
                    md_lines.append(
                        f"*{book_name} {c_num}:{vn}* - {fn['ltr']}. {fn['content']}"
                    )
        html += "</div>"

    if generate_txt:
        txt_lines.append("")

    return html

def _build_epub_toc(toc_links_intro, chap_map, nav_css):
    toc_html = (
        "<h1 class='chapter-title' style='text-align:center'>Table of Contents</h1>"
        "<table style='width:90%;margin:auto;'><tr><td>"
    )
    if toc_links_intro:
        toc_html += "".join(
            f"<br><a href='{pg.file_name}'>{lbl}</a>" for lbl, pg in toc_links_intro
        )
    for bk, lst in chap_map.items():
        toc_html += (
            f"<br><b>{bk}</b> "
            + " ".join(f"<a href='{doc.file_name}'>{num}</a>" for num, doc in lst)
        )
    toc_html += "</td></tr></table>"

    toc_doc = epub.EpubHtml(
        title="Table of Contents", file_name="toc.xhtml", lang="en"
    )
    toc_doc.content = toc_html
    toc_doc.add_item(nav_css)
    return toc_doc

def _maybe_write_markdown(generate_md, md_lines, cfg, chap_map, md_name):
    if not generate_md:
        return
    with open(md_name, "w", encoding="utf-8") as f:
        for line in md_lines:
            f.write(line.rstrip() + "\n")

def _maybe_write_txt(generate_txt, txt_lines, txt_name):
    if not generate_txt:
        return
    with open(txt_name, "w", encoding="utf-8") as f:
        for line in txt_lines:
            f.write(line.rstrip() + "\n")
            
