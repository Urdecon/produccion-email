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

def build_payload_from_excel(fp: Path) -> dict:
    """
    Lee tu plantilla:
      - Hoja 'Inicio': Mes_Clave (auto), Empresa, Proyecto
      - 'Produccion': A..F
      - 'Pendientes': A..F
    """
    # --- Inicio ---
    ws_ini = pd.read_excel(fp, sheet_name="Inicio", header=None, dtype="object")
    # buscar etiquetas en col A
    def _find_right(label: str) -> str:
        rows = ws_ini[ws_ini.iloc[:, 0].astype(str).str.strip() == label]
        if rows.empty:
            return ""
        row_idx = rows.index[0]
        return str(ws_ini.iloc[row_idx, 1]) if ws_ini.shape[1] > 1 else ""
    mes_clave = _find_right("Mes_Clave (auto)")
    empresa = _find_right("Empresa")
    proyecto = _find_right("Proyecto")
    fecha_seguimiento = _first_of_month_str(mes_clave)

    # --- Produccion ---
    cols_seg = ["Mes", "Capitulo", "Capitulo_Cod", "Certificacion", "RestoProd", "Observaciones"]
    try:
        seg = pd.read_excel(fp, sheet_name="Produccion", header=0, dtype="object")
        # Normalizar nombres por posición por si cambian encabezados
        seg = seg.iloc[:, :6]
        seg.columns = cols_seg
        seg = seg[seg["Capitulo"].astype(str).str.strip() != ""].copy()
        seg["fecha_produccion"] = seg["Mes"].map(_first_of_month_str)
        seg["certificacion_pendiente"] = seg["Certificacion"].map(_norm_num)
        seg["resto_produccion"] = seg["RestoProd"].map(_norm_num)
        seguimiento = [
            {
                "fecha_produccion": r["fecha_produccion"],
                "capitulo": str(r["Capitulo"]) if r["Capitulo"] is not None else "",
                "capitulo_codigo": str(r["Capitulo_Cod"]) if r["Capitulo_Cod"] is not None else "",
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
                "capitulo": str(r["Capitulo"]) if r["Capitulo"] is not None else "",
                "capitulo_codigo": str(r["Capitulo_Cod"]) if r["Capitulo_Cod"] is not None else "",
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
                "fecha_seguimiento": fecha_seguimiento,
                "empresa": "" if empresa is None else str(empresa),
                "proyecto": "" if proyecto is None else str(proyecto),
            },
            "seguimiento": seguimiento,
            "pendientes": pendientes,
        },
    }
    return payload
