QUERY_LLAMADAS_NORMALIZADAS = """
SELECT
    linkedid,
    fecha_inicio,
    numero_origen,
    destino_inicial,
    paso_por_cola,
    nombre_cola,
    extension_agente,
    nombre_agente,
    tiempo_conversacion,
    tiempo_timbrado,
    estado_final
FROM vw_llamadas_normalizadas
WHERE fecha_inicio >= %s
LIMIT 5000
"""

QUERY_COLAS_RESUMEN = """
SELECT * FROM vw_colas_estadisticas
"""

QUERY_AGENTES_RESUMEN = """
SELECT * FROM vw_estadisticas_agentes_general
"""

QUERY_ESTADISTICAS_COLAS = """
SELECT
    linkedid,
    numero_cola,
    fecha_entrada,
    estado_final,
    caller_id,
    agente_asignado,
    espera_seg,
    duracion_seg
FROM vw_estadisticas_colas
WHERE fecha_entrada >= %s
LIMIT 5000
"""

QUERY_LLAMADAS_REAL = """
SELECT
    linkedid,
    fecha_inicio,
    fecha_fin,
    total_segmentos,
    duracion_total,
    tiempo_total_conversacion
FROM vw_llamadas_real
WHERE fecha_inicio >= %s
LIMIT 5000
"""
