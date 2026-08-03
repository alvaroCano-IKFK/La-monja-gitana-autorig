import maya.cmds as cmds    
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

    def _get_ordered_lip_locator_names(self):
        """
        Orden de comisura a comisura: L_raw -> L_02 -> L_01 -> C -> R_01 -> R_02 -> R_raw.
        Coincide 1 a 1 con los 7 coordinate[]/outputMatrix[] del uvPin compartido.
        """
        L = f"L_{self.rig_name}"
        R = f"R_{self.rig_name}"
        C = f"C_{self.rig_name}"
        return [
            f"{L}_lipProjected_LOC",
            f"{L}_lipProjected02_LOC",
            f"{L}_lipProjected01_LOC",
            f"{C}_lipProjected_LOC",
            f"{R}_lipProjected01_LOC",
            f"{R}_lipProjected02_LOC",
            f"{R}_lipProjected_LOC",
        ]

    def _build_lip_curve(self):
        """
        Crea (una única vez) la curva de curvatura de los labios:
        1. Curva de grado 1 con un CV en la posición de cada locator (7 CVs).
        2. rebuildCurve a grado 3, 4 spans (4+3 = 7 CVs -> mismo conteo, misma correspondencia 1 a 1).
        3. Cada locator queda conectado a (gestiona en vivo) el CV que ocupa su posición.

        Solo se construye cuando existen los 7 locators (L, R y centro), es decir,
        cuando ya se ha llamado a build() en ambos lados. Si aún faltan, no hace nada.
        """
        curve_name = f"C_{self.rig_name}_lipCurvature_CRV"
        if cmds.objExists(curve_name):
            return curve_name

        ordered_locators = self._get_ordered_lip_locator_names()
        if not all(cmds.objExists(loc) for loc in ordered_locators):
            # Todavía no existen los locators de los dos lados; se construirá
            # cuando se llame a build() en el lado que falta.
            return None

        positions = [cmds.xform(loc, q=True, ws=True, t=True) for loc in ordered_locators]

        curve_transform = cmds.curve(d=1, p=positions, n=curve_name)
        cmds.rebuildCurve(
            curve_transform, ch=0, rpo=1, rt=0, end=1, kr=0, kcp=0, kep=1, kt=0,
            s=4, d=3, tol=0.01
        )
        cmds.setAttr(f"{curve_transform}.lineWidth", 3)

        curve_shape = cmds.listRelatives(curve_transform, shapes=True)[0]

        for cv_index, locator_name in enumerate(ordered_locators):
            cmds.connectAttr(f"{locator_name}.worldPosition[0]", f"{curve_shape}.controlPoints[{cv_index}]")
            
        if cmds.objExists(curve_transform):
            upperCurve = cmds.duplicate(curve_transform, n=f"{self.prefix}_lipCurvatureUpper_CRV")
        else:
            print(f"Warning: Curve {curve_transform} does not exist, cannot duplicate.")

        if cmds.objExists(curve_transform):
            lowerCurve = cmds.duplicate(curve_transform, n=f"{self.prefix}_lipCurvatureLower_CRV")
        else:
            print(f"Warning: Curve {curve_transform} does not exist, cannot duplicate.")
            
        cmds.connectAttr(f"{curve_transform}.worldSpace[0]", f"{upperCurve[0]}.create")
        cmds.connectAttr(f"{curve_transform}.worldSpace[0]", f"{lowerCurve[0]}.create")

        return curve_transform
    

    
    
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
            
        upper_lip_name = f"C_{self.prefix}_lipUpper_GRP"
        if not cmds.objExists(upper_lip_name):
            mid_lipUpper = controlsLibrary.create_control_from_lib(
                    lib_name=self.styles["mainFk"],
                    final_name=f"{self.prefix}_mid_lipUpper_CTRL"
            )
            mid_lipUpper = cmds.rename(mid_lipUpper, upper_lip_name)
            upper_lip_grp = self.group_maker.create_rig_hierarchy(
                    mid_lipUpper, self.lip_mid, match_rotation=True, world_space=True
            )
        else:
            mid_lipUpper = upper_lip_name
            upper_lip_grp = cmds.listRelatives(mid_lipUpper, parent=True)[0]
            
        upper_local_off, upper_local_trn = self._build_off_network(
                prefix=f"C_{self.rig_name}",
                base_name="mouthCenterUpper", source_ctrl=mid_lipUpper, source_ctrl_grp=upper_lip_grp
        )

        lower_lip_name = f"C_{self.prefix}_lipLower_GRP"
        if not cmds.objExists(lower_lip_name):
            mid_lipLower = controlsLibrary.create_control_from_lib(
                    lib_name=self.styles["mainFk"],
                    final_name=f"{self.prefix}_mid_lipLower_CTRL"
            )

            mid_lipLower = cmds.rename(mid_lipLower, lower_lip_name)
            lower_lip_grp = self.group_maker.create_rig_hierarchy(
                    mid_lipLower, self.lip_mid, match_rotation=True, world_space=True
            )
            cmds.setAttr(f"{lower_lip_grp}.scaleY", -1)
        else:
            mid_lipLower = lower_lip_name
            lower_lip_grp = cmds.listRelatives(mid_lipLower, parent=True)[0]



        # 2. CONTROL DE LA COMISURA (end_lip) — uno por lado
        end_lip = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["mainFk"],
            final_name=f"{self.prefix}_end_LIP_CTRL"
        )
        end_lip_grp = self.group_maker.create_rig_hierarchy(
            end_lip, self.lip_end, match_rotation=True, world_space=True
        )

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
        global_locator_grp = cmds.group(n=f"{self.prefix}_lipGlobal_GRP", em=True)
        cmds.parent(center_locator_global, global_locator_grp)
        
        cmds.connectAttr(f"{center_locator}.worldMatrix[0]", f"{center_locator_global}.offsetParentMatrix")

        #Conectar los grupos de upper y lower lip al locator global del centro mediante un constraint
        #(el locator es el driver: upper/lower lip siguen al centro, no al revés)
        if not cmds.listRelatives(upper_lip_grp, children=True, type="parentConstraint"):
            cmds.parentConstraint(center_locator_global, upper_lip_grp, mo=True)
        if not cmds.listRelatives(lower_lip_grp, children=True, type="parentConstraint"):
            cmds.parentConstraint(center_locator_global, lower_lip_grp, mo=True)
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

        blend02_index = self.BLEND02_INDEX[self.side]
        cmds.connectAttr(f"{bta_u02}.output", f"{uvpin_node}.coordinate[{blend02_index}].coordinateU")
        cmds.connectAttr(f"{bta_v02}.output", f"{uvpin_node}.coordinate[{blend02_index}].coordinateV")
        locator02 = cmds.spaceLocator(name=f"{self.prefix}_lipProjected02_LOC")[0]
        cmds.connectAttr(f"{uvpin_node}.outputMatrix[{blend02_index}]", f"{locator02}.offsetParentMatrix")

        #creamos el lipCenterOffProjection
        # Todo este bloque (locator + aimMatrix + cMuscleKeepOut) solo se crea
        # una vez, la primera vez que se llama a build() (lado L). En la
        # llamada del lado R, el locator ya existe: NO hacemos return aquí,
        # simplemente saltamos la creación y seguimos hasta el final del
        # método para que se pueda construir la curva (punto 7).
        nurb_locator_name = f"C_{self.rig_name}_lipCenterOffProjection_LOC"
        if not cmds.objExists(nurb_locator_name):
            nurbCenter_locator = cmds.spaceLocator(name=nurb_locator_name)[0]
            cmds.matchTransform(nurbCenter_locator, center_locator, pos=True, rot=True)
            cmds.setAttr(f"{nurbCenter_locator}.translateZ", 6 )

            aimCenter_locator_name = f"C_{self.rig_name}_lipCenterOffProjectionAim_LOC"
            aimCenter_locator = cmds.spaceLocator(name=aimCenter_locator_name)[0]

            aimMatrix_node = NodeCreator(
                side=f"C_{self.rig_name}", node_type="aimMatrix", base_name="mouth",
                name="Local", tag="CTRL", parent=None, custom_suffix=None
            ).create()

            cmds.connectAttr(f"{nurbCenter_locator}.worldMatrix[0]", f"{aimMatrix_node}.inputMatrix")
            cmds.connectAttr(f"{end_local_trn}.worldMatrix[0]", f"{aimMatrix_node}.primaryTargetMatrix")
            cmds.setAttr(f"{aimMatrix_node}.primaryMode", 1)  # 1 = Aim
            cmds.setAttr(f"{aimMatrix_node}.primaryInputAxisX", 0)
            cmds.setAttr(f"{aimMatrix_node}.primaryInputAxisZ", 1)
            cmds.setAttr(f"{aimMatrix_node}.secondaryMode", 1)
            cmds.setAttr(f"{aimMatrix_node}.secondaryTargetVectorY", 1)
            cmds.connectAttr(f"{aimMatrix_node}.outputMatrix", f"{aimCenter_locator}.offsetParentMatrix")

            cMuscleKeepOut_node = NodeCreator(
                side=f"C_{self.rig_name}", node_type="cMuscleKeepOut", base_name="mouth",
                name="Local", tag="CTRL", parent=None, custom_suffix=None
            ).create()

            vector_product_node = NodeCreator(
                side=f"C_{self.rig_name}", node_type="vectorProduct", base_name="mouth",
                name="Local", tag="CTRL", parent=None, custom_suffix=None
            ).create()

            cmds.connectAttr(f"{self.boca_surface}.worldSpace[0]", f"{cMuscleKeepOut_node}.muscleData[0].meshInBase")
            cmds.connectAttr(f"{aimMatrix_node}.outputMatrix", f"{vector_product_node}.matrix")
            cmds.connectAttr(f"{vector_product_node}.output", f"{cMuscleKeepOut_node}.inputData.inDirection")
            cmds.setAttr(f"{vector_product_node}.operation", 3)  # 3 = vector Matrix Product
            cmds.setAttr(f"{vector_product_node}.input1Z",1)
            cmds.setAttr(f"{vector_product_node}.normalizeOutput", 1)
        else:
            nurbCenter_locator = nurb_locator_name
            aimCenter_locator = f"C_{self.rig_name}_lipCenterOffProjectionAim_LOC"

        #Creacion de los joints
        cmds.select(clear=True)

        upper_joint = cmds.joint(n=f"C_{self.prefix}_lipUpper_JNT")
        cmds.matchTransform(upper_joint, upper_lip_grp, pos=True, rot=True)
        cmds.select(clear=True)
        
        lower_joint = cmds.joint(n=f"C_{self.prefix}_lipLower_JNT")
        cmds.matchTransform(lower_joint, lower_lip_grp, pos=True, rot=True)
        
        
        
        # =========================================================
        # 7. CURVA DE CURVATURA DE LOS LABIOS
        # Solo se construye de verdad cuando ya existen los 7 locators
        # (es decir, en la llamada de build() del segundo lado).
        # =========================================================
        self._build_lip_curve()

        return mid_lip_grp, end_lip_grp, end_local_off, end_local_trn,nurbCenter_locator,aimCenter_locator