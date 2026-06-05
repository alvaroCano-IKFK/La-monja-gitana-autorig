import maya.cmds as cmds
from functools import partial 
import os
import math
import json
import guides_module
import limbs_module
import leg_module
from nodeCreator_module import NodeCreator

class CurvatureModule(NodeCreator):
    def __init__(self, name, side, guide_data, root_instance=None):
        self.guide_data    = guide_data
        self.name          = name
        self.side          = side
        self.root_instance = root_instance

        self.start_joint   = None
        self.mid_joint     = None
        self.end_joint     = None

        self.linear_curve  = None
        self.bezier_curve  = None
        self.degree2_curve = None

        # Curvas de segmento generadas por create_twist_curves
        # El TwistModule las consume directamente
        self.upper_curve   = None
        self.lower_curve   = None
        
        self.tangent_locators = []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_shape(self, transform):
        shapes = cmds.listRelatives(transform, shapes=True, fullPath=True) or []
        if not shapes:
            cmds.error(f"[CurvatureModule] No shape found under '{transform}'")
        return shapes[0]

    def _get_cv_positions(self, curve):
        """Devuelve todas las posiciones de CVs de una curva como lista de listas."""
        shape = self._get_shape(curve)
        num_cvs = cmds.getAttr(f"{shape}.spans") + cmds.getAttr(f"{shape}.degree")
        return [cmds.xform(f"{curve}.cv[{i}]", q=True, ws=True, t=True) for i in range(num_cvs)]

    # ------------------------------------------------------------------
    # Creación principal
    # ------------------------------------------------------------------
    def create_basic_curve(self, start_joint, mid_joint, end_joint, switch_control=None):
        self.start_joint    = start_joint
        self.mid_joint      = mid_joint
        self.end_joint      = end_joint
        self.switch_control = switch_control

        pos_start = cmds.xform(start_joint, q=True, ws=True, t=True)
        pos_mid   = cmds.xform(mid_joint,   q=True, ws=True, t=True)
        pos_end   = cmds.xform(end_joint,   q=True, ws=True, t=True)

        # ==============================================================
        # 1. CURVA LINEAR
        # ==============================================================
        raw = cmds.curve(degree=1, p=[pos_start, pos_mid, pos_end])
        self.linear_curve = cmds.rename(raw, f"{self.side}_{self.name}_linear_CRV")
        print(f"[CurvatureModule] Linear:  '{self.linear_curve}'")

        # ==============================================================
        # 2. CURVA BEZIER
        # ==============================================================
        self.bezier_curve = self._create_bezier_from_linear()
        print(f"[CurvatureModule] Bezier:  '{self.bezier_curve}'")

        # ==============================================================
        # 3. CURVA DEGREE-2
        # ==============================================================
        self.degree2_curve = self._create_degree2_from_linear()
        print(f"[CurvatureModule] Degree2: '{self.degree2_curve}'")

        # ==============================================================
        # 4. DETACH → upper_curve + lower_curve (para el TwistModule)
        #    La degree2_curve original se conserva con keepOriginal=True
        # ==============================================================
        self._create_twist_curves()

        # ==============================================================
        # 5. LOCATORS EN TANGENTES BEZIER
        # ==============================================================
        self.tangent_locators = self.create_locators_at_bezier_tangents(
            self.bezier_curve, only_elbow_tangents=True
        )

        cmds.select(cl=True)

    # ------------------------------------------------------------------
    def _create_bezier_from_linear(self):
        pos_start = cmds.xform(self.start_joint, q=True, ws=True, t=True)
        pos_mid   = cmds.xform(self.mid_joint,   q=True, ws=True, t=True)
        pos_end   = cmds.xform(self.end_joint,   q=True, ws=True, t=True)

        bez = cmds.curve(degree=3, bezier=True, p=[
            pos_start, pos_start, pos_mid, pos_mid, pos_mid, pos_end, pos_end
        ])
        bez = cmds.rename(bez, f"{self.side}_{self.name}_bezier_CRV")

        vec_start_end = [
            pos_end[0] - pos_start[0],
            pos_end[1] - pos_start[1],
            pos_end[2] - pos_start[2]
        ]

        length = math.sqrt(vec_start_end[0]**2 + vec_start_end[1]**2 + vec_start_end[2]**2)
        if length == 0:
            length = 1

        dir_smooth     = [vec_start_end[i] / length for i in range(3)]
        tangent_weight = length * 0.25

        new_cv2 = [pos_mid[i] - dir_smooth[i] * tangent_weight for i in range(3)]
        new_cv4 = [pos_mid[i] + dir_smooth[i] * tangent_weight for i in range(3)]

        cmds.xform(f"{bez}.cv[0]", ws=True, t=pos_start)
        cmds.xform(f"{bez}.cv[1]", ws=True, t=pos_start)
        cmds.xform(f"{bez}.cv[2]", ws=True, t=new_cv2)
        cmds.xform(f"{bez}.cv[3]", ws=True, t=pos_mid)
        cmds.xform(f"{bez}.cv[4]", ws=True, t=new_cv4)
        cmds.xform(f"{bez}.cv[5]", ws=True, t=pos_end)
        cmds.xform(f"{bez}.cv[6]", ws=True, t=pos_end)

        print(f"[CurvatureModule] Bezier: tangentes suavizadas por interpolación de vector.")
        return bez

    # ------------------------------------------------------------------
    def _create_degree2_from_linear(self):
        d2 = cmds.duplicate(self.linear_curve, name=f"{self.side}_{self.name}_degree2_CRV")[0]
        cmds.rebuildCurve(d2, degree=2, spans=2, keepRange=0,
                          rebuildType=0, keepEndPoints=True, keepTangents=False)
        return d2

    # ------------------------------------------------------------------
    def _create_twist_curves(self):
        """
        Hace un detachCurve a u=0.5 sobre la degree2_curve con keepOriginal=True.
        La curva original se conserva intacta con todas sus conexiones a controlPoints.
        Las dos curvas resultantes se guardan en self.upper_curve y self.lower_curve
        para que el TwistModule las consuma directamente.
        """
        detach_results = cmds.detachCurve(
            f"{self.degree2_curve}.u[0.5]",
            ch=True,
            k=[True, True],
            rpo=False          # rpo=False → keepOriginal=True, NO reemplaza la curva original
        )

        # detachCurve devuelve [upperCurve, lowerCurve, detachNode] cuando ch=True
        self.upper_curve = cmds.rename(detach_results[0],
                                       f"{self.side}_{self.name}_upperSegment_CRV")
        self.lower_curve = cmds.rename(detach_results[1],
                                       f"{self.side}_{self.name}_lowerSegment_CRV")

        # Aseguramos que el parámetro de corte esté exactamente en 0.5
        history      = cmds.listHistory(self.upper_curve)
        detach_node  = cmds.ls(history, type="detachCurve")
        if detach_node:
            cmds.setAttr(f"{detach_node[0]}.parameter[0]", 0.5)

        print(f"[CurvatureModule] Twist curves: '{self.upper_curve}' / '{self.lower_curve}'")
        print(f"[CurvatureModule] degree2_curve original conservada: '{self.degree2_curve}'")

    # ------------------------------------------------------------------
    # MÉTODO: CREAR LOCATORS Y DUPLICAR EL CV 2 Y CV 4
    # ------------------------------------------------------------------
    def create_locators_at_bezier_tangents(self, curve, only_elbow_tangents=True):
        """
        Genera los locators en los CVs tangentes y luego duplica y renombra 
        específicamente el del cv2 y el del cv4.
        """
        if only_elbow_tangents:
            tangent_indices = [2, 3, 4]
        else:
            tangent_indices = [1, 2, 4, 5]

        cv_positions = self._get_cv_positions(curve)
        originals  = {}
        duplicates = {}

        for idx in tangent_indices:
            if idx < len(cv_positions):
                pos = cv_positions[idx]

                orig_name = f"{self.side}_{self.name}_tangent{idx}_LOC"
                orig_loc  = cmds.spaceLocator(name=orig_name)[0]
                cmds.xform(orig_loc, ws=True, t=pos)

                orig_shape = self._get_shape(orig_loc)
                cmds.setAttr(f"{orig_shape}.localScaleX", 2)
                cmds.setAttr(f"{orig_shape}.localScaleY", 2)
                cmds.setAttr(f"{orig_shape}.localScaleZ", 2)

                originals[idx] = orig_loc

                if idx in [2, 4]:
                    dup_name = f"{self.side}_{self.name}_tangent_cv{idx}_LOC"
                    dup_loc  = cmds.duplicate(orig_loc, name=dup_name)[0]

                    dup_shape = self._get_shape(dup_loc)
                    cmds.setAttr(f"{dup_shape}.localScaleX", 1.2)
                    cmds.setAttr(f"{dup_shape}.localScaleY", 1.2)
                    cmds.setAttr(f"{dup_shape}.localScaleZ", 1.2)

                    duplicates[idx] = dup_loc

        # ------------------------------------------------------------------
        # CONSTRAINTS DE LOCATORS
        # ------------------------------------------------------------------
        cmds.pointConstraint(originals[4], duplicates[4], maintainOffset=False)
        cmds.pointConstraint(originals[2], duplicates[2], maintainOffset=False)
        cmds.parent(originals[2], originals[4], originals[3])

        if self.mid_joint and cmds.objExists(self.mid_joint):
            if 3 in originals:
                cmds.pointConstraint(self.mid_joint, originals[3], maintainOffset=True)

        if self.mid_joint and self.start_joint and \
           cmds.objExists(self.mid_joint) and cmds.objExists(self.start_joint):
            orient = cmds.orientConstraint(
                self.start_joint, self.mid_joint, originals[3], maintainOffset=True
            )
            cmds.setAttr(f"{orient[0]}.interpType", 2)

        # ------------------------------------------------------------------
        # CONEXIÓN MATRICIAL → degree2_curve controlPoints
        # ------------------------------------------------------------------
        if self.degree2_curve and cmds.objExists(self.degree2_curve):
            d2_shape = self._get_shape(self.degree2_curve)

            if self.start_joint and cmds.objExists(self.start_joint):
                start_dcm = cmds.createNode(
                    'decomposeMatrix', name=f"{self.side}_{self.start_joint}_DCM"
                )
                cmds.connectAttr(
                    f"{self.start_joint}.worldMatrix[0]", f"{start_dcm}.inputMatrix", force=True
                )
                cmds.connectAttr(
                    f"{start_dcm}.outputTranslate", f"{d2_shape}.controlPoints[0]", force=True
                )

            mapping = {2: 1, 4: 2}
            for bez_idx, d2_idx in mapping.items():
                if bez_idx in duplicates:
                    loc_dup  = duplicates[bez_idx]
                    codo_dcm = cmds.createNode(
                        'decomposeMatrix', name=f"{self.side}_{loc_dup}_DCM"
                    )
                    cmds.connectAttr(
                        f"{loc_dup}.worldMatrix[0]", f"{codo_dcm}.inputMatrix", force=True
                    )
                    cmds.connectAttr(
                        f"{codo_dcm}.outputTranslate",
                        f"{d2_shape}.controlPoints[{d2_idx}]", force=True
                    )
                    print(f"[CurvatureModule] Tangente conectada: {loc_dup} -> controlPoints[{d2_idx}]")

            if self.end_joint and cmds.objExists(self.end_joint):
                end_dcm = cmds.createNode(
                    'decomposeMatrix', name=f"{self.side}_{self.end_joint}_DCM"
                )
                cmds.connectAttr(
                    f"{self.end_joint}.worldMatrix[0]", f"{end_dcm}.inputMatrix", force=True
                )
                cmds.connectAttr(
                    f"{end_dcm}.outputTranslate", f"{d2_shape}.controlPoints[3]", force=True
                )

            print(f"[CurvatureModule] Node Editor configurado para {self.name}.")

        # ------------------------------------------------------------------
        # CONEXIÓN CURVATURA → scale de originals[3]
        # ------------------------------------------------------------------
        if self.switch_control and cmds.objExists(self.switch_control):
            attr_path = f"{self.switch_control}.Curvature"
            if cmds.attributeQuery("Curvature", node=self.switch_control, exists=True):
                if 3 in originals:
                    loc3 = originals[3]
                    cmds.connectAttr(attr_path, f"{loc3}.scaleX", force=True)
                    cmds.connectAttr(attr_path, f"{loc3}.scaleY", force=True)
                    cmds.connectAttr(attr_path, f"{loc3}.scaleZ", force=True)
                    print(f"[CurvatureModule] '{attr_path}' conectado al Scale de {loc3}.")
            else:
                cmds.warning(
                    f"[CurvatureModule] '{self.switch_control}' no tiene el atributo 'Curvature'."
                )
        else:
            print("[CurvatureModule] No se especificó un Switch Control válido.")

        print(f"[CurvatureModule] Proceso de locators finalizado para {self.name}.")
        return originals, duplicates