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
        cmds.addAttr(settings_grp, ln="HorizontalFollow01", nn="Horizontal Follow 01", at="float", min=0, max=1, dv=0, k=True)
        cmds.addAttr(settings_grp, ln="HorizontalFollow02", nn="Horizontal Follow 02", at="float", min=0, max=1, dv=0, k=True)
        cmds.addAttr(settings_grp, ln="VerticalFollow01", nn="Vertical Follow 01", at="float", min=0, max=1, dv=0, k=True)
        cmds.addAttr(settings_grp, ln="VerticalFollow02", nn="Vertical Follow 02", at="float", min=0, max=1, dv=0, k=True)
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
        if not self._is_coordinate_connected(uvpin_node, center_raw_index):
            center_local_off, center_local_trn, center_cps = self._build_cps_network(
                prefix=f"C_{self.rig_name}", cps_name=f"C_{self.rig_name}_lips_CPS",
                base_name="mouthCenter", source_ctrl=mid_lip, source_ctrl_grp=mid_lip_grp
            )
            cmds.connectAttr(f"{center_cps}.result.parameterU", f"{uvpin_node}.coordinate[{center_raw_index}].coordinateU")
            cmds.connectAttr(f"{center_cps}.result.parameterV", f"{uvpin_node}.coordinate[{center_raw_index}].coordinateV")

            center_locator = cmds.spaceLocator(name=f"C_{self.rig_name}_lipProjected_LOC")[0]
            cmds.connectAttr(f"{uvpin_node}.outputMatrix[{center_raw_index}]", f"{center_locator}.offsetParentMatrix")

        center_cps = cmds.listConnections(
            f"{uvpin_node}.coordinate[{center_raw_index}].coordinateU", source=True, destination=False
        )[0]

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

        return mid_lip_grp, end_lip_grp, end_local_off, end_local_trn