"""Estrategias de reintento para operaciones fallidas.

Implementa algoritmos de backoff exponencial con jitter
y una estrategia sin reintento para operaciones que no
deben repetirse.
"""

# Habilitar evaluacion diferida de type hints (Python 3.7+)
from __future__ import annotations

# Generacion de valores aleatorios para jitter en backoff
import random
# Tipos para firmas de metodos con type hints
from typing import Optional

# Interfaz abstracta que estas clases implementan
from src.strategies.base import EstrategiaReintento


class BackoffExponencial(EstrategiaReintento):
    """Estrategia de reintento con backoff exponencial y jitter.

    Incrementa el tiempo de espera exponencialmente en cada
    intento, anadiendo un factor aleatorio (jitter) para
    evitar tormentas de reintentos simultaneos.

    Args:
        demora_inicial: Tiempo base de espera en segundos.
        demora_maxima: Tiempo maximo de espera en segundos.
        factor_multiplicador: Factor de crecimiento exponencial.
    """

    def __init__(
        self,
        demora_inicial: float = 1.0,
        demora_maxima: float = 60.0,
        factor_multiplicador: float = 2.0,
    ) -> None:
        # Tiempo de espera base para el primer reintento
        self.demora_inicial = demora_inicial
        # Tiempo maximo de espera (techo para evitar esperas infinitas)
        self.demora_maxima = demora_maxima
        # Factor multiplicador: cada intento espera factor veces mas
        self.factor = factor_multiplicador

    def calcular_demora(self, intento: int) -> float:
        """Calcula la demora para el intento actual.

        Usa la formula: min(demora_inicial * factor^intento, demora_maxima)
        mas un jitter aleatorio de +/- 25%.

        Args:
            intento: Numero de intento actual (1-based).

        Returns:
            Tiempo de espera en segundos para este intento.
        """
        demora_base = self.demora_inicial * (self.factor ** (intento - 1))
        demora_limitada = min(demora_base, self.demora_maxima)

        jitter = demora_limitada * random.uniform(-0.25, 0.25)
        demora_final = max(0.1, demora_limitada + jitter)

        return demora_final


class SinReintento(EstrategiaReintento):
    """Estrategia que no reintenta operaciones fallidas.

    Util para operaciones que no deben repetirse
    o cuando se quiere fallar rapidamente.
    """

    def calcular_demora(self, intento: int) -> float:
        """Retorna 0, indicando que no se debe reintentar.

        Args:
            intento: Numero de intento (ignorado).

        Returns:
            Siempre 0.
        """
        return 0.0
