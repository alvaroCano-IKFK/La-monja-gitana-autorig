"""
progress_module.py

Helper de barra de progreso para el autorig.
Uso pensado para envolver la construccion de modulos en build_module.

Autor: para el autorig modular de Alvaro
"""

from contextlib import contextmanager

import maya.cmds as cmds
import maya.mel as mel


class ProgressCancelled(Exception):
    """Se lanza cuando el usuario cancela la construccion desde la barra."""
    pass


class RigProgress(object):
    """
    Barra de progreso para procesos largos en Maya.

    Parametros
    ----------
    title : str
        Titulo de la ventana (solo modo 'window').
    total : int
        Numero total de pasos.
    mode : str
        'window' -> ventana flotante con boton de cancelar.
        'main'   -> barra del Help Line (no roba el foco).
    interruptable : bool
        Permite cancelar con ESC / boton Cancel.
    refresh_ui : bool
        Fuerza cmds.refresh() en cada step. Necesario para ver la barra
        moverse, pero tiene coste. Desactivalo si haces steps muy seguidos.
    """

    def __init__(self, title="Building rig", total=100, mode="window",
                 interruptable=True, refresh_ui=True):
        self.title = title
        self.total = max(int(total), 1)
        self.mode = mode
        self.interruptable = interruptable
        self.refresh_ui = refresh_ui

        self.current = 0
        self._started = False
        self._main_bar = None

        # Si Maya corre en batch no hay UI, desactivamos todo.
        self.enabled = not cmds.about(batch=True)

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    def start(self, status="Iniciando..."):
        if not self.enabled or self._started:
            return

        # Nos aseguramos de que no haya ninguna barra huerfana abierta.
        self.force_close()

        if self.mode == "main":
            self._main_bar = mel.eval('$tmp = $gMainProgressBar')
            cmds.progressBar(self._main_bar, edit=True,
                             beginProgress=True,
                             isInterruptable=self.interruptable,
                             status=status,
                             minValue=0,
                             maxValue=self.total)
        else:
            cmds.progressWindow(title=self.title,
                                progress=0,
                                status=status,
                                isInterruptable=self.interruptable,
                                minValue=0,
                                maxValue=self.total)

        self._started = True

    def step(self, status=None, amount=1):
        """Avanza la barra. Lanza ProgressCancelled si el usuario cancela."""
        if not self.enabled or not self._started:
            return

        if self.is_cancelled():
            raise ProgressCancelled("Construccion cancelada por el usuario.")

        self.current = min(self.current + amount, self.total)

        kwargs = {"edit": True, "progress": self.current}
        if status:
            # Mostramos tambien el contador, ayuda mucho a ver que no se ha colgado.
            kwargs["status"] = "{0}  ({1}/{2})".format(status, self.current, self.total)

        if self.mode == "main":
            cmds.progressBar(self._main_bar, **kwargs)
        else:
            cmds.progressWindow(**kwargs)

        if self.refresh_ui:
            cmds.refresh()

    def set_status(self, status):
        """Cambia el texto sin avanzar la barra."""
        if not self.enabled or not self._started:
            return

        if self.mode == "main":
            cmds.progressBar(self._main_bar, edit=True, status=status)
        else:
            cmds.progressWindow(edit=True, status=status)

        if self.refresh_ui:
            cmds.refresh()

    def is_cancelled(self):
        if not self.enabled or not self._started or not self.interruptable:
            return False

        if self.mode == "main":
            return cmds.progressBar(self._main_bar, query=True, isCancelled=True)
        return cmds.progressWindow(query=True, isCancelled=True)

    def end(self):
        if not self.enabled or not self._started:
            return

        if self.mode == "main":
            cmds.progressBar(self._main_bar, edit=True, endProgress=True)
        else:
            cmds.progressWindow(endProgress=True)

        self._started = False

    # ------------------------------------------------------------------
    # Utilidad de rescate
    # ------------------------------------------------------------------
    @staticmethod
    def force_close():
        """
        Cierra cualquier barra que se haya quedado colgada por un error.
        Llamalo desde el Script Editor si Maya se queda bloqueado.
        """
        try:
            cmds.progressWindow(endProgress=True)
        except Exception:
            pass
        try:
            bar = mel.eval('$tmp = $gMainProgressBar')
            cmds.progressBar(bar, edit=True, endProgress=True)
        except Exception:
            pass


# ----------------------------------------------------------------------
# Context manager: la forma comoda de usarlo
# ----------------------------------------------------------------------
@contextmanager
def rig_progress(title="Building rig", total=100, mode="window",
                 undo_chunk=True, **kwargs):
    """
    Envuelve un bloque de construccion con barra de progreso y,
    opcionalmente, un unico chunk de undo.

    Ejemplo:
        with rig_progress("Autorig", total=6) as prog:
            prog.step("Root")
            ...
    """
    prog = RigProgress(title=title, total=total, mode=mode, **kwargs)
    prog.start()

    if undo_chunk:
        cmds.undoInfo(openChunk=True, chunkName=title)

    try:
        yield prog
    except ProgressCancelled:
        cmds.warning("Construccion cancelada. Deshaz con Ctrl+Z si hace falta.")
    finally:
        # El finally es CRITICO: si un modulo peta, la barra debe cerrarse igual.
        if undo_chunk:
            cmds.undoInfo(closeChunk=True)
        prog.end()


# ----------------------------------------------------------------------
# Ejemplo de integracion en build_module
# ----------------------------------------------------------------------
if __name__ == "__main__":

    # Lista de (etiqueta, callable) para construir el rig paso a paso.
    # En tu build_module real esto serian tus instancias de modulo.
    steps = [
        ("Root y jerarquia base", lambda: None),
        ("Columna y cuello",      lambda: None),
        ("Brazo izquierdo",       lambda: None),
        ("Brazo derecho",         lambda: None),
        ("Pierna izquierda",      lambda: None),
        ("Pierna derecha",        lambda: None),
        ("Dedos",                 lambda: None),
        ("Twist y curvature",     lambda: None),
        ("Soft IK",               lambda: None),
        ("Rig facial",            lambda: None),
        ("Skinning",              lambda: None),
    ]

    with rig_progress("La monja gitana autorig", total=len(steps)) as prog:
        for label, func in steps:
            prog.step(label)   # texto ANTES de ejecutar: se ve lo que esta haciendo
            func()