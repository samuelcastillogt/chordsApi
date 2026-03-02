from flask import Flask, request, Response, jsonify, send_from_directory, render_template, redirect
from flask_cors import CORS
import json
from typing import List, Optional
import hashlib
import re
import html
from pathlib import Path
from db import (
    ensure_canciones_table,
    canciones_table_exists,
    insert_cancion,
    get_cancion_by_slug,
)
app = Flask(__name__)
CORS(app)

BASE_DIR = Path(__file__).resolve().parent
CHORDS_DIST_DIR = BASE_DIR / "static" / "app"

CHORD_SHAPES_GUITAR = {
    "Cmaj": {"pos": [-1, 3, 2, 0, 1, 0], "fretStart": 1},
    "Gmaj": {"pos": [3, 2, 0, 0, 0, 3], "fretStart": 1},
    "Dmaj": {"pos": [-1, -1, 0, 2, 3, 2], "fretStart": 1},
    "Amin": {"pos": [-1, 0, 2, 2, 1, 0], "fretStart": 1},
    "Emin": {"pos": [0, 2, 2, 0, 0, 0], "fretStart": 1},
}

SONG_LIBRARY = {
    "noche-en-seis-cuerdas": {
        "title": "Noche en Seis Cuerdas",
        "artist": "Guitarra App",
        "album": "Sesion Demo",
        "tonality": "E minor",
        "bpm": 92,
        "lines": [
            {
                "lyrics": "Sigo marcando el ritmo en la ciudad",
                "chords": [
                    {"name": "Emin", "position": 0},
                    {"name": "Dmaj", "position": 18},
                    {"name": "Cmaj", "position": 29},
                ],
            },
            {
                "lyrics": "cae la noche y vuelve a respirar",
                "chords": [
                    {"name": "Amin", "position": 0},
                    {"name": "Cmaj", "position": 16},
                    {"name": "Gmaj", "position": 26},
                ],
            },
            {
                "lyrics": "todo parece abrirse una vez mas",
                "chords": [
                    {"name": "Emin", "position": 0},
                    {"name": "Dmaj", "position": 18},
                    {"name": "Gmaj", "position": 29},
                ],
            },
            {
                "lyrics": "cuando la banda vuelve a tocar",
                "chords": [
                    {"name": "Amin", "position": 0},
                    {"name": "Cmaj", "position": 16},
                    {"name": "Emin", "position": 27},
                ],
            },
        ],
    }
}
SONG_DRAFTS: List[dict] = []
DB_INIT_ERROR: Optional[str] = None

try:
    ensure_canciones_table()
except Exception as error:
    DB_INIT_ERROR = str(error)


def _parse_pos_csv(pos: str) -> List[int]:
    return [int(x.strip()) for x in pos.split(",")]


def render_guitar_svg(
    name: str,
    positions: List[int],
    fret_start: int = 1,
    frets_visible: int = 5,
    barres: Optional[List[dict]] = None,
) -> str:
    """
    positions: 6 ints, low->high (E A D G B e)
      -1 mute, 0 open, >=1 fret
    """
    if len(positions) != 6:
        raise ValueError("positions must have 6 values for guitar")

    barres = barres or []

    # Layout
    W, H = 260, 360
    margin_top = 60
    margin_left = 40
    grid_w = 180
    grid_h = 220
    strings = 6
    frets = frets_visible

    string_gap = grid_w / (strings - 1)
    fret_gap = grid_h / frets

    # Helpers
    def x_for_string(i_0_based: int) -> float:
        return margin_left + i_0_based * string_gap

    def y_for_fret_line(fret_index_0_based: int) -> float:
        return margin_top + fret_index_0_based * fret_gap

    def y_for_fret_center(fret_number: int) -> float:
        rel = fret_number - fret_start
        return margin_top + (rel + 0.5) * fret_gap

    # Start SVG
    svg = []
    svg.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
    )
    svg.append('<rect width="100%" height="100%" fill="white"/>')

    # Title
    svg.append(
        f'<text x="{W/2}" y="32" font-size="20" text-anchor="middle" font-family="Arial">{name}</text>'
    )

    # Fret label if not starting at 1
    if fret_start != 1:
        svg.append(
            f'<text x="{margin_left + grid_w + 18}" y="{margin_top + 14}" font-size="14" font-family="Arial">fret {fret_start}</text>'
        )

    # Nut (thicker top line if fret_start == 1)
    nut_y = margin_top
    nut_thickness = 6 if fret_start == 1 else 2
    svg.append(
        f'<line x1="{margin_left}" y1="{nut_y}" x2="{margin_left+grid_w}" y2="{nut_y}" stroke="black" stroke-width="{nut_thickness}"/>'
    )

    # Frets (remaining)
    for f in range(1, frets + 1):
        y = y_for_fret_line(f)
        svg.append(
            f'<line x1="{margin_left}" y1="{y}" x2="{margin_left+grid_w}" y2="{y}" stroke="black" stroke-width="2"/>'
        )

    # Strings
    for s in range(strings):
        x = x_for_string(s)
        svg.append(
            f'<line x1="{x}" y1="{margin_top}" x2="{x}" y2="{margin_top+grid_h}" stroke="black" stroke-width="2"/>'
        )

    # Open/mute markers above nut
    marker_y = margin_top - 18
    for i, p in enumerate(positions):
        x = x_for_string(i)
        if p == -1:
            svg.append(
                f'<text x="{x}" y="{marker_y}" font-size="16" text-anchor="middle" font-family="Arial">x</text>'
            )
        elif p == 0:
            svg.append(
                f'<text x="{x}" y="{marker_y}" font-size="16" text-anchor="middle" font-family="Arial">o</text>'
            )

    # Barres
    for b in barres:
        fret = int(b["fret"])
        from_s = int(b["fromString"])
        to_s = int(b["toString"])
        # Convert (6..1) to (0..5) where 0=low E, 5=high e (left-to-right)
        a = 6 - from_s
        c = 6 - to_s
        x1 = x_for_string(min(a, c))
        x2 = x_for_string(max(a, c))
        y = y_for_fret_center(fret)
        svg.append(
            f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="black" stroke-width="10" stroke-linecap="round"/>'
        )

    # Finger dots
    for i, p in enumerate(positions):
        if p <= 0:
            continue
        if not (fret_start <= p < fret_start + frets_visible):
            continue
        x = x_for_string(i)
        y = y_for_fret_center(p)
        svg.append(f'<circle cx="{x}" cy="{y}" r="10" fill="black"/>')

    svg.append("</svg>")
    return "\n".join(svg)


def etag_for(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def title_from_slug(value: str) -> str:
    return " ".join(part.capitalize() for part in value.split("-") if part)


def slugify(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"[^a-z0-9\s-]", "", lowered)
    lowered = re.sub(r"[\s_]+", "-", lowered)
    lowered = re.sub(r"-{2,}", "-", lowered)
    return lowered.strip("-")


CHORD_TOKEN_REGEX = re.compile(
    r"[A-G](?:#|b)?(?:maj|min|m|sus\d*|dim|aug|add\d*|M?\d*)?(?:/[A-G](?:#|b)?)?"
)


def is_chord_line(line: str) -> bool:
    clean = line.strip()
    if not clean:
        return False
    matches = list(CHORD_TOKEN_REGEX.finditer(line))
    if not matches:
        return False
    if len(matches) >= 2:
        return True
    return clean in {"Em", "A", "D", "G", "C", "Bm", "F#m", "Gm", "E", "B"}


def parse_song_text_to_lines(song_text: str) -> List[dict]:
    raw_lines = song_text.split("\n")
    parsed: List[dict] = []
    idx = 0

    while idx < len(raw_lines):
        current = raw_lines[idx].rstrip()
        if not current.strip():
            idx += 1
            continue

        if is_chord_line(current):
            chord_matches = list(CHORD_TOKEN_REGEX.finditer(current))
            chords = [
                {"name": match.group(0), "position": match.start()}
                for match in chord_matches
            ]
            next_line = ""
            if idx + 1 < len(raw_lines):
                candidate = raw_lines[idx + 1].rstrip()
                if candidate.strip() and not is_chord_line(candidate):
                    next_line = candidate
                    idx += 1
            parsed.append({"lyrics": next_line, "chords": chords})
        else:
            parsed.append({"lyrics": current, "chords": []})

        idx += 1

    return parsed


def build_song_payload(song_name: str) -> dict:
    song_key = song_name.strip().lower()
    if song_key in SONG_LIBRARY:
        return SONG_LIBRARY[song_key]

    song_title = title_from_slug(song_key) or "Cancion Demo"
    return {
        "title": song_title,
        "artist": "Autor Independiente",
        "album": "Borrador",
        "tonality": "E minor",
        "bpm": 90,
        "lines": [
            {
                "lyrics": "Esta version aun esta en construccion",
                "chords": [
                    {"name": "Emin", "position": 0},
                    {"name": "Cmaj", "position": 14},
                    {"name": "Gmaj", "position": 27},
                ],
            },
            {
                "lyrics": "pero ya puedes probar acordes y estructura",
                "chords": [
                    {"name": "Amin", "position": 0},
                    {"name": "Dmaj", "position": 23},
                    {"name": "Emin", "position": 35},
                ],
            },
        ],
    }


def normalize_song_raw(raw_song: str) -> str:
    text = raw_song.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(?is)<\s*div\s*>\s*<\s*/\s*div\s*>", "\n", text)
    text = re.sub(r"(?is)<\s*a\b[^>]*>(.*?)<\s*/\s*a\s*>", r"\1", text)
    text = re.sub(r"(?is)<\s*/?\s*pre\b[^>]*>", "", text)
    text = re.sub(r"(?is)<[^>]+>", "", text)
    text = html.unescape(text)

    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

@app.route("/")
def index():
    from datetime import datetime
    return render_template("landing.html", year=datetime.now().year)


@app.route("/robots.txt")
def robots_txt():
    content = "User-agent: *\nAllow: /\nSitemap: /sitemap.xml\n"
    return Response(content, mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap_xml():
    urls = ["/", "/app", "/blog/primer-post", "/song/noche-en-seis-cuerdas"]
    xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url in urls:
        xml.append(f"<url><loc>{url}</loc></url>")
    xml.append("</urlset>")
    return Response("\n".join(xml), mimetype="application/xml")


@app.route("/song/<string:song_name>")
def song_page(song_name: str):
    return redirect(f"/app/song/{song_name}", code=302)


@app.route("/api/v1/song/<string:song_name>")
def song_data(song_name: str):
    db_song = get_cancion_by_slug(song_name)
    if db_song:
        return jsonify(
            {
                "slug": db_song["slug"],
                "title": db_song["nombre"],
                "artist": db_song["artista"],
                "album": "Catalogo Canciones",
                "tonality": "N/A",
                "bpm": 0,
                "rawSong": db_song["cancion"],
                "lines": parse_song_text_to_lines(db_song["cancion"]),
                "availableChords": sorted(CHORD_SHAPES_GUITAR.keys()),
            }
        )

    payload = build_song_payload(song_name)
    payload["slug"] = song_name
    payload["rawSong"] = ""
    payload["availableChords"] = sorted(CHORD_SHAPES_GUITAR.keys())
    return jsonify(payload)


@app.route("/admin/song/new", methods=["GET", "POST"])
def song_form():
    preview = None
    db_result = None
    error_message = ""
    form_data = {"slug": "", "nombre": "", "artista": "", "cancion_raw": ""}

    if request.method == "POST":
        form_data["slug"] = request.form.get("slug", "").strip()
        form_data["nombre"] = request.form.get("nombre", "").strip()
        form_data["artista"] = request.form.get("artista", "").strip()
        form_data["cancion_raw"] = request.form.get("cancion_raw", "")

        if not form_data["slug"] and form_data["nombre"]:
            form_data["slug"] = slugify(form_data["nombre"])

        if form_data["slug"] and form_data["nombre"] and form_data["artista"] and form_data["cancion_raw"].strip():
            preview = {
                "slug": form_data["slug"],
                "nombre": form_data["nombre"],
                "artista": form_data["artista"],
                "cancion": normalize_song_raw(form_data["cancion_raw"]),
            }
            SONG_DRAFTS.append(preview)
            try:
                db_result = insert_cancion(
                    slug=preview["slug"],
                    nombre=preview["nombre"],
                    artista=preview["artista"],
                    cancion=preview["cancion"],
                )
            except Exception as error:
                error_message = str(error)
        else:
            error_message = "Completa slug, nombre, artista y cancion."

    return render_template(
        "song_form.html",
        preview=preview,
        db_result=db_result,
        error_message=error_message,
        form_data=form_data,
        drafts_count=len(SONG_DRAFTS),
    )


@app.route("/api/v1/song-draft/latest")
def song_draft_latest():
    if not SONG_DRAFTS:
        return jsonify({"error": "No hay canciones procesadas aun"}), 404
    return jsonify(SONG_DRAFTS[-1])


@app.route("/api/v1/db/canciones/status")
def canciones_table_status():
    if DB_INIT_ERROR:
        return jsonify({"ok": False, "table": "canciones", "error": DB_INIT_ERROR}), 500

    try:
        exists = canciones_table_exists()
        return jsonify({"ok": True, "table": "canciones", "exists": exists})
    except Exception as error:
        return jsonify({"ok": False, "table": "canciones", "error": str(error)}), 500

@app.route("/api/v1/health")
def health():
    return "True"

@app.route("/api/v1/modes")
def modes():
    with open("json/modos.json", "r") as f:
        return json.load(f)

@app.route("/api/v1/notes")
def notes():
    with open("json/notes.json", "r") as f:
        return json.load(f)

@app.route("/api/v1/scales/<string:note>/<string:mode>")
def scales(note, mode):
    with open("json/scales.json", "r") as f:
        scales_data = json.load(f)
        for item in scales_data:
            if note in item:
                return item[note][mode]
    return {"error": "Scale not found"}, 404

@app.route("/api/v1/render/chord.svg")
def render_chord_svg_get():
    instrument = request.args.get("instrument", "guitar")
    name = request.args.get("name", "Chord")
    pos = request.args.get("pos")
    fret_start = int(request.args.get("fretStart", "1"))

    if not pos:
        return Response("Missing required query param: pos", status=400, mimetype="text/plain")

    try:
        positions = _parse_pos_csv(pos)
    except Exception:
        return Response("Invalid pos CSV. Example: -1,3,2,0,1,0", status=400, mimetype="text/plain")

    if instrument != "guitar":
        return Response("Unsupported instrument", status=400, mimetype="text/plain")

    try:
        svg = render_guitar_svg(name=name, positions=positions, fret_start=fret_start)
    except ValueError as e:
        return Response(str(e), status=400, mimetype="text/plain")

    et = etag_for(svg)
    resp = Response(svg, status=200, mimetype="image/svg+xml")
    resp.headers["Content-Type"] = "image/svg+xml; charset=utf-8"
    resp.headers["Cache-Control"] = "public, max-age=86400"
    resp.headers["ETag"] = et
    return resp


@app.route("/api/v1/render/chord.svg", methods=["POST"])
def render_chord_svg_post():
    payload = request.get_json(silent=True)
    if payload is None:
        return Response("Invalid JSON body", status=400, mimetype="text/plain")

    instrument = payload.get("instrument", "guitar")
    meta = payload.get("meta", {}) or {}
    diagram = payload.get("diagram", {}) or {}

    if instrument != "guitar":
        return Response("Unsupported instrument", status=400, mimetype="text/plain")

    name = meta.get("name", "Chord")
    positions = diagram.get("positions", [])
    fret_start = int(diagram.get("fretStart", 1))
    frets_visible = int(diagram.get("fretsVisible", 5))
    barres = diagram.get("barres", [])

    try:
        svg = render_guitar_svg(
            name=name,
            positions=positions,
            fret_start=fret_start,
            frets_visible=frets_visible,
            barres=barres,
        )
    except (ValueError, TypeError) as e:
        return Response(str(e), status=400, mimetype="text/plain")

    et = etag_for(svg)
    resp = Response(svg, status=200, mimetype="image/svg+xml")
    resp.headers["Cache-Control"] = "public, max-age=86400"
    resp.headers["ETag"] = et
    return resp

@app.route("/api/v1/chords/guitar/<chord>.svg")
def chord_svg_guitar(chord: str):
    shape = CHORD_SHAPES_GUITAR.get(chord)
    if not shape:
        return Response(f"Chord not found: {chord}", status=404, mimetype="text/plain")

    svg = render_guitar_svg(
        name=chord,
        positions=shape["pos"],
        fret_start=shape.get("fretStart", 1),
    )
    return Response(svg, status=200, mimetype="image/svg+xml")


@app.route("/app", defaults={"path": ""})
@app.route("/app/<path:path>")
def serve_chords_app(path: str):
    if not CHORDS_DIST_DIR.exists():
        return Response("Build not found. Run 'npm run build' inside chords.", status=404, mimetype="text/plain")

    requested_file = CHORDS_DIST_DIR / path
    if path and requested_file.exists() and requested_file.is_file():
        return send_from_directory(CHORDS_DIST_DIR, path)

    return send_from_directory(CHORDS_DIST_DIR, "index.html")


@app.route("/blog/<string:post_id>")
def get_blog_post(post_id: str):
    return jsonify(
        {
            "id": post_id,
            "title": f"Blog post {post_id}",
            "summary": "Dynamic blog endpoint ready. Replace this with DB/content lookup.",
            "url": f"/blog/{post_id}",
        }
    )
