import maya.cmds as cmds    
import maya.mel as mel
import guides_module
import controlsLibrary
from groups_module import ControlsGroups
from nodeCreator_module import NodeCreator
import rigRoot_module

class MouthModule(object):

    # Índices fijos de coordinate[] / outputMatrix[] en el uvPin compartido
    RAW_INDEX = {"L": 0, "R": 1, "C": 2}
    BLEND01_INDEX = {"L": 3, "R": 5}
    BLEND02_INDEX = {"L": 4, "R": 6}

    def __init__(self, boca_surface="boca_surface", 
                 lip_mid="lip_mid", 
                 lip_end="lip_end", 
                 root_instance=None, 
                 rig_name="Character",
                 side="L"):
        
        self.boca_surface = boca_surface
        self.lip_mid = lip_mid
        self.lip_end = lip_end
        self.group_maker = ControlsGroups()
        self.rig_name = rig_name
        self.root_instance = root_instance
        self.styles = {"mainFk": "circleControl"}
        
        self.side = side
        self.prefix = f"{self.side}_{rig_name}"
        
        # Nodos que expone el modulo para que el jaw pueda engancharse.
        self.mid_lip_ctrl = None
        self.end_lip_ctrl = None
        self.end_lip_grp = None

    # ------------------------------------------------------------------
    # HELPERS DE IDEMPOTENCIA (crear una vez, reutilizar siempre)
    # ------------------------------------------------------------------
    def _get_or_create_shared_uvpin(self):
        uvpin_name = f"C_{self.rig_name}_mouth_uvPin"
        if cmds.objExists(uvpin_name):
            return uvpin_name

        uvpin_node = NodeCreator(
            side=f"C_{self.rig_name}", node_type="uvPin", base_name="mouth",
            name="Local", tag="CTRL", parent=None, custom_suffix=None
        ).create()
        uvpin_node = cmds.rename(uvpin_node, uvpin_name)

        cmds.connectAttr(f"{self.boca_surface}.worldSpace[0]", f"{uvpin_node}.deformedGeometry")
        cmds.setAttr(f"{uvpin_node}.normalAxis", 2)
        cmds.setAttr(f"{uvpin_node}.tangentAxis", 0)
        return uvpin_node

    def _get_or_create_shared_settings_grp(self):
        grp_name = f"C_{self.rig_name}_lipsSettings_GRP"
        if cmds.objExists(grp_name):
            return grp_name

        settings_grp = cmds.group(em=True, n=grp_name)
        cmds.addAttr(settings_grp, ln="HorizontalFollow01", nn="Horizontal Follow 01", at="float", min=0, max=1, dv=0.5, k=True)
        cmds.addAttr(settings_grp, ln="HorizontalFollow02", nn="Horizontal Follow 02", at="float", min=0, max=1, dv=0.25, k=True)
        cmds.addAttr(settings_grp, ln="VerticalFollow01", nn="Vertical Follow 01", at="float", min=0, max=1, dv=0.77, k=True)
        cmds.addAttr(settings_grp, ln="VerticalFollow02", nn="Vertical Follow 02", at="float", min=0, max=1, dv=0.58, k=True)
        return settings_grp

    def _is_coordinate_connected(self, uvpin_node, coordinate_index):
        conns = cmds.listConnections(
            f"{uvpin_node}.coordinate[{coordinate_index}].coordinateU",
            source=True, destination=False
        )
        return bool(conns)

    def _build_cps_network(self, prefix, cps_name, base_name, source_ctrl, source_ctrl_grp):
        """
        Crea el space-tracking + closestPointOnSurface (CPS) crudo de un control.
        Devuelve (local_off, local_trn, closest_point_node).
        """
        local_off, local_trn = self.group_maker.create_space_tracking_hierarchy(
            space_base_name=f"{prefix}_{base_name}Local",
            target_joint=source_ctrl_grp,
            parent_group=None
        )

        mult_node = NodeCreator(
            side=prefix, node_type="multMatrix", base_name=base_name,
            name="Local", tag="CTRL", parent=None, custom_suffix=None
        ).create()
        decompose_node = NodeCreator(
            side=prefix, node_type="decomposeMatrix", base_name=base_name,
            name="Local", tag="CTRL", parent=None, custom_suffix=None
        ).create()
        decompose_trn_node = NodeCreator(
            side=prefix, node_type="decomposeMatrix", base_name=base_name,
            name="Local", tag="CTRL", parent=None, custom_suffix=None
        ).create()

        cmds.connectAttr(f"{source_ctrl}.matrix", f"{mult_node}.matrixIn[0]")
        cmds.connectAttr(f"{mult_node}.matrixSum", f"{decompose_node}.inputMatrix")
        cmds.connectAttr(f"{decompose_node}.outputTranslate", f"{local_trn}.translate")
        cmds.connectAttr(f"{decompose_node}.outputRotate", f"{local_trn}.rotate")
        cmds.connectAttr(f"{decompose_node}.outputScale", f"{local_trn}.scale")
        cmds.connectAttr(f"{local_trn}.worldMatrix[0]", f"{decompose_trn_node}.inputMatrix")

        closest_point_node = NodeCreator(
            side=prefix, node_type="closestPointOnSurface", base_name=base_name,
            name="Local", tag="CTRL", parent=None, custom_suffix=None
        ).create()
        closest_point_node = cmds.rename(closest_point_node, cps_name)

        cmds.connectAttr(f"{self.boca_surface}.worldSpace[0]", f"{closest_point_node}.inputSurface")
        cmds.connectAttr(f"{decompose_trn_node}.outputTranslate", f"{closest_point_node}.inPosition")

        return local_off, local_trn, closest_point_node

    # ------------------------------------------------------------------
    # MAYA MUSCLE / KEEP OUT
    # ------------------------------------------------------------------
    def _get_or_create_muscle_surface(self):
        """
        Convierte la nurbs de la boca en Muscle Object (una sola vez, aunque
        build() se llame varias veces) y devuelve:
            (transform_de_la_nurbs, shape_cMuscleObject)
        """
        # --- plugin + scripts MEL (en Maya 2025 todo vive en cMuscle.mel) ---
        if not cmds.pluginInfo("MayaMuscle", query=True, loaded=True):
            cmds.loadPlugin("MayaMuscle", quiet=True)
        mel.eval('source "cMuscle.mel";')

        # self.boca_surface se usa como shape (worldSpace[0]); las herramientas
        # de Muscle necesitan el transform.
        surface_node = self.boca_surface
        if cmds.objectType(surface_node, isAType="shape"):
            surface_trn = cmds.listRelatives(surface_node, parent=True)[0]
        else:
            surface_trn = surface_node

        muscle_shapes = cmds.listRelatives(
            surface_trn, shapes=True, type="cMuscleObject"
        ) or []

        # --- Muscles/Bones > Convert Surface to Muscle/Bone ---
        #     cMuscle_makeMuscle(int $keepBase) ; 0 = sin copia base
        if not muscle_shapes:
            sel_backup = cmds.ls(selection=True) or []

            cmds.select(surface_trn, replace=True)
            mel.eval("cMuscle_makeMuscle(0);")

            # IMPORTANTE: hay que volver a preguntar. La lista de arriba se
            # calculo ANTES de la conversion y sigue vacia; si usas
            # muscle_shapes[0] sin refrescar te salta un IndexError.
            muscle_shapes = cmds.listRelatives(
                surface_trn, shapes=True, type="cMuscleObject"
            ) or []

            if sel_backup:
                cmds.select(sel_backup, replace=True)
            else:
                cmds.select(clear=True)

        if not muscle_shapes:
            cmds.warning(
                f"MouthModule: no se pudo convertir '{surface_trn}' en Muscle Object."
            )
            return surface_trn, None

        cmds.setAttr(f"{muscle_shapes[0]}.fat", 0)
        return surface_trn, muscle_shapes[0]

    # def _build_projection_aim_keepout(self, side_code, nurb_center_locator,
    #                                   target_node, surface_trn):
    #     """
    #     Crea, para UN lado, el aim locator sobre el centro de proyeccion y le
    #     monta el keepOut contra la nurbs.

    #     side_code           -> "C", "L" o "R"
    #     nurb_center_locator -> C_<rig>_lipCenterOfProjection_LOC (compartido)
    #     target_node         -> nodo al que mira el eje Z de este lado
    #     surface_trn         -> transform de la nurbs ya convertida a muscle

    #     Es idempotente: si el aim locator de ese lado ya existe, no hace nada.
    #     Devuelve el nombre del aim locator, o None si no se pudo crear.
    #     """
    #     prefix = f"{side_code}_{self.rig_name}"
    #     aim_locator_name = f"{prefix}_lipCenterOfProjectionAim_LOC"

    #     if cmds.objExists(aim_locator_name):
    #         return aim_locator_name

    #     if not cmds.objExists(target_node):
    #         cmds.warning(
    #             f"MouthModule: el target '{target_node}' del aim de '{side_code}' "
    #             f"no existe todavia, me salto ese lado."
    #         )
    #         return None

    #     aim_locator = cmds.spaceLocator(name=aim_locator_name)[0]

    #     aim_matrix = NodeCreator(
    #         side=prefix, node_type="aimMatrix", base_name="mouthAim",
    #         name="Local", tag="CTRL", parent=None, custom_suffix=None
    #     ).create()
    #     aim_matrix = cmds.rename(
    #         aim_matrix, f"{prefix}_lipCenterOfProjectionAim_aimMatrix"
    #     )

    #     cmds.connectAttr(f"{nurb_center_locator}.worldMatrix[0]", f"{aim_matrix}.inputMatrix")
    #     cmds.connectAttr(f"{target_node}.worldMatrix[0]", f"{aim_matrix}.primaryTargetMatrix")

    #     # --- Primario: el eje Z apunta al target ---
    #     cmds.setAttr(f"{aim_matrix}.primaryMode", 1)          # 1 = Aim
    #     cmds.setAttr(f"{aim_matrix}.primaryInputAxisX", 0)
    #     cmds.setAttr(f"{aim_matrix}.primaryInputAxisY", 0)
    #     cmds.setAttr(f"{aim_matrix}.primaryInputAxisZ", 1)

    #     # --- Secundario: Y hacia ARRIBA ---
    #     # secondaryMode 1 (Aim) haria que la Y apuntase a la posicion del
    #     # secondaryTargetMatrix, que al no estar conectado es el origen del
    #     # mundo => Y mirando abajo. Con 2 (Align) la Y se alinea con el
    #     # vector secondaryTargetVector (0,1,0) en espacio mundo.
    #     cmds.setAttr(f"{aim_matrix}.secondaryMode", 2)        # 2 = Align
    #     cmds.setAttr(f"{aim_matrix}.secondaryInputAxisX", 0)
    #     cmds.setAttr(f"{aim_matrix}.secondaryInputAxisY", 1)
    #     cmds.setAttr(f"{aim_matrix}.secondaryInputAxisZ", 0)
    #     cmds.setAttr(f"{aim_matrix}.secondaryTargetVectorX", 0)
    #     cmds.setAttr(f"{aim_matrix}.secondaryTargetVectorY", 1)
    #     cmds.setAttr(f"{aim_matrix}.secondaryTargetVectorZ", 0)

    #     cmds.connectAttr(f"{aim_matrix}.outputMatrix", f"{aim_locator}.offsetParentMatrix")

    #     # =========================================================
    #     # KEEP OUT
    #     # =========================================================
    #     sel_backup = cmds.ls(selection=True) or []

    #     # --- Self/Multi Collision > Rig selection for KeepOut ---
    #     #     cMuscle_rigKeepOutSel() trabaja sobre la seleccion.
    #     #     (cMuscle_rigKeepOut pide un $obj, no es este)
    #     keepout_before = set(cmds.ls(type="cMuscleKeepOut") or [])

    #     cmds.select(aim_locator, replace=True)
    #     mel.eval("cMuscle_rigKeepOutSel();")

    #     keepout_after = set(cmds.ls(type="cMuscleKeepOut") or [])
    #     new_keepout_shapes = sorted(keepout_after - keepout_before)

    #     # De la shape cMuscleKeepOut subimos a su transform.
    #     keepout_trns = []
    #     for shp in new_keepout_shapes:
    #         keepout_trns.extend(cmds.listRelatives(shp, parent=True) or [])

    #     # --- In Direction en Z ---
    #     # Los tres componentes explicitos: por defecto viene en X, si solo
    #     # pones la Z te queda una diagonal (1, 0, 1).
    #     for ko_shape in new_keepout_shapes:
    #         cmds.setAttr(f"{ko_shape}.inDirectionX", 0)
    #         cmds.setAttr(f"{ko_shape}.inDirectionY", 0)
    #         cmds.setAttr(f"{ko_shape}.inDirectionZ", 1)

    #     # --- Self/Multi Collision > Connect Muscles to Keep Out ---
    #     #     cMuscle_keepOutAddRemMuscle(1) ; keepOut primero, muscle el ULTIMO
    #     if keepout_trns:
    #         cmds.select(keepout_trns, replace=True)
    #         cmds.select(surface_trn, add=True)
    #         mel.eval("cMuscle_keepOutAddRemMuscle(1);")
    #     else:
    #         cmds.warning(
    #             f"MouthModule: no se creo ningun cMuscleKeepOut sobre "
    #             f"'{aim_locator}', me salto el Connect Muscles to Keep Out."
    #         )

    #     if sel_backup:
    #         cmds.select(sel_backup, replace=True)
    #     else:
    #         cmds.select(clear=True)

    #     return aim_locator

    
    def _build_off_network(self, prefix, base_name, source_ctrl, source_ctrl_grp):
        """
        Crea el space-tracking + closestPointOnSurface (CPS) crudo de un control.
        Devuelve (local_off, local_trn, closest_point_node).
        """
        local_off, local_trn = self.group_maker.create_space_tracking_hierarchy(
            space_base_name=f"{prefix}_{base_name}Local",
            target_joint=source_ctrl_grp,
            parent_group=None
        )

        mult_node = NodeCreator(
            side=prefix, node_type="multMatrix", base_name=base_name,
            name="Local", tag="CTRL", parent=None, custom_suffix=None
        ).create()
        decompose_node = NodeCreator(
            side=prefix, node_type="decomposeMatrix", base_name=base_name,
            name="Local", tag="CTRL", parent=None, custom_suffix=None
        ).create()
        decompose_trn_node = NodeCreator(
            side=prefix, node_type="decomposeMatrix", base_name=base_name,
            name="Local", tag="CTRL", parent=None, custom_suffix=None
        ).create()

        cmds.connectAttr(f"{source_ctrl}.matrix", f"{mult_node}.matrixIn[0]")
        cmds.connectAttr(f"{mult_node}.matrixSum", f"{decompose_node}.inputMatrix")
        cmds.connectAttr(f"{decompose_node}.outputTranslate", f"{local_trn}.translate")
        cmds.connectAttr(f"{decompose_node}.outputRotate", f"{local_trn}.rotate")
        cmds.connectAttr(f"{decompose_node}.outputScale", f"{local_trn}.scale")
        cmds.connectAttr(f"{local_trn}.worldMatrix[0]", f"{decompose_trn_node}.inputMatrix")


        return local_off, local_trn

    # ------------------------------------------------------------------
    # SISTEMA DE PREBIND (genérico) — mismo patrón que upperPrebind_joint /
    # lowerPrebind_joint, pero reutilizable para depresor / upperPinch / lowerPinch.
    # ------------------------------------------------------------------
    def _get_skincluster_from_joint(self, joint_name):
        """
        Busca un skinCluster que use 'joint_name' como influencia.
        Devuelve (skinCluster, indice_de_influencia) o (None, None) si todavía
        no existe (por ejemplo si el skinning de la malla se hace en otro módulo
        y aún no se ha corrido).
        """
        if not cmds.objExists(joint_name):
            return None, None

        skin_clusters = list(set(cmds.listConnections(joint_name, type="skinCluster") or []))
        if not skin_clusters:
            return None, None

        skin_cluster = skin_clusters[0]
        influences = cmds.skinCluster(skin_cluster, q=True, inf=True) or []
        if joint_name not in influences:
            return None, None

        influence_index = influences.index(joint_name)
        return skin_cluster, influence_index

    def _connect_prebind_to_skincluster(self, skin_cluster, joint_name, prebind_joint):
        """
        Busca el índice de influencia de 'joint_name' dentro de 'skin_cluster'
        (el mismo índice en el que joint_name está conectado a .matrix[i])
        y conecta prebind_joint.worldInverseMatrix[0] -> skin_cluster.bindPreMatrix[i]
        en ese mismo índice. Idempotente.
        """
        if not skin_cluster or not cmds.objExists(skin_cluster):
            return
        if not cmds.objExists(joint_name) or not cmds.objExists(prebind_joint):
            return

        influences = cmds.skinCluster(skin_cluster, q=True, inf=True) or []
        if joint_name not in influences:
            return
        index = influences.index(joint_name)

        dest = f"{skin_cluster}.bindPreMatrix[{index}]"
        if not cmds.isConnected(f"{prebind_joint}.worldInverseMatrix[0]", dest):
            cmds.connectAttr(f"{prebind_joint}.worldInverseMatrix[0]", dest, force=True)

    def _connect_freeze_lock_weights(self, freeze_joint, skin_cluster):
        """
        Conecta freeze_joint.lockInfluenceWeights -> skin_cluster.lockWeights[0]
        (freeze_joint siempre se pasa primero al crear cada skinCluster, así que
        su índice de influencia es 0). Idempotente.
        """
        if not freeze_joint or not skin_cluster:
            return
        if not cmds.objExists(freeze_joint) or not cmds.objExists(skin_cluster):
            return

        src = f"{freeze_joint}.lockInfluenceWeights"
        dst = f"{skin_cluster}.lockWeights[0]"
        if not cmds.isConnected(src, dst):
            cmds.connectAttr(src, dst, force=True)

    def _connect_joint_lock_weights(self, joint_name, skin_cluster):
        """
        Conecta joint_name.lockInfluenceWeights -> skin_cluster.lockWeights[i],
        donde i es el índice de influencia real de joint_name dentro de
        skin_cluster (a diferencia de _connect_freeze_lock_weights, que asume
        siempre índice 0 para freeze_joint). Idempotente.
        """
        if not joint_name or not skin_cluster:
            return
        if not cmds.objExists(joint_name) or not cmds.objExists(skin_cluster):
            return

        influences = cmds.skinCluster(skin_cluster, q=True, inf=True) or []
        if joint_name not in influences:
            return
        index = influences.index(joint_name)

        src = f"{joint_name}.lockInfluenceWeights"
        dst = f"{skin_cluster}.lockWeights[{index}]"
        if not cmds.isConnected(src, dst):
            cmds.connectAttr(src, dst, force=True)

    def _chain_curve_into_skincluster(self, previous_curve_name, next_skin_cluster):
        """
        Encadena dos curvas: redirige TANTO el input geometry COMO el original
        geometry del siguiente skinCluster (p.ej. Levator) para que lean
        directamente el worldSpace de la curva anterior de la cadena (p.ej.
        Upper), en vez de la copia estática (Orig) creada al hacer bind.

        Así el siguiente skinCluster siempre parte de la posición actual (ya
        deformada) de la curva anterior, y aplica su propia deformación de
        joints encima. Idempotente.
        """
        if not previous_curve_name or not next_skin_cluster:
            return
        if not cmds.objExists(previous_curve_name) or not cmds.objExists(next_skin_cluster):
            return

        src = f"{previous_curve_name}.worldSpace[0]"
        input_dst = f"{next_skin_cluster}.input[0].inputGeometry"
        original_dst = f"{next_skin_cluster}.originalGeometry[0]"

        if not cmds.isConnected(src, input_dst):
            cmds.connectAttr(src, input_dst, force=True)
        if not cmds.isConnected(src, original_dst):
            cmds.connectAttr(src, original_dst, force=True)

    def _setup_prebind_joint(self, prebind_name, source_joint, driver_target):
        """
        Crea (si no existe) el joint de PreBind para 'source_joint', lo
        parentConstrainea a 'driver_target' (el mismo driver que ya mueve el
        grupo/off del control, igual que center_locator_name en upper/lower) y,
        si 'source_joint' ya es influencia de algún skinCluster, conecta
        prebind.inverseMatrix -> skinCluster.bindPreMatrix[indice].

        Idempotente: se puede llamar en cada build() sin duplicar nada.
        """
        if not cmds.objExists(source_joint) or not cmds.objExists(driver_target):
            return None

        if not cmds.objExists(prebind_name):
            cmds.select(clear=True)
            prebind_joint = cmds.joint(n=prebind_name)
            cmds.matchTransform(prebind_joint, source_joint, pos=True, rot=True)
            cmds.select(clear=True)
        else:
            prebind_joint = prebind_name

        if not cmds.listRelatives(prebind_joint, children=True, type="parentConstraint"):
            cmds.parentConstraint(driver_target, prebind_joint, mo=True)

        skin_cluster, _ = self._get_skincluster_from_joint(source_joint)
        if skin_cluster:
            self._connect_prebind_to_skincluster(skin_cluster, source_joint, prebind_joint)

        return prebind_joint

    def _create_blend_pair(self, side_label, axis, own_cps, center_cps, suffix, blender_attr):
        """
        Crea un blendTwoAttr que blendea own_cps.Parameter{U/V} (input0, raw propio)
        vs center_cps.Parameter{U/V} (input1, centro), controlado por blender_attr.
        axis: "U" o "V". suffix: "01" o "02".
        """
        bta_name = f"{side_label}_lip{axis}{suffix}_BTA"

        bta_node = NodeCreator(
            side=side_label, node_type="blendTwoAttr", base_name=f"lip{axis}{suffix}",
            name="Local", tag="CTRL", parent=None, custom_suffix=None
        ).create()
        bta_node = cmds.rename(bta_node, bta_name)

        param_attr = "parameterU" if axis == "U" else "parameterV"
        cmds.connectAttr(f"{own_cps}.result.{param_attr}", f"{bta_node}.input[0]")
        cmds.connectAttr(f"{center_cps}.result.{param_attr}", f"{bta_node}.input[1]")
        cmds.connectAttr(blender_attr, f"{bta_node}.attributesBlender")

        return bta_node

    def _get_ordered_lip_locator_info(self):
        """
        Igual que _get_ordered_lip_locator_names, pero además devuelve el
        prefix (L_/R_/C_ + rig_name) y el base_name de cada locator, para
        poder nombrar los decomposeMatrix con el mismo criterio que el resto
        del módulo (NodeCreator side=prefix, base_name=base).
        Orden de comisura a comisura: L_raw -> L_02 -> L_01 -> C -> R_01 -> R_02 -> R_raw.
        Coincide 1 a 1 con los 7 coordinate[]/outputMatrix[] del uvPin compartido.
        """
        L = f"L_{self.rig_name}"
        R = f"R_{self.rig_name}"
        C = f"C_{self.rig_name}"
        return [
            (L, "lipProjected", f"{L}_lipProjected_LOC"),
            (L, "lipProjected02", f"{L}_lipProjected02_LOC"),
            (L, "lipProjected01", f"{L}_lipProjected01_LOC"),
            (C, "lipProjected", f"{C}_lipProjected_LOC"),
            (R, "lipProjected01", f"{R}_lipProjected01_LOC"),
            (R, "lipProjected02", f"{R}_lipProjected02_LOC"),
            (R, "lipProjected", f"{R}_lipProjected_LOC"),
        ]

    def _get_ordered_lip_locator_names(self):
        """
        Orden de comisura a comisura: L_raw -> L_02 -> L_01 -> C -> R_01 -> R_02 -> R_raw.
        Coincide 1 a 1 con los 7 coordinate[]/outputMatrix[] del uvPin compartido.
        """
        return [locator_name for _, _, locator_name in self._get_ordered_lip_locator_info()]

    def _build_lip_curve(self):
        """
        Crea (una única vez) la curva de curvatura de los labios:
        1. Curva de grado 1 con un CV en la posición de cada locator (7 CVs).
        2. rebuildCurve a grado 3, 4 spans (4+3 = 7 CVs -> mismo conteo, misma correspondencia 1 a 1).
        3. Cada locator queda conectado a (gestiona en vivo) el CV que ocupa su posición.

        Solo se construye cuando existen los 7 locators (L, R y centro), es decir,
        cuando ya se ha llamado a build() en ambos lados. Si aún faltan, no hace nada.
        """
        curve_name = f"C_{self.rig_name}_lipProjected_CRV"
        if cmds.objExists(curve_name):
            return curve_name

        locator_info = self._get_ordered_lip_locator_info()
        ordered_locators = [locator_name for _, _, locator_name in locator_info]
        if not all(cmds.objExists(loc) for loc in ordered_locators):
            # Todavía no existen los locators de los dos lados; se construirá
            # cuando se llame a build() en el lado que falta.
            return None

        positions = [cmds.xform(loc, q=True, ws=True, t=True) for loc in ordered_locators]

        self.curve_transform = cmds.curve(d=1, p=positions, n=curve_name)
        cmds.rebuildCurve(
            self.curve_transform, ch=0, rpo=1, rt=0, end=1, kr=0, kcp=0, kep=1, kt=0,
            s=4, d=3, tol=0.01
        )
        cmds.setAttr(f"{self.curve_transform}.lineWidth", 3)

        curve_shape = cmds.listRelatives(self.curve_transform, shapes=True)[0]

        for cv_index, (prefix, base_name, locator_name) in enumerate(locator_info):
            decompose_node = NodeCreator(
                side=prefix, node_type="decomposeMatrix", base_name=base_name,
                name="Local", tag="CTRL", parent=None, custom_suffix=None
            ).create()
            cmds.connectAttr(f"{locator_name}.worldMatrix[0]", f"{decompose_node}.inputMatrix")
            cmds.connectAttr(f"{decompose_node}.outputTranslate", f"{curve_shape}.controlPoints[{cv_index}]")

        if cmds.objExists(self.curve_transform):
            upperCurve = cmds.duplicate(self.curve_transform, n=f"C_{self.rig_name}_lipUpperLine_CRV")
        else:
            print(f"Warning: Curve {self.curve_transform} does not exist, cannot duplicate.")

        if cmds.objExists(self.curve_transform):
            lowerCurve = cmds.duplicate(self.curve_transform, n=f"C_{self.rig_name}_lipLowerLine_CRV")
        else:
            print(f"Warning: Curve {self.curve_transform} does not exist, cannot duplicate.")

        if cmds.objExists(self.curve_transform):
            levatorCurve = cmds.duplicate(self.curve_transform, n=f"C_{self.rig_name}_lipCurvatureLevator_CRV")
        else:
            print(f"Warning: Curve {self.curve_transform} does not exist, cannot duplicate.")

        if cmds.objExists(self.curve_transform):
            depresorCurve = cmds.duplicate(self.curve_transform, n=f"C_{self.rig_name}_lipCurvatureDepresor_CRV")
        else:
            print(f"Warning: Curve {self.curve_transform} does not exist, cannot duplicate.")

        if cmds.objExists(self.curve_transform):
            upperPinchCurve = cmds.duplicate(self.curve_transform, n=f"C_{self.rig_name}_lipCurvatureUpperPinch_CRV")
        else:
            print(f"Warning: Curve {self.curve_transform} does not exist, cannot duplicate.")

        if cmds.objExists(self.curve_transform):
            lowerPinchCurve = cmds.duplicate(self.curve_transform, n=f"C_{self.rig_name}_lipCurvatureLowerPinch_CRV")
        else:
            print(f"Warning: Curve {self.curve_transform} does not exist, cannot duplicate.")
            
        #cmds.connectAttr(f"{self.curve_transform}.worldSpace[0]", f"{upperCurve[0]}.create")
        #cmds.connectAttr(f"{self.curve_transform}.worldSpace[0]", f"{lowerCurve[0]}.create")
        #cmds.connectAttr(f"{self.curve_transform}.worldSpace[0]", f"{levatorCurve[0]}.create")
        #cmds.connectAttr(f"{self.curve_transform}.worldSpace[0]", f"{depresorCurve[0]}.create")
        #cmds.connectAttr(f"{self.curve_transform}.worldSpace[0]", f"{upperPinchCurve[0]}.create")
        #cmds.connectAttr(f"{self.curve_transform}.worldSpace[0]", f"{lowerPinchCurve[0]}.create")

        return self.curve_transform, upperCurve, lowerCurve, levatorCurve, depresorCurve, upperPinchCurve, lowerPinchCurve

    def _get_or_create_curve_motion_locator(self, curve_name, base_name, u_value, side=None):
        """
        Crea (una única vez) un motionPath sobre `curve_name` fijo en `u_value`,
        con un locator conectado a su salida (posición + rotación).

        `side` determina el prefijo (L_/R_/C_) del nombre para que cada lado
        tenga sus propios nodos, aunque lean de la misma curva compartida.
        Idempotente: si el locator ya existe, lo devuelve sin tocar nada.
        """
        prefix = f"{side}_{self.rig_name}" if side else f"C_{self.rig_name}"
        locator_name = f"{prefix}_{base_name}_tracker_LOC"
        locatorGlobal_name = f"{prefix}_{base_name}_trackerGlobal_LOC"

        motionpath_name = f"{prefix}_{base_name}_MPA"

        if cmds.objExists(locator_name):
            return motionpath_name, locator_name

        motionpath_node = NodeCreator(
            side=prefix, node_type="motionPath", base_name=base_name,
            name="Local", tag="CTRL", parent=None, custom_suffix=None
        ).create()
        motionpath_node = cmds.rename(motionpath_node, motionpath_name)

        cmds.connectAttr(f"{curve_name}.worldSpace[0]", f"{motionpath_node}.geometryPath")
        cmds.setAttr(f"{motionpath_node}.uValue", u_value)

        locatorTracker = cmds.spaceLocator(name=locator_name)[0]
        cmds.connectAttr(f"{motionpath_node}.allCoordinates", f"{locatorTracker}.translate")
        cmds.connectAttr(f"{motionpath_node}.rotate", f"{locatorTracker}.rotate")
        
        # 3. Crear Tracker Global limpio
        if not cmds.objExists(locatorGlobal_name):
            locatorTrackerGlobal = cmds.spaceLocator(name=locatorGlobal_name)[0]
            # Conectar la matriz mundial del Tracker Local al offsetParentMatrix del Global
            cmds.connectAttr(f"{locatorTracker}.worldMatrix[0]", f"{locatorTrackerGlobal}.offsetParentMatrix")

        return motionpath_node, locatorTracker
    
    # ------------------------------------------------------------------
    # BUILD
    # ------------------------------------------------------------------
    def build(self):
        # 1. CONTROL CENTRAL — se construye una única vez y se reutiliza en el lado R
        center_name = f"C_{self.rig_name}_mid_LIP_CTRL"
        if not cmds.objExists(center_name):
            mid_lip = controlsLibrary.create_control_from_lib(
                lib_name=self.styles["mainFk"],
                final_name=f"{self.prefix}_mid_LIP_CTRL"
            )
            mid_lip = cmds.rename(mid_lip, center_name)
            mid_lip_grp = self.group_maker.create_rig_hierarchy(
                mid_lip, self.lip_mid, match_rotation=True, world_space=True
            )
        else:
            mid_lip = center_name
            mid_lip_grp = cmds.listRelatives(mid_lip, parent=True)[0]
            
        self.mid_lip_ctrl = mid_lip          


        # 2. CONTROL DE LA COMISURA (end_lip) — uno por lado
        end_lip = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["mainFk"],
            final_name=f"{self.prefix}_end_LIP_CTRL"
        )
        end_lip_grp = self.group_maker.create_rig_hierarchy(
            end_lip, self.lip_end, match_rotation=True, world_space=True
        )
        self.end_lip_ctrl = end_lip
        self.end_lip_grp = end_lip_grp

        cmds.rebuildSurface(self.boca_surface, ch=0, rpo=1, rt=0, end=1, kr=0, kcp=0, kc=0,
                             su=4, du=3, sv=4, dv=3, tol=0.01, fr=0, dir=2)

        self.main_rig_grp = cmds.group(em=True, n=f"{self.prefix}_mouthControls_GRP")

        if self.side == "R":
            mirror_behavior_grp = f"{self.root_instance.rig_name}_mirrorBehaviour_GRP"
            if cmds.objExists(mirror_behavior_grp):
                cmds.parent(end_lip_grp, mirror_behavior_grp)
                cmds.setAttr(f"{end_lip_grp}.scaleX", 1)
                cmds.setAttr(f"{end_lip_grp}.scaleY", 1)
                cmds.setAttr(f"{end_lip_grp}.scaleZ", 1)
                cmds.setAttr(f"{end_lip_grp}.rotateX", 0)
                cmds.setAttr(f"{end_lip_grp}.rotateY", 45)
                cmds.setAttr(f"{end_lip_grp}.rotateZ", 0)
                
        #Duplicar controles de upper y lower lip para usarlos como locators en global, no en local        
        upper_lip_name = f"C_{self.rig_name}_lipUpper_GRP"
        if not cmds.objExists(upper_lip_name):
            mid_lipUpper = controlsLibrary.create_control_from_lib(
                    lib_name=self.styles["mainFk"],
                    final_name=f"C_{self.rig_name}_mid_lipUpper_CTRL"
            )
            mid_lipUpper = cmds.rename(mid_lipUpper, upper_lip_name)
            upper_lip_grp = self.group_maker.create_rig_hierarchy(
                    mid_lipUpper, self.lip_mid, match_rotation=True, world_space=True
            )
        else:
            mid_lipUpper = upper_lip_name
            upper_lip_grp = cmds.listRelatives(mid_lipUpper, parent=True)[0]
            
        upper_off_name = f"C_{self.rig_name}_UpperLocal_OFF"
        upper_trn_name = f"C_{self.rig_name}_UpperLocal_TRN"
        if not cmds.objExists(upper_off_name):
            upper_local_off, upper_local_trn = self._build_off_network(
                prefix=f"C_{self.rig_name}",
                base_name="Upper", source_ctrl=mid_lipUpper, source_ctrl_grp=upper_lip_grp
            )
        else:
            upper_local_off, upper_local_trn = upper_off_name, upper_trn_name

        lower_lip_name = f"C_{self.rig_name}_lipLower_GRP"
        if not cmds.objExists(lower_lip_name):
            mid_lipLower = controlsLibrary.create_control_from_lib(
                    lib_name=self.styles["mainFk"],
                    final_name=f"C_{self.rig_name}_mid_lipLower_CTRL"
            )

            mid_lipLower = cmds.rename(mid_lipLower, lower_lip_name)
            lower_lip_grp = self.group_maker.create_rig_hierarchy(
                    mid_lipLower, self.lip_mid, match_rotation=True, world_space=True
            )
            cmds.setAttr(f"{lower_lip_grp}.scaleY", -1)
        else:
            mid_lipLower = lower_lip_name
            lower_lip_grp = cmds.listRelatives(mid_lipLower, parent=True)[0]
            
        lower_off_name = f"C_{self.rig_name}_LowerLocal_OFF"
        lower_trn_name = f"C_{self.rig_name}_LowerLocal_TRN"
        inverted_name = f"C_{self.rig_name}_lipLowerInverted_GRP"

        if not cmds.objExists(inverted_name):
            lower_local_off, lower_local_trn = self._build_off_network(
                prefix=f"C_{self.rig_name}",
                base_name="Lower", source_ctrl=mid_lipLower, source_ctrl_grp=lower_lip_grp
            )
            inverted_group = cmds.group(em=True, n=inverted_name)
            cmds.setAttr(f"{inverted_group}.scaleY", -1)
            cmds.parent(lower_local_off, inverted_group)
            cmds.setAttr(f"{lower_local_off}.rotateX", 0)
            cmds.setAttr(f"{lower_local_off}.scaleZ", 1)
        else:
            inverted_group = inverted_name
            lower_local_off = cmds.listRelatives(inverted_group, children=True, type="transform")[0]
            lower_local_trn = lower_trn_name
        
        # 3. UVPIN Y SETTINGS ÚNICOS COMPARTIDOS
        uvpin_node = self._get_or_create_shared_uvpin()
        settings_grp = self._get_or_create_shared_settings_grp()

        # =========================================================
        # 4. CPS RAW DEL CENTRO — se construye una única vez
        # =========================================================
        center_raw_index = self.RAW_INDEX["C"]
        center_locator_name = f"C_{self.rig_name}_lipProjected_LOC"
        if not self._is_coordinate_connected(uvpin_node, center_raw_index):
            center_local_off, center_local_trn, center_cps = self._build_cps_network(
                prefix=f"C_{self.rig_name}", cps_name=f"C_{self.rig_name}_lips_CPS",
                base_name="mouthCenter", source_ctrl=mid_lip, source_ctrl_grp=mid_lip_grp
            )
            cmds.connectAttr(f"{center_cps}.result.parameterU", f"{uvpin_node}.coordinate[{center_raw_index}].coordinateU")
            cmds.connectAttr(f"{center_cps}.result.parameterV", f"{uvpin_node}.coordinate[{center_raw_index}].coordinateV")

            center_locator = cmds.spaceLocator(name=center_locator_name)[0]
            cmds.connectAttr(f"{uvpin_node}.outputMatrix[{center_raw_index}]", f"{center_locator}.offsetParentMatrix")
        else:
            center_locator = center_locator_name


        center_cps = cmds.listConnections(
            f"{uvpin_node}.coordinate[{center_raw_index}].coordinateU", source=True, destination=False
        )[0]

        #duplicar el locator del centro para usarlo como locator en global, no en local
        
        center_locator_global = cmds.duplicate(center_locator_name, n=f"{self.prefix}_lipProjectedGlobal_LOC")[0]
        #WIP: este grupo se tiene que constreñir al joint de la cabeza y el grupo de los controles de la boca generales tmb
        #global_locator_grp = cmds.group(n=f"{self.prefix}_lipGlobal_GRP", em=True)
        #cmds.parent(center_locator_global, global_locator_grp)
        
        cmds.connectAttr(f"{center_locator}.worldMatrix[0]", f"{center_locator_global}.offsetParentMatrix")

        #Conectar los grupos de upper y lower lip al locator global del centro mediante un constraint
        #(el locator es el driver: upper/lower lip siguen al centro, no al revés)
        if not cmds.listRelatives(upper_lip_grp, children=True, type="parentConstraint"):
            cmds.parentConstraint(center_locator_global, upper_lip_grp, mo=True)
        if not cmds.listRelatives(lower_lip_grp, children=True, type="parentConstraint"):
            cmds.parentConstraint(center_locator_global, lower_lip_grp, mo=True)
            
        # =========================================================
        # 4.5 LOS OFFSETS DE UPPER/LOWER SIGUEN AL LOCATOR DEL CENTRO
        # =========================================================
        if not cmds.listRelatives(upper_local_off, children=True, type="parentConstraint"):
            cmds.parentConstraint(center_locator_name, upper_local_off, mo=True)
        if not cmds.listRelatives(lower_local_off, children=True, type="parentConstraint"):
            cmds.parentConstraint(center_locator_name, lower_local_off, mo=True)
            
            
        # =========================================================
        # 5. CPS RAW DE ESTE LADO (L o R)
        # =========================================================
        end_local_off, end_local_trn, end_cps = self._build_cps_network(
            prefix=self.prefix, cps_name=f"{self.prefix}_lips_CPS",
            base_name="mouth", source_ctrl=end_lip, source_ctrl_grp=end_lip_grp
        )

        raw_index = self.RAW_INDEX[self.side]
        cmds.connectAttr(f"{end_cps}.result.parameterU", f"{uvpin_node}.coordinate[{raw_index}].coordinateU")
        cmds.connectAttr(f"{end_cps}.result.parameterV", f"{uvpin_node}.coordinate[{raw_index}].coordinateV")

        raw_locator = cmds.spaceLocator(name=f"{self.prefix}_lipProjected_LOC")[0]
        cmds.connectAttr(f"{uvpin_node}.outputMatrix[{raw_index}]", f"{raw_locator}.offsetParentMatrix")

        if self.side == "R":
            local_mirror_grp = cmds.group(em=True, n=f"{self.prefix}_mouthLocalMirror_GRP")
            cmds.setAttr(f"{local_mirror_grp}.scaleX", -1)
            cmds.parent(end_local_off, local_mirror_grp)
            cmds.matchTransform(end_local_off, end_lip, pos=True, rot=True)

        # =========================================================
        # 6. BLEND 01 y BLEND 02 (U y V) — este lado
        # =========================================================
        bta_u01 = self._create_blend_pair(self.prefix, "U", end_cps, center_cps, "01", f"{settings_grp}.HorizontalFollow01")
        bta_v01 = self._create_blend_pair(self.prefix, "V", end_cps, center_cps, "01", f"{settings_grp}.VerticalFollow01")
        bta_u02 = self._create_blend_pair(self.prefix, "U", end_cps, center_cps, "02", f"{settings_grp}.HorizontalFollow02")
        bta_v02 = self._create_blend_pair(self.prefix, "V", end_cps, center_cps, "02", f"{settings_grp}.VerticalFollow02")

        blend01_index = self.BLEND01_INDEX[self.side]
        cmds.connectAttr(f"{bta_u01}.output", f"{uvpin_node}.coordinate[{blend01_index}].coordinateU")
        cmds.connectAttr(f"{bta_v01}.output", f"{uvpin_node}.coordinate[{blend01_index}].coordinateV")
        locator01 = cmds.spaceLocator(name=f"{self.prefix}_lipProjected01_LOC")[0]
        cmds.connectAttr(f"{uvpin_node}.outputMatrix[{blend01_index}]", f"{locator01}.offsetParentMatrix")
        
        
        levator_name = f"{self.prefix}_levator_CTRL"
        if not cmds.objExists(levator_name):
            levator_ctrl = controlsLibrary.create_control_from_lib(
                lib_name=self.styles["mainFk"],
                final_name=levator_name
            )
            
            levator_ctrl_grp = self.group_maker.create_rig_hierarchy(
                levator_ctrl, locator01, match_rotation=True, world_space=True
            )
        else:
            levator_ctrl = levator_name
            levator_ctrl_grp = cmds.listRelatives(levator_ctrl, parent=True)[0]

        depresor_name = f"{self.prefix}_depresor_CTRL"
        if not cmds.objExists(depresor_name):
            depresor_ctrl = controlsLibrary.create_control_from_lib(
                lib_name=self.styles["mainFk"],
                final_name=depresor_name
            )
            
            depresor_ctrl_grp = self.group_maker.create_rig_hierarchy(
                depresor_ctrl, locator01, match_rotation=True, world_space=True
            )
            depresor_negative = cmds.group(depresor_ctrl_grp, n=f"{self.prefix}_depresor_negative_GRP")
            cmds.setAttr(f"{self.prefix}_depresor_negative_GRP.scaleY", -1)
            cmds.parent(depresor_ctrl_grp, depresor_negative)
        else:
            depresor_ctrl = depresor_name
            depresor_ctrl_grp = cmds.listRelatives(depresor_ctrl, parent=True)[0]

        # =========================================================
        # 6.5 SETUP DE OFF/TRN + JOINTS PARA LEVATOR Y DEPRESOR (ambos sides)
        # =========================================================
        levator_off_name = f"{self.prefix}_levatorLocal_OFF"
        levator_trn_name = f"{self.prefix}_levatorLocal_TRN"
        if not cmds.objExists(levator_off_name):
            levator_local_off, levator_local_trn = self._build_off_network(
                prefix=self.prefix, base_name="levator",
                source_ctrl=levator_ctrl, source_ctrl_grp=levator_ctrl_grp
            )
        else:
            levator_local_off, levator_local_trn = levator_off_name, levator_trn_name

        levator_joint_name = f"{self.prefix}_levator_JNT"
        if not cmds.objExists(levator_joint_name):
            cmds.select(clear=True)
            levator_joint = cmds.joint(n=levator_joint_name)
            cmds.matchTransform(levator_joint, levator_ctrl_grp, pos=True, rot=True)
            cmds.parentConstraint(levator_local_trn, levator_joint, mo=True)
            cmds.select(clear=True)
        else:
            levator_joint = levator_joint_name

        depresor_off_name = f"{self.prefix}_depresorLocal_OFF"
        depresor_trn_name = f"{self.prefix}_depresorLocal_TRN"
        if not cmds.objExists(depresor_off_name):
            depresor_local_off, depresor_local_trn = self._build_off_network(
                prefix=self.prefix, base_name="depresor",
                source_ctrl=depresor_ctrl, source_ctrl_grp=depresor_ctrl_grp
            )
            cmds.setAttr(f"{depresor_local_off}.scaleY", -1)
            cmds.setAttr(f"{depresor_local_off}.scaleX", -1)
            cmds.setAttr(f"{depresor_local_off}.scaleZ", -1)



        else:
            depresor_local_off, depresor_local_trn = depresor_off_name, depresor_trn_name

        depresor_joint_name = f"{self.prefix}_depresor_JNT"
        if not cmds.objExists(depresor_joint_name):
            cmds.select(clear=True)
            depresor_joint = cmds.joint(n=depresor_joint_name)
            cmds.matchTransform(depresor_joint, depresor_ctrl_grp, pos=True, rot=True)
            cmds.parentConstraint(depresor_local_trn, depresor_joint, mo=True)
            cmds.select(clear=True)
        else:
            depresor_joint = depresor_joint_name

        blend02_index = self.BLEND02_INDEX[self.side]
        cmds.connectAttr(f"{bta_u02}.output", f"{uvpin_node}.coordinate[{blend02_index}].coordinateU")
        cmds.connectAttr(f"{bta_v02}.output", f"{uvpin_node}.coordinate[{blend02_index}].coordinateV")
        locator02 = cmds.spaceLocator(name=f"{self.prefix}_lipProjected02_LOC")[0]
        cmds.connectAttr(f"{uvpin_node}.outputMatrix[{blend02_index}]", f"{locator02}.offsetParentMatrix")

        # =========================================================
        # 6.6 CONTROLES UPPERPINCH Y LOWERPINCH (sobre locator02, ambos sides)
        # Mismo patrón que levator/depresor pero anclados al lipProjected02
        # =========================================================
        upperPinch_name = f"{self.prefix}_upperPinch_CTRL"
        if not cmds.objExists(upperPinch_name):
            upperPinch_ctrl = controlsLibrary.create_control_from_lib(
                lib_name=self.styles["mainFk"],
                final_name=upperPinch_name
            )

            upperPinch_ctrl_grp = self.group_maker.create_rig_hierarchy(
                upperPinch_ctrl, locator02, match_rotation=True, world_space=True
            )
        else:
            upperPinch_ctrl = upperPinch_name
            upperPinch_ctrl_grp = cmds.listRelatives(upperPinch_ctrl, parent=True)[0]

        lowerPinch_name = f"{self.prefix}_lowerPinch_CTRL"
        if not cmds.objExists(lowerPinch_name):
            lowerPinch_ctrl = controlsLibrary.create_control_from_lib(
                lib_name=self.styles["mainFk"],
                final_name=lowerPinch_name
            )

            lowerPinch_ctrl_grp = self.group_maker.create_rig_hierarchy(
                lowerPinch_ctrl, locator02, match_rotation=True, world_space=True
            )
            lowerPinch_negative = cmds.group(lowerPinch_ctrl_grp, n=f"{self.prefix}_lowerPinch_negative_GRP")
            cmds.setAttr(f"{self.prefix}_lowerPinch_negative_GRP.scaleY", -1)
            cmds.parent(lowerPinch_ctrl_grp, lowerPinch_negative)
        else:
            lowerPinch_ctrl = lowerPinch_name
            lowerPinch_ctrl_grp = cmds.listRelatives(lowerPinch_ctrl, parent=True)[0]

        # =========================================================
        # 6.7 SETUP DE OFF/TRN + JOINTS PARA UPPERPINCH Y LOWERPINCH (ambos sides)
        # =========================================================
        upperPinch_off_name = f"{self.prefix}_upperPinchLocal_OFF"
        upperPinch_trn_name = f"{self.prefix}_upperPinchLocal_TRN"
        if not cmds.objExists(upperPinch_off_name):
            upperPinch_local_off, upperPinch_local_trn = self._build_off_network(
                prefix=self.prefix, base_name="upperPinch",
                source_ctrl=upperPinch_ctrl, source_ctrl_grp=upperPinch_ctrl_grp
            )
        else:
            upperPinch_local_off, upperPinch_local_trn = upperPinch_off_name, upperPinch_trn_name

        upperPinch_joint_name = f"{self.prefix}_upperPinch_JNT"
        if not cmds.objExists(upperPinch_joint_name):
            cmds.select(clear=True)
            upperPinch_joint = cmds.joint(n=upperPinch_joint_name)
            cmds.matchTransform(upperPinch_joint, upperPinch_ctrl_grp, pos=True, rot=True)
            cmds.parentConstraint(upperPinch_local_trn, upperPinch_joint, mo=True)
            cmds.select(clear=True)
        else:
            upperPinch_joint = upperPinch_joint_name

        lowerPinch_off_name = f"{self.prefix}_lowerPinchLocal_OFF"
        lowerPinch_trn_name = f"{self.prefix}_lowerPinchLocal_TRN"
        if not cmds.objExists(lowerPinch_off_name):
            lowerPinch_local_off, lowerPinch_local_trn = self._build_off_network(
                prefix=self.prefix, base_name="lowerPinch",
                source_ctrl=lowerPinch_ctrl, source_ctrl_grp=lowerPinch_ctrl_grp
            )
            cmds.setAttr(f"{lowerPinch_local_off}.scaleY", -1)
            cmds.setAttr(f"{lowerPinch_local_off}.scaleX", -1)
            cmds.setAttr(f"{lowerPinch_local_off}.scaleZ", -1)
        else:
            lowerPinch_local_off, lowerPinch_local_trn = lowerPinch_off_name, lowerPinch_trn_name

        lowerPinch_joint_name = f"{self.prefix}_lowerPinch_JNT"
        if not cmds.objExists(lowerPinch_joint_name):
            cmds.select(clear=True)
            lowerPinch_joint = cmds.joint(n=lowerPinch_joint_name)
            cmds.matchTransform(lowerPinch_joint, lowerPinch_ctrl_grp, pos=True, rot=True)
            cmds.parentConstraint(lowerPinch_local_trn, lowerPinch_joint, mo=True)
            cmds.select(clear=True)
        else:
            lowerPinch_joint = lowerPinch_joint_name

        #if self.side == "R":
            #mirror_behavior_grp = f"{self.root_instance.rig_name}_mirrorBehaviour_GRP"
            #if cmds.objExists(mirror_behavior_grp):
                #cmds.parent(levator_ctrl_grp,depresor_ctrl_grp, mirror_behavior_grp)
                #cmds.setAttr(f"{levator_ctrl_grp}.scaleX", -1)
                #cmds.setAttr(f"{levator_ctrl_grp}.scaleY", 1)
                #cmds.setAttr(f"{levator_ctrl_grp}.scaleZ", 1)
                #cmds.setAttr(f"{depresor_ctrl_grp}.scaleX", -1)
                #cmds.setAttr(f"{depresor_ctrl_grp}.scaleY", 1)
                #cmds.setAttr(f"{depresor_ctrl_grp}.scaleZ", 1)

        # =========================================================
        # LIP CENTER OF PROJECTION + AIM MATRIX + MAYA MUSCLE KEEP OUT
        # =========================================================
        # El locator de proyeccion es UNICO y central: se crea en la primera
        # llamada a build() y las siguientes lo reutilizan.
        # Lo que se repite por lado es el aim locator + su keepOut: los tres
        # (C, L, R) nacen en la MISMA posicion y solo cambia su orientacion,
        # porque son tres rayos que salen del mismo punto de proyeccion.
        # El keepOut de cada uno lo desliza por su propia Z hasta sacarlo
        # de la nurbs.

        # nurb_locator_name = f"C_{self.rig_name}_lipCenterOfProjection_LOC"
        # if not cmds.objExists(nurb_locator_name):
        #     nurbCenter_locator = cmds.spaceLocator(name=nurb_locator_name)[0]
        #     cmds.matchTransform(nurbCenter_locator, center_locator, pos=True, rot=True)
        #     cmds.setAttr(f"{nurbCenter_locator}.translateZ", 6)
        # else:
        #     nurbCenter_locator = nurb_locator_name

        # # La nurbs se convierte a Muscle Object una sola vez (es compartida).
        # surface_trn, muscle_shape = self._get_or_create_muscle_surface()

        # # --- C: apunta al tracker local del centro ---
        # # Si aun no existe caemos al locator proyectado del centro.
        # center_target = f"C_{self.rig_name}_mouthCenterLocal_TRN"
        # if not cmds.objExists(center_target):
        #     center_target = center_locator_name

        # self._build_projection_aim_keepout(
        #     side_code="C",
        #     nurb_center_locator=nurbCenter_locator,
        #     target_node=center_target,
        #     surface_trn=surface_trn,
        # )

        # # --- Lado actual (L o R): apunta a la comisura de este lado ---
        # aimCenter_locator = self._build_projection_aim_keepout(
        #     side_code=self.side,
        #     nurb_center_locator=nurbCenter_locator,
        #     target_node=end_local_trn,
        #     surface_trn=surface_trn,
        # )

            
        # =========================================================
        #Creacion de los joints
        # =========================================================
        cmds.select(clear=True)

        upper_joint_name = f"C_{self.rig_name}_lipUpper_JNT"
        if not cmds.objExists(upper_joint_name):
            upper_joint = cmds.joint(n=upper_joint_name)
            cmds.matchTransform(upper_joint, upper_lip_grp, pos=True, rot=True)
            if cmds.objExists(upper_local_trn):
                cmds.parentConstraint(upper_local_trn, upper_joint, mo=True)
            else:
                cmds.warning(f"MouthModule: no se pudo crear el parentConstraint de {upper_joint}, "
                              f"'{upper_local_trn}' no existe en la escena.")
            cmds.select(clear=True)
        else:
            upper_joint = upper_joint_name

        lower_joint_name = f"C_{self.rig_name}_lipLower_JNT"
        if not cmds.objExists(lower_joint_name):
            lower_joint = cmds.joint(n=lower_joint_name)
            cmds.matchTransform(lower_joint, lower_lip_grp, pos=True, rot=True)
            if cmds.objExists(lower_local_trn):
                cmds.parentConstraint(lower_local_trn, lower_joint, mo=True)
            else:
                cmds.warning(f"MouthModule: no se pudo crear el parentConstraint de {lower_joint}, "
                              f"'{lower_local_trn}' no existe en la escena.")
            cmds.select(clear=True)
        else:
            lower_joint = lower_joint_name

        
        
        freeze_joint_name = f"C_{self.rig_name}_freeze_JNT"
        if not cmds.objExists(freeze_joint_name):
            freeze_joint = cmds.joint(n=freeze_joint_name)
        else:
            freeze_joint = freeze_joint_name
            

        # =========================================================
        # 7. CURVA DE CURVATURA DE LOS LABIOS
        # Solo se construye de verdad cuando ya existen los 7 locators
        # (es decir, en la llamada de build() del segundo lado).
        # =========================================================
        self._build_lip_curve()

        # =========================================================
        # 8. BIND SKIN de las curvas upper/lower — solo cuando la curva
        # ya existe (segunda llamada de build()) y todavía no tiene skinCluster
        # =========================================================
        upper_curve_name = f"C_{self.rig_name}_lipUpperLine_CRV"
        lower_curve_name = f"C_{self.rig_name}_lipLowerLine_CRV"

        upperSkinning = None
        lowerSkinning = None

        if cmds.objExists(upper_curve_name):
            existing_upper_skin = cmds.listConnections(upper_curve_name, type="skinCluster")
            if not existing_upper_skin:
                upperSkinning = cmds.skinCluster(
                    freeze_joint, upper_joint, upper_curve_name,
                    tsb=True, bm=0, sm=0, nw=1, wd=0, mi=1, dr=4.0
                )[0]
                cmds.connectAttr(f"{self.curve_transform}.worldSpace[0]", f"{upperSkinning}.input[0].inputGeometry", f=True)
                cmds.skinPercent(upperSkinning, f"{upper_curve_name}.cv[0]", transformValue=[(freeze_joint, 1.0)])
                cmds.skinPercent(upperSkinning, f"{upper_curve_name}.cv[6]", transformValue=[(freeze_joint, 1.0)])
                cmds.skinPercent(upperSkinning, f"{upper_curve_name}.cv[1]", transformValue=[(freeze_joint, 0.5)])
                cmds.skinPercent(upperSkinning, f"{upper_curve_name}.cv[5]", transformValue=[(freeze_joint, 0.5)])
            else:
                upperSkinning = existing_upper_skin[0]

        # La curva original (lipProjected, alimentada por un decomposeMatrix por
        # cada locator) conecta su worldSpace (global) al originalGeometry[0]
        # del primer skinCluster creado (Upper).
        if upperSkinning and cmds.objExists(self.curve_transform):
            src = f"{self.curve_transform}.worldSpace[0]"
            dst = f"{upperSkinning}.originalGeometry[0]"
            if not cmds.isConnected(src, dst):
                cmds.connectAttr(src, dst, force=True)

        self._connect_freeze_lock_weights(freeze_joint, upperSkinning)
        self._connect_joint_lock_weights(upper_joint, upperSkinning)

        if cmds.objExists(lower_curve_name):
            existing_lower_skin = cmds.listConnections(lower_curve_name, type="skinCluster")
            if not existing_lower_skin:
                lowerSkinning = cmds.skinCluster(
                    freeze_joint, lower_joint, lower_curve_name,
                    tsb=True, bm=0, sm=0, nw=1, wd=0, mi=1, dr=4.0
                )[0]
                cmds.connectAttr(f"{self.curve_transform}.worldSpace[0]", f"{lowerSkinning}.input[0].inputGeometry", f=True)
                cmds.skinPercent(lowerSkinning, f"{lower_curve_name}.cv[0]", transformValue=[(freeze_joint, 1.0)])
                cmds.skinPercent(lowerSkinning, f"{lower_curve_name}.cv[6]", transformValue=[(freeze_joint, 1.0)])
                cmds.skinPercent(lowerSkinning, f"{lower_curve_name}.cv[1]", transformValue=[(freeze_joint, 0.5)])
                cmds.skinPercent(lowerSkinning, f"{lower_curve_name}.cv[5]", transformValue=[(freeze_joint, 0.5)])
            else:
                lowerSkinning = existing_lower_skin[0]

        # La curva original (lipProjected) también debe alimentar el
        # originalGeometry[0] del skinCluster de Lower (mismo criterio que Upper).
        if lowerSkinning and cmds.objExists(self.curve_transform):
            src = f"{self.curve_transform}.worldSpace[0]"
            dst = f"{lowerSkinning}.originalGeometry[0]"
            if not cmds.isConnected(src, dst):
                cmds.connectAttr(src, dst, force=True)

        self._connect_freeze_lock_weights(freeze_joint, lowerSkinning)
        self._connect_joint_lock_weights(lower_joint, lowerSkinning)

        # --- BIND SKIN de las curvas de levator / depresor / upperPinch / lowerPinch ---
        # Mismo sistema que upper/lower, pero cada curva es compartida entre L y R,
        # asi que los joints influencia son freeze_joint + el joint de cada lado.
        levator_curve_name = f"C_{self.rig_name}_lipCurvatureLevator_CRV"
        depresor_curve_name = f"C_{self.rig_name}_lipCurvatureDepresor_CRV"
        upperPinch_curve_name = f"C_{self.rig_name}_lipCurvatureUpperPinch_CRV"
        lowerPinch_curve_name = f"C_{self.rig_name}_lipCurvatureLowerPinch_CRV"

        L_levator_joint = f"L_{self.rig_name}_levator_JNT"
        R_levator_joint = f"R_{self.rig_name}_levator_JNT"
        L_depresor_joint = f"L_{self.rig_name}_depresor_JNT"
        R_depresor_joint = f"R_{self.rig_name}_depresor_JNT"
        L_upperPinch_joint = f"L_{self.rig_name}_upperPinch_JNT"
        R_upperPinch_joint = f"R_{self.rig_name}_upperPinch_JNT"
        L_lowerPinch_joint = f"L_{self.rig_name}_lowerPinch_JNT"
        R_lowerPinch_joint = f"R_{self.rig_name}_lowerPinch_JNT"

        levatorSkinning = None
        depresorSkinning = None
        upperPinchSkinning = None
        lowerPinchSkinning = None

        if cmds.objExists(levator_curve_name) and cmds.objExists(L_levator_joint) and cmds.objExists(R_levator_joint):
            existing_levator_skin = cmds.listConnections(levator_curve_name, type="skinCluster")
            if not existing_levator_skin:
                levatorSkinning = cmds.skinCluster(
                    freeze_joint, L_levator_joint, R_levator_joint, levator_curve_name,
                    tsb=True, bm=0, sm=0, nw=1, wd=0, mi=1, dr=4.0
                )[0]
                cmds.skinPercent(levatorSkinning, f"{levator_curve_name}.cv[0]", transformValue=[(freeze_joint, 1.0)])
                cmds.skinPercent(levatorSkinning, f"{levator_curve_name}.cv[6]", transformValue=[(freeze_joint, 1.0)])
                cmds.skinPercent(levatorSkinning, f"{levator_curve_name}.cv[1]", transformValue=[(freeze_joint, 0.5), (L_levator_joint, 0.5)])
                cmds.skinPercent(levatorSkinning, f"{levator_curve_name}.cv[5]", transformValue=[(freeze_joint, 0.5), (R_levator_joint, 0.5)])
            else:
                levatorSkinning = existing_levator_skin[0]

        # Levator hereda la deformación ya resuelta de Upper (cadena Upper -> Levator -> UpperPinch)
        self._chain_curve_into_skincluster(upper_curve_name, levatorSkinning)
        self._connect_freeze_lock_weights(freeze_joint, levatorSkinning)
        self._connect_joint_lock_weights(L_levator_joint, levatorSkinning)
        self._connect_joint_lock_weights(R_levator_joint, levatorSkinning)

        if cmds.objExists(depresor_curve_name) and cmds.objExists(L_depresor_joint) and cmds.objExists(R_depresor_joint):
            existing_depresor_skin = cmds.listConnections(depresor_curve_name, type="skinCluster")
            if not existing_depresor_skin:
                depresorSkinning = cmds.skinCluster(
                    freeze_joint, L_depresor_joint, R_depresor_joint, depresor_curve_name,
                    tsb=True, bm=0, sm=0, nw=1, wd=0, mi=1, dr=4.0
                )[0]
                cmds.skinPercent(depresorSkinning, f"{depresor_curve_name}.cv[0]", transformValue=[(freeze_joint, 1.0)])
                cmds.skinPercent(depresorSkinning, f"{depresor_curve_name}.cv[6]", transformValue=[(freeze_joint, 1.0)])
                cmds.skinPercent(depresorSkinning, f"{depresor_curve_name}.cv[1]", transformValue=[(freeze_joint, 0.5), (L_depresor_joint, 0.5)])
                cmds.skinPercent(depresorSkinning, f"{depresor_curve_name}.cv[5]", transformValue=[(freeze_joint, 0.5), (R_depresor_joint, 0.5)])
            else:
                depresorSkinning = existing_depresor_skin[0]

        # Depresor hereda la deformación ya resuelta de Lower (cadena Lower -> Depresor -> LowerPinch)
        self._chain_curve_into_skincluster(lower_curve_name, depresorSkinning)
        self._connect_freeze_lock_weights(freeze_joint, depresorSkinning)
        self._connect_joint_lock_weights(L_depresor_joint, depresorSkinning)
        self._connect_joint_lock_weights(R_depresor_joint, depresorSkinning)

        if cmds.objExists(upperPinch_curve_name) and cmds.objExists(L_upperPinch_joint) and cmds.objExists(R_upperPinch_joint):
            existing_upperPinch_skin = cmds.listConnections(upperPinch_curve_name, type="skinCluster")
            if not existing_upperPinch_skin:
                upperPinchSkinning = cmds.skinCluster(
                    freeze_joint, L_upperPinch_joint, R_upperPinch_joint, upperPinch_curve_name,
                    tsb=True, bm=0, sm=0, nw=1, wd=0, mi=1, dr=4.0
                )[0]
                cmds.skinPercent(upperPinchSkinning, f"{upperPinch_curve_name}.cv[0]", transformValue=[(freeze_joint, 1.0)])
                cmds.skinPercent(upperPinchSkinning, f"{upperPinch_curve_name}.cv[6]", transformValue=[(freeze_joint, 1.0)])
                cmds.skinPercent(upperPinchSkinning, f"{upperPinch_curve_name}.cv[1]", transformValue=[(freeze_joint, 0.5), (L_upperPinch_joint, 0.5)])
                cmds.skinPercent(upperPinchSkinning, f"{upperPinch_curve_name}.cv[5]", transformValue=[(freeze_joint, 0.5), (R_upperPinch_joint, 0.5)])
            else:
                upperPinchSkinning = existing_upperPinch_skin[0]

        # UpperPinch hereda la deformación ya resuelta de Levator
        self._chain_curve_into_skincluster(levator_curve_name, upperPinchSkinning)
        self._connect_freeze_lock_weights(freeze_joint, upperPinchSkinning)
        self._connect_joint_lock_weights(L_upperPinch_joint, upperPinchSkinning)
        self._connect_joint_lock_weights(R_upperPinch_joint, upperPinchSkinning)

        if cmds.objExists(lowerPinch_curve_name) and cmds.objExists(L_lowerPinch_joint) and cmds.objExists(R_lowerPinch_joint):
            existing_lowerPinch_skin = cmds.listConnections(lowerPinch_curve_name, type="skinCluster")
            if not existing_lowerPinch_skin:
                lowerPinchSkinning = cmds.skinCluster(
                    freeze_joint, L_lowerPinch_joint, R_lowerPinch_joint, lowerPinch_curve_name,
                    tsb=True, bm=0, sm=0, nw=1, wd=0, mi=1, dr=4.0
                )[0]
                cmds.skinPercent(lowerPinchSkinning, f"{lowerPinch_curve_name}.cv[0]", transformValue=[(freeze_joint, 1.0)])
                cmds.skinPercent(lowerPinchSkinning, f"{lowerPinch_curve_name}.cv[6]", transformValue=[(freeze_joint, 1.0)])
                cmds.skinPercent(lowerPinchSkinning, f"{lowerPinch_curve_name}.cv[1]", transformValue=[(freeze_joint, 0.5), (L_lowerPinch_joint, 0.5)])
                cmds.skinPercent(lowerPinchSkinning, f"{lowerPinch_curve_name}.cv[5]", transformValue=[(freeze_joint, 0.5), (R_lowerPinch_joint, 0.5)])
            else:
                lowerPinchSkinning = existing_lowerPinch_skin[0]

        # LowerPinch hereda la deformación ya resuelta de Depresor
        self._chain_curve_into_skincluster(depresor_curve_name, lowerPinchSkinning)
        self._connect_freeze_lock_weights(freeze_joint, lowerPinchSkinning)
        self._connect_joint_lock_weights(L_lowerPinch_joint, lowerPinchSkinning)
        self._connect_joint_lock_weights(R_lowerPinch_joint, lowerPinchSkinning)

        cmds.select(clear=True)

        upperPrebind_joint_name = f"C_{self.rig_name}_lipUpperPreBind_JNT"
        if not cmds.objExists(upperPrebind_joint_name):
            upperPrebind_joint = cmds.joint(n=upperPrebind_joint_name)
            cmds.matchTransform(upperPrebind_joint, upper_joint, pos=True, rot=True)
            cmds.select(clear=True)
        else:
            upperPrebind_joint = upperPrebind_joint_name

        if not cmds.listRelatives(upperPrebind_joint, children=True, type="parentConstraint"):
            cmds.parentConstraint(center_locator_name, upperPrebind_joint, mo=True)

        if upperSkinning:
            self._connect_prebind_to_skincluster(upperSkinning, upper_joint, upperPrebind_joint)

        lowerPrebind_joint_name = f"C_{self.rig_name}_lipLowerPreBind_JNT"
        if not cmds.objExists(lowerPrebind_joint_name):
            lowerPrebind_joint = cmds.joint(n=lowerPrebind_joint_name)
            cmds.matchTransform(lowerPrebind_joint, lower_joint, pos=True, rot=True)
            cmds.select(clear=True)
        else:
            lowerPrebind_joint = lowerPrebind_joint_name

        if not cmds.listRelatives(lowerPrebind_joint, children=True, type="parentConstraint"):
            cmds.parentConstraint(center_locator_name, lowerPrebind_joint, mo=True)

        if lowerSkinning:
            self._connect_prebind_to_skincluster(lowerSkinning, lower_joint, lowerPrebind_joint)
            
        # =========================================================
        # 9. CREACIÓN DE TRACKERS / MOTION PATHS Y CONSTRAINTS
        # =========================================================
        if (cmds.objExists(upper_curve_name) and cmds.objExists(lower_curve_name)
                and cmds.objExists(levator_curve_name) and cmds.objExists(depresor_curve_name)):
            u_levator_L = 0.25
            u_depresor_L = 0.25

            # --- UPPER / LEVATORES ---
            # Levator L
            _, tracker_upper_L = self._get_or_create_curve_motion_locator(
                curve_name=upper_curve_name, base_name="levatorFollow", u_value=u_levator_L, side="L"
            )
            # Levator R
            _, tracker_upper_R = self._get_or_create_curve_motion_locator(
                curve_name=upper_curve_name, base_name="levatorFollow", u_value=1.0 - u_levator_L, side="R"
            )

            # --- LOWER / DEPRESORES ---
            # Depresor L
            _, tracker_lower_L = self._get_or_create_curve_motion_locator(
                curve_name=lower_curve_name, base_name="depresorFollow", u_value=u_depresor_L, side="L"
            )
            # Depresor R
            _, tracker_lower_R = self._get_or_create_curve_motion_locator(
                curve_name=lower_curve_name, base_name="depresorFollow", u_value=1.0 - u_depresor_L, side="R"
            )

            # --- CONEXIÓN / PARENT CONSTRAINT A LOS GRUPOS DE CONTROLES ---
            for side_code in ["L", "R"]:
                prefix_side = f"{side_code}_{self.rig_name}"
                
                # Nombres de los Global Trackers creados
                upper_global_loc = f"{prefix_side}_levatorFollow_trackerGlobal_LOC"
                lower_global_loc = f"{prefix_side}_depresorFollow_trackerGlobal_LOC"

                # Nombres de los Trackers LOCALES creados
                upper_local_loc = f"{prefix_side}_levatorFollow_tracker_LOC"
                lower_local_loc = f"{prefix_side}_depresorFollow_tracker_LOC"

                # Nombres de los controles
                levator_ctrl = f"{prefix_side}_levator_CTRL"
                depresor_ctrl = f"{prefix_side}_depresor_CTRL"

                # 1. LEVATOR: Apuntamos directamente al grupo raíz principal (_GRP)
                levator_grp = f"{prefix_side}_levator_GRP"
                if cmds.objExists(levator_grp):
                    if not cmds.listRelatives(levator_grp, type="parentConstraint"):
                        cmds.parentConstraint(upper_global_loc, levator_grp, mo=True)

                    # --- OFF LOCAL DEL LEVATOR: lo conduce el Tracker LOCAL ---
                    levator_off = f"{prefix_side}_levatorLocal_OFF"
                    if cmds.objExists(levator_off) and cmds.objExists(upper_local_loc):
                        if not cmds.listRelatives(levator_off, type="parentConstraint"):
                            cmds.parentConstraint(upper_local_loc, levator_off, mo=True)

                    # --- PREBIND DEL LEVATOR (conducido por el Tracker LOCAL) ---
                    levator_joint_side = f"{prefix_side}_levator_JNT"
                    levatorPrebind_name = f"{prefix_side}_levatorPreBind_JNT"
                    self._setup_prebind_joint(
                        prebind_name=levatorPrebind_name,
                        source_joint=levator_joint_side,
                        driver_target=upper_local_loc
                    )

                # 2. DEPRESOR: Si existe el grupo negativo usamos ese, si no el _GRP principal
                if cmds.objExists(depresor_ctrl):
                    neg_grp = f"{prefix_side}_depresor_negative_GRP"
                    depresor_grp = f"{prefix_side}_depresor_GRP"
                    target_depresor_grp = neg_grp if cmds.objExists(neg_grp) else depresor_grp

                    if cmds.objExists(target_depresor_grp):
                        if not cmds.listRelatives(target_depresor_grp, type="parentConstraint"):
                            cmds.parentConstraint(lower_global_loc, target_depresor_grp, mo=True)

                    # --- OFF LOCAL DEL DEPRESOR: lo conduce el Tracker LOCAL ---
                    depresor_off = f"{prefix_side}_depresorLocal_OFF"
                    if cmds.objExists(depresor_off) and cmds.objExists(lower_local_loc):
                        if not cmds.listRelatives(depresor_off, type="parentConstraint"):
                            cmds.parentConstraint(lower_local_loc, depresor_off, mo=True)

                    # --- PREBIND DEL DEPRESOR (conducido por el Tracker LOCAL) ---
                    depresor_joint_side = f"{prefix_side}_depresor_JNT"
                    depresorPrebind_name = f"{prefix_side}_depresorPreBind_JNT"
                    self._setup_prebind_joint(
                        prebind_name=depresorPrebind_name,
                        source_joint=depresor_joint_side,
                        driver_target=lower_local_loc
                    )

            # --- UPPERPINCH / LOWERPINCH ----
            # UpperPinch va DESPUÉS de Levator en la cadena (Upper -> Levator -> UpperPinch),
            # así que su tracker debe leer el world space de la curva Levator (la anterior),
            # no de Upper. Igual para LowerPinch con Depresor (Lower -> Depresor -> LowerPinch).
            u_pinch_L = 0.1

            # Upper pinch L
            _, tracker_upperPinch_L = self._get_or_create_curve_motion_locator(
                curve_name=levator_curve_name, base_name="upperPinchFollow", u_value=u_pinch_L, side="L"
            )
            # Upper pinch R
            _, tracker_upperPinch_R = self._get_or_create_curve_motion_locator(
                curve_name=levator_curve_name, base_name="upperPinchFollow", u_value=1.0 - u_pinch_L, side="R"
            )

            # Lower pinch L
            _, tracker_lowerPinch_L = self._get_or_create_curve_motion_locator(
                curve_name=depresor_curve_name, base_name="lowerPinchFollow", u_value=u_pinch_L, side="L"
            )
            # Lower pinch R
            _, tracker_lowerPinch_R = self._get_or_create_curve_motion_locator(
                curve_name=depresor_curve_name, base_name="lowerPinchFollow", u_value=1.0 - u_pinch_L, side="R"
            )

            # --- CONEXIÓN / PARENT CONSTRAINT A LOS GRUPOS DE CONTROLES ---
            for side_code in ["L", "R"]:
                prefix_side = f"{side_code}_{self.rig_name}"

                # Nombres de los Global Trackers creados
                
                upperPinch_global_loc = f"{prefix_side}_upperPinchFollow_trackerGlobal_LOC"
                lowerPinch_global_loc = f"{prefix_side}_lowerPinchFollow_trackerGlobal_LOC"

                # Nombres de los Trackers LOCALES creados
                upperPinch_local_loc = f"{prefix_side}_upperPinchFollow_tracker_LOC"
                lowerPinch_local_loc = f"{prefix_side}_lowerPinchFollow_tracker_LOC"

                # Nombres de los controles
                lowerPinch_ctrl_name = f"{prefix_side}_lowerPinch_CTRL"

                # 1. UPPERPINCH: apuntamos directamente al grupo raíz principal (_GRP)
                upperPinch_grp = f"{prefix_side}_upperPinch_GRP"
                if cmds.objExists(upperPinch_grp):
                    if not cmds.listRelatives(upperPinch_grp, type="parentConstraint"):
                        cmds.parentConstraint(upperPinch_global_loc, upperPinch_grp, mo=True)

                    # --- OFF LOCAL DEL UPPERPINCH: lo conduce el Tracker LOCAL ---
                    upperPinch_off = f"{prefix_side}_upperPinchLocal_OFF"
                    if cmds.objExists(upperPinch_off) and cmds.objExists(upperPinch_local_loc):
                        if not cmds.listRelatives(upperPinch_off, type="parentConstraint"):
                            cmds.parentConstraint(upperPinch_local_loc, upperPinch_off, mo=True)

                    # --- PREBIND DEL UPPERPINCH (conducido por el Tracker LOCAL) ---
                    upperPinch_joint_side = f"{prefix_side}_upperPinch_JNT"
                    upperPinchPrebind_name = f"{prefix_side}_upperPinchPreBind_JNT"
                    self._setup_prebind_joint(
                        prebind_name=upperPinchPrebind_name,
                        source_joint=upperPinch_joint_side,
                        driver_target=upperPinch_local_loc
                    )

                # 2. LOWERPINCH: si existe el grupo negativo usamos ese, si no el _GRP principal
                if cmds.objExists(lowerPinch_ctrl_name):
                    neg_grp = f"{prefix_side}_lowerPinch_negative_GRP"
                    lowerPinch_grp = f"{prefix_side}_lowerPinch_GRP"
                    target_lowerPinch_grp = neg_grp if cmds.objExists(neg_grp) else lowerPinch_grp

                    if cmds.objExists(target_lowerPinch_grp):
                        if not cmds.listRelatives(target_lowerPinch_grp, type="parentConstraint"):
                            cmds.parentConstraint(lowerPinch_global_loc, target_lowerPinch_grp, mo=True)

                    # --- OFF LOCAL DEL LOWERPINCH: lo conduce el Tracker LOCAL ---
                    lowerPinch_off = f"{prefix_side}_lowerPinchLocal_OFF"
                    if cmds.objExists(lowerPinch_off) and cmds.objExists(lowerPinch_local_loc):
                        if not cmds.listRelatives(lowerPinch_off, type="parentConstraint"):
                            cmds.parentConstraint(lowerPinch_local_loc, lowerPinch_off, mo=True)

                    # --- PREBIND DEL LOWERPINCH (conducido por el Tracker LOCAL) ---
                    lowerPinch_joint_side = f"{prefix_side}_lowerPinch_JNT"
                    lowerPinchPrebind_name = f"{prefix_side}_lowerPinchPreBind_JNT"
                    self._setup_prebind_joint(
                        prebind_name=lowerPinchPrebind_name,
                        source_joint=lowerPinch_joint_side,
                        driver_target=lowerPinch_local_loc
                    )

        return mid_lip_grp, end_lip_grp, end_local_off, end_local_trn