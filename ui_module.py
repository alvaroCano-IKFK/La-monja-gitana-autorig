import maya.cmds as cmds
from functools import partial 
import os
import math
import json
import guides_module
import spine_module
import limbs_module
import reorient_module
import mirror_module
import build_module
import eyes_module
import guides_io_module


class UI(object):

    def __init__(self, name="AutoRig_Master"):
        self.name = name
        self.character = guides_module.CharacterGuides()
        self.reorienter = reorient_module.Reorienter()
        self.mirror_guides = mirror_module.Mirror()
        self.builder = build_module.BuildRig()

        # Campos de la seccion de curvas de loop, para leerlos desde los botones
        self.rig_name_field = None
        self.side_menu = None
        self.inner_reference_field = None

    def main_UI(self):
        window_name = self.name
        if cmds.window(window_name, exists=True):
            cmds.deleteUI(window_name)

        win = cmds.window(window_name, title="AutoRig Master", w=300)
        main_layout = cmds.columnLayout(adj=True)

        # ------------------------------------------------------------------
        # 1. GUIAS
        # ------------------------------------------------------------------
        cmds.frameLayout(l="1. Create Guides", collapsable=True, cl=True, marginHeight=5)
        cmds.columnLayout(adj=True)
        cmds.button(l="Guides", c=lambda x: self.character.create_guides(), h=40)
        cmds.setParent(main_layout)

        # ------------------------------------------------------------------
        # 2. DATA MANAGEMENT
        # ------------------------------------------------------------------
        cmds.frameLayout(l="2. Data Management", collapsable=True, cl=True, marginHeight=5)
        cmds.columnLayout(adj=True)
        cmds.button(l="Export Guides", c=lambda x: self._export_guides())
        cmds.separator(h=10)
        cmds.button(l="Import Guides", c=lambda x: self._import_guides())
        cmds.separator(h=10)
        cmds.button(l="Mirror", c=lambda x: self.mirror_guides.mirror())
        cmds.setParent(main_layout)

        # ------------------------------------------------------------------
        # 3. CURVAS DE LOOP DE LOS OJOS
        #
        # Sustituye a la antigua seccion de sets. El artefacto que se guarda ya
        # no es un objectSet con indices de vertice, sino una curva de grado 1
        # con un CV por vertice del borde del parpado. Se crea una vez por
        # parpado y por lado, se queda en la escena y de ella sale todo lo
        # demas: la linea del parpado y los joints de loop.
        # ------------------------------------------------------------------
        cmds.frameLayout(l="3. Eye Loop Curves", collapsable=True, cl=True, marginHeight=5)
        cmds.columnLayout(adj=True)

        self.rig_name_field = cmds.textFieldGrp(
            l="Rig Name", tx="Character", cw2=(70, 150), adj=2)

        self.side_menu = cmds.optionMenuGrp(l="Side", cw2=(70, 150))
        cmds.menuItem(l="L")
        cmds.menuItem(l="R")

        cmds.separator(h=8)
        cmds.text(l="Selecciona el edge loop del borde del parpado:", al="left")
        cmds.button(l="Create Upper Loop Curve",
                    c=lambda x: self._build_loop_curve(upper=True))
        cmds.separator(h=4)
        cmds.button(l="Create Lower Loop Curve",
                    c=lambda x: self._build_loop_curve(upper=False))

        cmds.separator(h=8)
        # Opcional: nodo del centro de la cara para decidir cual de los dos
        # extremos del loop es la comisura interna. Vacio = se usa la X mundial
        # 0, que vale si el personaje esta centrado en el origen.
        self.inner_reference_field = cmds.textFieldButtonGrp(
            l="Inner Ref", tx="", bl="<< Sel", cw3=(70, 120, 50), adj=2,
            bc=lambda: self._set_inner_reference_from_selection())
        cmds.text(l="(opcional: nodo del centro de la cara)", al="left")

        cmds.separator(h=8)
        cmds.button(l="Check Loop Curves", c=lambda x: self._report_loop_curves())
        cmds.separator(h=4)
        cmds.rowLayout(nc=2, cw2=(150, 150), adj=1)
        cmds.button(l="Diagnose Upper",
                    c=lambda x: self._diagnose_loop_curve(upper=True))
        cmds.button(l="Diagnose Lower",
                    c=lambda x: self._diagnose_loop_curve(upper=False))
        cmds.setParent("..")

        cmds.setParent(main_layout)

        # ------------------------------------------------------------------
        # 4. BUILD
        # ------------------------------------------------------------------
        cmds.frameLayout(l="4. Build Rig", collapsable=True, cl=True, marginHeight=5)
        cmds.columnLayout(adj=True)
        cmds.button(l="BUILD", c=lambda x: self.builder.build(),
                    bgc=(0.3, 0.5, 0.3), h=40)
        cmds.setParent(main_layout)

        cmds.showWindow(win)

    # ------------------------------------------------------------------
    # EXPORT / IMPORT DE GUIAS
    # ------------------------------------------------------------------
    def _export_guides(self):
        """
        Vuelca guides_GRP entero a un JSON. El propio modulo abre el file
        dialog, aqui no se decide la ruta.
        """

        return guides_io_module.export_guides()

    def _import_guides(self):
        """
        Reconstruye las guias desde un JSON. Si ya hay guias en la escena el
        modulo pregunta antes de borrarlas.
        """

        return guides_io_module.import_guides()

    # ------------------------------------------------------------------
    # CURVAS DE LOOP DE LOS OJOS
    # ------------------------------------------------------------------
    def _get_eye_naming(self):
        """
        Lado y nombre de rig que hay puestos en la ventana. Son solo para
        construir el nombre de la curva: la configuracion del build sigue
        viviendo en build_module, aqui no se guarda nada.
        """
        rig_name = cmds.textFieldGrp(self.rig_name_field, q=True, tx=True) or "Character"
        side = cmds.optionMenuGrp(self.side_menu, q=True, v=True) or "L"

        return side, rig_name.strip()

    def _get_inner_reference(self):
        """
        Nodo de referencia del centro de la cara, o None si el campo esta vacio
        o apunta a algo que ya no existe.
        """
        value = cmds.textFieldButtonGrp(self.inner_reference_field, q=True, tx=True) or ""
        value = value.strip()

        if not value:
            return None

        if not cmds.objExists(value):
            cmds.warning(f"[UI] '{value}' no existe en la escena. Se ignora la "
                         f"referencia y se usa la X mundial 0.")
            return None

        return value

    def _set_inner_reference_from_selection(self):
        """
        Mete en el campo el primer nodo seleccionado, para no escribir el
        nombre a mano.
        """
        selection = cmds.ls(selection=True, long=False) or []

        # Un componente no vale como referencia: hace falta un transform.
        selection = [item for item in selection if "." not in item]
        if not selection:
            cmds.warning("[UI] Selecciona un nodo del centro de la cara.")
            return None

        cmds.textFieldButtonGrp(self.inner_reference_field, e=True, tx=selection[0])

        return selection[0]

    def _build_loop_curve(self, upper=True):
        """
        Crea la curva de loop del parpado a partir del edge seleccionado, con
        el nombre de convencion para que el modulo la encuentre sola.
        """
        side, rig_name = self._get_eye_naming()

        return eyes_module.EyesModule.build_loop_curve_from_selection(
            side, rig_name, upper=upper,
            inner_reference=self._get_inner_reference()
        )

    def _report_loop_curves(self):
        """
        Imprime que curvas de loop hay y cuantos joints saldrian, sin construir
        nada.
        """
        side, rig_name = self._get_eye_naming()

        return eyes_module.EyesModule.report_loop_curves(side, rig_name)

    def _diagnose_loop_curve(self, upper=True):
        """
        Imprime, CV a CV, donde cae sobre la linea del parpado y a que
        distancia. Necesita el rig ya construido: la linea no existe antes.
        """
        side, rig_name = self._get_eye_naming()

        return eyes_module.EyesModule.diagnose_loop_curve(side, rig_name, upper=upper)


if __name__ == "__main__":
    ui_instance = UI()
    ui_instance.main_UI()