"""Normaliza las cabeceras de los .po a UTF-8 limpio.

Uso:
    python normalizar_po.py [ruta_a_locales]

Se llama desde build_i18n.bat antes de compilar los .mo. Conserva todos los
msgid/msgstr y solo reconstruye el bloque de cabecera, que es donde se estaba
introduciendo texto corrupto (charset=*UTF-8, Language: \u00e9s, etc.).
"""
from pathlib import Path
import sys

BASE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "locales"


def cabecera_limpia(idioma: str) -> list[str]:
    return [
        'msgid ""',
        'msgstr ""',
        '"Project-Id-Version: PACKAGE VERSION\\n"',
        f'"Language: {idioma}\\n"',
        '"MIME-Version: 1.0\\n"',
        '"Content-Type: text/plain; charset=UTF-8\\n"',
        '"Content-Transfer-Encoding: 8bit\\n"',
        '"Generated-By: pygettext.py 1.5\\n"',
        "",
    ]


def normalizar(ruta: Path) -> bool:
    crudo = ruta.read_bytes()
    try:
        texto = crudo.decode("utf-8")
    except UnicodeDecodeError:
        texto = crudo.decode("cp1252")

    lineas = texto.replace("\r\n", "\n").split("\n")
    idioma = ruta.parent.parent.name or "es"

    try:
        inicio = next(i for i, linea in enumerate(lineas) if linea.strip() == 'msgid ""')
    except StopIteration:
        texto_nuevo = texto.replace("charset=cp1252", "charset=UTF-8")
        return escribir_si_cambia(ruta, crudo, texto_nuevo)

    fin_msgstr = next(
        (i for i in range(inicio + 1, len(lineas))
         if lineas[i].strip().startswith('msgstr ""')),
        None,
    )
    if fin_msgstr is None:
        return False

    fin = fin_msgstr + 1
    while fin < len(lineas) and lineas[fin].lstrip().startswith('"'):
        fin += 1

    nuevo = "\n".join(lineas[:inicio] + cabecera_limpia(idioma) + lineas[fin:])
    if not nuevo.endswith("\n"):
        nuevo += "\n"
    return escribir_si_cambia(ruta, crudo, nuevo)


def escribir_si_cambia(ruta: Path, crudo: bytes, texto: str) -> bool:
    datos = texto.encode("utf-8")
    if datos == crudo:
        return False
    ruta.write_bytes(datos)
    return True


def main() -> None:
    if not BASE.is_dir():
        print(f"No existe {BASE}")
        return
    for po in sorted(BASE.glob("*/LC_MESSAGES/dialogs*.po")):
        if normalizar(po):
            print(f"Normalizado: {po}")
        else:
            print(f"OK: {po}")


if __name__ == "__main__":
    main()
