"""
routers/reportes.py
--------------------
Endpoints para generar reportes de ventas en Excel: diario y por rango de
fechas. La lógica de armado del Excel vive en reportes.py; aquí solo se
resuelve el request HTTP.
"""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import io

from database import get_db
from reportes import generar_reporte
from routers.auth import obtener_usuario_actual

router = APIRouter(prefix="/reportes", tags=["Reportes"], dependencies=[Depends(obtener_usuario_actual)])


def _responder_excel(contenido: bytes, nombre_archivo: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(contenido),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={nombre_archivo}"},
    )


@router.get("/diario", summary="Reporte de ventas de un día específico")
def reporte_diario(fecha: date = Query(...), db: Session = Depends(get_db)):
    contenido, nombre_archivo, _resumen = generar_reporte(db, fecha, fecha)
    if contenido is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No existen ventas registradas para esta fecha.",
        )
    return _responder_excel(contenido, nombre_archivo)


@router.get("/rango", summary="Reporte de ventas por rango de fechas")
def reporte_rango(desde: date = Query(...), hasta: date = Query(...), db: Session = Depends(get_db)):
    if desde > hasta:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La fecha 'desde' no puede ser posterior a 'hasta'.")
    contenido, nombre_archivo, _resumen = generar_reporte(db, desde, hasta)
    if contenido is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No existen ventas registradas en ese rango de fechas.",
        )
    return _responder_excel(contenido, nombre_archivo)


@router.get("/resumen", summary="Resumen numérico de un periodo (sin generar el Excel)")
def resumen_periodo(desde: date = Query(...), hasta: date = Query(...), db: Session = Depends(get_db)):
    _contenido, _nombre, resumen = generar_reporte(db, desde, hasta)
    if not resumen:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existen ventas registradas en ese rango de fechas.")
    return resumen
