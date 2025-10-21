# application/services/excel_to_payload.py
from __future__ import annotations
from pathlib import Path
import pandas as pd

def _norm_num(x: str | float | int | None) -> float | None:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    if s == "":
        return None
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None

def _first_of_month_str(ym: str) -> str:
    # ym = "YYYY-MM" -> "01/MM/YYYY"
    s = str(ym).strip()
    if len(s) >= 7 and s[4] == "-":
        y = int(s[:4]); m = int(s[5:7])
        return f"01/{m:02d}/{y:04d}"
    # fallback: devolver tal cual
    return s

def _find_to_the_right(ws_ini: pd.DataFrame, label: str) -> str:
    """
    Busca 'label' en cualquier columna de la hoja 'Inicio' y devuelve el valor de la celda a la derecha.
    - Coincidencia exacta tras strip (sensibilidad normal; en tu plantilla coincide tal cual).
    - Si el label está en la última columna, devuelve "".
    """
    # Normalizamos a strings para comparar
    df = ws_ini.fillna("").astype(str)
    # Recorremos todas las celdas buscando el label
    for r in range(df.shape[0]):
        for c in range(df.shape[1]):
            if df.iat[r, c].strip() == label:
                # celda a la derecha
                if c + 1 < df.shape[1]:
                    return str(ws_ini.iat[r, c + 1])
                return ""
    # No encontrado
    return ""

def build_payload_from_excel(fp: Path) -> dict:
    """
    Lee tu plantilla:
      - Hoja 'Inicio':
            · Mes_Clave (auto)  → valor a la derecha (p.ej. F6)
            · Empresa           → valor a la derecha (p.ej. F7)
            · Proyecto          → valor a la derecha (p.ej. B8)
      - 'Produccion': A..F (posición)
      - 'Pendientes': A..F (posición)
    """
    # --- Inicio (sin encabezados, para poder buscar por etiqueta) ---
    ws_ini = pd.read_excel(fp, sheet_name="Inicio", header=None, dtype="object")

    mes_clave = _find_to_the_right(ws_ini, "Mes_Clave (auto)")
    empresa = _find_to_the_right(ws_ini, "Empresa")
    proyecto = _find_to_the_right(ws_ini, "Proyecto")

    fecha_seguimiento = _first_of_month_str(mes_clave)

    # --- Produccion ---
    cols_seg = ["Mes", "Capitulo", "Capitulo_Cod", "Certificacion", "RestoProd", "Observaciones"]
    try:
        seg = pd.read_excel(fp, sheet_name="Produccion", header=0, dtype="object")
        # Normalizar por posición (primeras 6 columnas)
        seg = seg.iloc[:, :6]
        seg.columns = cols_seg
        seg = seg[seg["Capitulo"].astype(str).str.strip() != ""].copy()
        seg["fecha_produccion"] = seg["Mes"].map(_first_of_month_str)
        seg["certificacion_pendiente"] = seg["Certificacion"].map(_norm_num)
        seg["resto_produccion"] = seg["RestoProd"].map(_norm_num)
        seguimiento = [
            {
                "fecha_produccion": r["fecha_produccion"],
                "capitulo": "" if pd.isna(r["Capitulo"]) else str(r["Capitulo"]),
                "capitulo_codigo": "" if pd.isna(r["Capitulo_Cod"]) else str(r["Capitulo_Cod"]),
                "certificacion_pendiente": r["certificacion_pendiente"],
                "resto_produccion": r["resto_produccion"],
                "observaciones": "" if pd.isna(r["Observaciones"]) else str(r["Observaciones"]),
            }
            for _, r in seg.iterrows()
        ]
    except Exception:
        seguimiento = []

    # --- Pendientes ---
    cols_pen = ["Mes", "Capitulo", "Capitulo_Cod", "Proveedor", "CostePend", "Observaciones"]
    try:
        pen = pd.read_excel(fp, sheet_name="Pendientes", header=0, dtype="object")
        pen = pen.iloc[:, :6]
        pen.columns = cols_pen
        pen = pen[pen["Capitulo"].astype(str).str.strip() != ""].copy()
        pen["fecha_produccion"] = pen["Mes"].map(_first_of_month_str)
        pen["coste_pendiente"] = pen["CostePend"].map(_norm_num)
        pendientes = [
            {
                "fecha_produccion": r["fecha_produccion"],
                "capitulo": "" if pd.isna(r["Capitulo"]) else str(r["Capitulo"]),
                "capitulo_codigo": "" if pd.isna(r["Capitulo_Cod"]) else str(r["Capitulo_Cod"]),
                "proveedor": "" if pd.isna(r["Proveedor"]) else str(r["Proveedor"]),
                "coste_pendiente": r["coste_pendiente"],
                "observaciones": "" if pd.isna(r["Observaciones"]) else str(r["Observaciones"]),
            }
            for _, r in pen.iterrows()
        ]
    except Exception:
        pendientes = []

    payload = {
        "selected_cases": ["seguimiento", "pendientes"],
        "payload": {
            "header": {
                "fecha_seguimiento": "" if fecha_seguimiento is None else str(fecha_seguimiento).strip(),
                "empresa": "" if empresa is None else str(empresa).strip(),
                "proyecto": "" if proyecto is None else str(proyecto).strip(),
            },
            "seguimiento": seguimiento,
            "pendientes": pendientes,
        },
    }
    return payload
