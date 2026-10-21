#!/usr/bin/env python3
"""
update_stats.py - Actualiza las estadísticas de actividad y el logbook
de búsqueda en index.html usando la API de QRZ Logbook.

Uso:
    export QRZ_API_KEY=...   # en tu terminal, sin guardarla en archivos
    python3 update_stats.py
    (alternativa: python3 update_stats.py --api-key ...)

Para obtener tu API key:
    1. Ingresa a https://logbook.qrz.com/logbook
    2. Click en "Settings"
    3. Copia tu "API Key"

El script:
    - Descarga todos tus QSOs desde QRZ
    - Calcula: total QSOs, países, bandas, modos
    - Actualiza los números en index.html
    - Actualiza el diccionario JS del buscador "¿Estás en mi log?"
"""

import argparse
import os
import re
import sys
import urllib.request
import urllib.parse


def fetch_qsos(api_key):
    """Descarga todos los QSOs desde la API de QRZ Logbook."""
    url = "https://logbook.qrz.com/api"
    params = urllib.parse.urlencode({
        "KEY": api_key,
        "ACTION": "FETCH",
        "OPTION": "ALL"
    })
    req = urllib.request.Request(url, data=params.encode("utf-8"), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"Error conectando a QRZ: {e}")
        sys.exit(1)


def parse_adif(raw):
    """Parsea la respuesta de QRZ que contiene ADIF y extrae los QSOs."""
    # La respuesta de QRZ tiene formato: RESULT=OK&LOGIDS=...&ADIF=<adif data>&...
    # o puede ser un error
    if "RESULT=FAIL" in raw:
        reason = re.search(r"REASON=([^&]+)", raw)
        msg = reason.group(1) if reason else "desconocido"
        print(f"Error de QRZ: {msg}")
        sys.exit(1)

    # Extraer la parte ADIF
    adif_match = re.search(r"ADIF=(.*)", raw, re.DOTALL)
    if not adif_match:
        # Tal vez la respuesta ES el ADIF directamente
        adif_data = raw
    else:
        adif_data = urllib.parse.unquote(adif_match.group(1))

    # Parsear registros ADIF
    qsos = []
    # Cada QSO termina con <eor> (end of record)
    records = re.split(r"<eor>", adif_data, flags=re.IGNORECASE)

    for record in records:
        if not record.strip():
            continue
        qso = {}
        # Extraer campos ADIF: <FIELD:length>value
        fields = re.findall(r"<(\w+):(\d+)(?::\w+)?>([^<]*)", record, re.IGNORECASE)
        for name, length, value in fields:
            qso[name.upper()] = value[:int(length)].strip()
        if qso:
            qsos.append(qso)

    return qsos


def compute_stats(qsos):
    """Calcula estadísticas a partir de los QSOs."""
    total = len(qsos)
    countries = set()
    bands = set()
    modes = set()

    for qso in qsos:
        # País: puede estar en COUNTRY o DXCC
        country = qso.get("COUNTRY", "") or qso.get("DXCC", "")
        if country:
            countries.add(country)

        band = qso.get("BAND", "")
        if band:
            bands.add(band.lower())

        mode = qso.get("MODE", "")
        if mode:
            modes.add(mode.upper())

    return {
        "total": total,
        "countries": len(countries),
        "bands": len(bands),
        "modes": len(modes),
        "country_list": sorted(countries),
        "band_list": sorted(bands),
        "mode_list": sorted(modes),
    }


def build_logbook_csv(qsos):
    """Genera el contenido del archivo CSV para el buscador de logbook."""
    lines = ["indicativo,fecha,banda,modo"]
    for qso in qsos:
        call = qso.get("CALL", "").upper()
        if not call:
            continue
        date = qso.get("QSO_DATE", "")
        if len(date) == 8:
            date = f"{date[6:8]}/{date[4:6]}/{date[0:4]}"
        band = qso.get("BAND", "?")
        mode = qso.get("MODE", "?")
        lines.append(f"{call},{date},{band},{mode}")
    return "\n".join(lines) + "\n"


def update_html(stats):
    """Actualiza index.html con las nuevas estadísticas."""
    with open("index.html", "r", encoding="utf-8") as f:
        html = f.read()

    # Actualizar stat-number values
    # Patron: stat-icon > stat-number > stat-label
    # Reemplazar por label
    replacements = {
        "QSOs Totales": str(stats["total"]),
        "Países": str(stats["countries"]),
        "Bandas": str(stats["bands"]),
        "Modos": str(stats["modes"]),
    }

    for label, value in replacements.items():
        # Busca: <div class="stat-number">NUMERO</div>\n...<div class="stat-label">LABEL</div>
        pattern = r'(<div class="stat-number">)\d+(</div>\s*<div class="stat-label">' + re.escape(label) + r")"
        replacement = r"\g<1>" + value + r"\g<2>"
        html, count = re.subn(pattern, replacement, html)
        if count:
            print(f"  ✓ {label}: {value}")
        else:
            print(f"  ✗ No se encontró '{label}' en el HTML")

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)


def update_logbook_csv(csv_content):
    """Escribe el archivo data/logbook.csv."""
    os.makedirs("data", exist_ok=True)
    with open("data/logbook.csv", "w", encoding="utf-8") as f:
        f.write(csv_content)


def main():
    parser = argparse.ArgumentParser(
        description="Actualiza estadísticas en index.html desde QRZ Logbook"
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("QRZ_API_KEY"),
        help="Tu API Key de QRZ Logbook (Settings > API Key). "
             "Por defecto se lee de la variable de entorno QRZ_API_KEY"
    )
    args = parser.parse_args()
    if not args.api_key:
        parser.error("falta la API key: definí QRZ_API_KEY o usá --api-key")

    print("📡 Descargando QSOs desde QRZ...")
    raw = fetch_qsos(args.api_key)

    print("📋 Parseando ADIF...")
    qsos = parse_adif(raw)

    if not qsos:
        print("⚠️  No se encontraron QSOs. Verifica tu API key.")
        sys.exit(1)

    print(f"📊 Calculando estadísticas de {len(qsos)} QSOs...")
    stats = compute_stats(qsos)

    print(f"\n--- Resumen ---")
    print(f"  QSOs totales: {stats['total']}")
    print(f"  Países: {stats['countries']} ({', '.join(stats['country_list'])})")
    print(f"  Bandas: {stats['bands']} ({', '.join(stats['band_list'])})")
    print(f"  Modos: {stats['modes']} ({', '.join(stats['mode_list'])})")

    print(f"\n✏️  Actualizando index.html...")
    update_html(stats)

    print("✏️  Actualizando data/logbook.csv...")
    csv_content = build_logbook_csv(qsos)
    update_logbook_csv(csv_content)
    print(f"  ✓ {len(qsos)} QSOs escritos en data/logbook.csv")

    print("\n✅ Listo. Hace commit y push para actualizar la web.")


if __name__ == "__main__":
    main()
