import maya.cmds as cmds    
import guides_module
import controlsLibrary
from groups_module import ControlsGroups
from nodeCreator_module import NodeCreator
import rigRoot_module

class MouthModule(object):

    # Índices fijos de coordinate[] en el uvPin compartido
    RAW_INDEX = {"L": 0, "R": 1, "C": 2}
    BLEND_INDEX = {"L": 3, "R": 4}

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
    # HELPERS MÍNIMOS (solo idempotencia: crear una vez, reutilizar siempre)
    # ------------------------------------------------------------------
    def _get_or_create_shared_uvpin(self):
        """Crea el uvPin único de la boca la primera vez, y lo reutiliza siempre."""
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

    def _get_or_create_shared_lips_settings_grp(self):
        """Grupo único con los attributes de blend, compartido por L y R (no uno por lado)."""
        grp_name = f"C_{self.rig_name}_lipsSettings_GRP"
        if cmds.objExists(grp_name):
            return grp_name

        blend_grp = cmds.group(em=True, n=grp_name)
        cmds.addAttr(blend_grp, ln="HorizontalFollow01", at="float", min=0, max=1, dv=0, k=True)
        cmds.addAttr(blend_grp, ln="VerticalFollow01", at="float", min=0, max=1, dv=0, k=True)
        return blend_grp

    def _is_coordinate_connected(self, uvpin_node, coordinate_index):
        """True si ese slot del uvPin ya tiene algo conectado (para no reconstruir el centro dos veces)."""
        conns = cmds.listConnections(
            f"{uvpin_node}.coordinate[{coordinate_index}].coordinateU",
            source=True, destination=False
        )
        return bool(conns)

    # ------------------------------------------------------------------
    # BUILD — todo en una sola función, en orden de ejecución real
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

        # 3. UVPIN ÚNICO COMPARTIDO (L, R y centro se conectan aquí)
        uvpin_node = self._get_or_create_shared_uvpin()

        # =========================================================
        # 4. RED DEL END_LIP (comisura del lado actual: L o R)
        # =========================================================
        end_local_off, end_local_trn = self.group_maker.create_space_tracking_hierarchy(
            space_base_name=f"{self.prefix}_mouthLocal",
            target_joint=end_lip_grp,
            parent_group=None
        )

        stale_nodes = cmds.ls(f"{self.prefix}_mouth_Local_*_multMatrix_*") + \
                      cmds.ls(f"{self.prefix}_mouth_Local_*_decomposeMatrix_*")
        if stale_nodes:
            cmds.delete(stale_nodes)

        end_mult_node = NodeCreator(
            side=self.prefix, node_type="multMatrix", base_name="mouth",
            name="Local", tag="CTRL", parent=None, custom_suffix=None
        ).create()
        end_decompose_node = NodeCreator(
            side=self.prefix, node_type="decomposeMatrix", base_name="mouth",
            name="Local", tag="CTRL", parent=None, custom_suffix=None
        ).create()
        end_decompose_trn_node = NodeCreator(
            side=self.prefix, node_type="decomposeMatrix", base_name="mouth",
            name="Local", tag="CTRL", parent=None, custom_suffix=None
        ).create()

        cmds.connectAttr(f"{end_lip}.matrix", f"{end_mult_node}.matrixIn[0]")
        cmds.connectAttr(f"{end_mult_node}.matrixSum", f"{end_decompose_node}.inputMatrix")
        cmds.connectAttr(f"{end_decompose_node}.outputTranslate", f"{end_local_trn}.translate")
        cmds.connectAttr(f"{end_decompose_node}.outputRotate", f"{end_local_trn}.rotate")
        cmds.connectAttr(f"{end_decompose_node}.outputScale", f"{end_local_trn}.scale")
        cmds.connectAttr(f"{end_local_trn}.worldMatrix[0]", f"{end_decompose_trn_node}.inputMatrix")

        end_closest_point = NodeCreator(
            side=self.prefix, node_type="closestPointOnSurface", base_name="mouth",
            name="Local", tag="CTRL", parent=None, custom_suffix=None
        ).create()
        cmds.connectAttr(f"{self.boca_surface}.worldSpace[0]", f"{end_closest_point}.inputSurface")
        cmds.connectAttr(f"{end_decompose_trn_node}.outputTranslate", f"{end_closest_point}.inPosition")

        # --- Conexión CRUDA de este lado (nunca se toca luego) ---
        raw_index = self.RAW_INDEX[self.side]
        cmds.connectAttr(f"{end_closest_point}.result.parameterU", f"{uvpin_node}.coordinate[{raw_index}].coordinateU")
        cmds.connectAttr(f"{end_closest_point}.result.parameterV", f"{uvpin_node}.coordinate[{raw_index}].coordinateV")

        if self.side == "R":
            local_mirror_grp = cmds.group(em=True, n=f"{self.prefix}_mouthLocalMirror_GRP")
            cmds.setAttr(f"{local_mirror_grp}.scaleX", -1)
            cmds.parent(end_local_off, local_mirror_grp)
            cmds.matchTransform(end_local_off, end_lip, pos=True, rot=True)

        # =========================================================
        # 5. RED DEL CENTRO (mid_lip) — se construye una única vez
        #    (incluye su propio locator, igual que L y R)
        # =========================================================
        center_raw_index = self.RAW_INDEX["C"]
        if not self._is_coordinate_connected(uvpin_node, center_raw_index):

            center_local_off, center_local_trn = self.group_maker.create_space_tracking_hierarchy(
                space_base_name=f"C_{self.rig_name}_mouthCenterLocal",
                target_joint=mid_lip_grp,
                parent_group=None
            )

            center_mult_node = NodeCreator(
                side=f"C_{self.rig_name}", node_type="multMatrix", base_name="mouthCenter",
                name="Local", tag="CTRL", parent=None, custom_suffix=None
            ).create()
            center_decompose_node = NodeCreator(
                side=f"C_{self.rig_name}", node_type="decomposeMatrix", base_name="mouthCenter",
                name="Local", tag="CTRL", parent=None, custom_suffix=None
            ).create()
            center_decompose_trn_node = NodeCreator(
                side=f"C_{self.rig_name}", node_type="decomposeMatrix", base_name="mouthCenter",
                name="Local", tag="CTRL", parent=None, custom_suffix=None
            ).create()

            cmds.connectAttr(f"{mid_lip}.matrix", f"{center_mult_node}.matrixIn[0]")
            cmds.connectAttr(f"{center_mult_node}.matrixSum", f"{center_decompose_node}.inputMatrix")
            cmds.connectAttr(f"{center_decompose_node}.outputTranslate", f"{center_local_trn}.translate")
            cmds.connectAttr(f"{center_decompose_node}.outputRotate", f"{center_local_trn}.rotate")
            cmds.connectAttr(f"{center_decompose_node}.outputScale", f"{center_local_trn}.scale")
            cmds.connectAttr(f"{center_local_trn}.worldMatrix[0]", f"{center_decompose_trn_node}.inputMatrix")

            center_closest_point = NodeCreator(
                side=f"C_{self.rig_name}", node_type="closestPointOnSurface", base_name="mouthCenter",
                name="Local", tag="CTRL", parent=None, custom_suffix=None
            ).create()
            cmds.connectAttr(f"{self.boca_surface}.worldSpace[0]", f"{center_closest_point}.inputSurface")
            cmds.connectAttr(f"{center_decompose_trn_node}.outputTranslate", f"{center_closest_point}.inPosition")

            cmds.connectAttr(f"{center_closest_point}.result.parameterU", f"{uvpin_node}.coordinate[{center_raw_index}].coordinateU")
            cmds.connectAttr(f"{center_closest_point}.result.parameterV", f"{uvpin_node}.coordinate[{center_raw_index}].coordinateV")

            # --- Locator del centro, igual patrón que L y R ---
            center_locator = cmds.spaceLocator(name=f"C_{self.rig_name}_mouthCenterLocal_locator")[0]
            cmds.connectAttr(f"{uvpin_node}.outputMatrix[{center_raw_index}]", f"{center_locator}.offsetParentMatrix")

        # Recuperamos el closestPoint del centro (recién creado o de la llamada anterior)
        center_closest_point = cmds.listConnections(
            f"{uvpin_node}.coordinate[{center_raw_index}].coordinateU", source=True, destination=False
        )[0]

        # =========================================================
        # 6. BLEND (HorizontalFollow / VerticalFollow) — este lado
        #    Usa el ÚNICO grupo de lips settings, compartido L/R
        # =========================================================
        blend_grp = self._get_or_create_shared_lips_settings_grp()

        blendU_node = NodeCreator(
            side=self.prefix, node_type="blendTwoAttr", base_name="mouth",
            name="HorizontalFollow", tag="CTRL", parent=None, custom_suffix=None
        ).create()
        blendV_node = NodeCreator(
            side=self.prefix, node_type="blendTwoAttr", base_name="mouth",
            name="VerticalFollow", tag="CTRL", parent=None, custom_suffix=None
        ).create()

        cmds.connectAttr(f"{end_closest_point}.result.parameterU", f"{blendU_node}.input[0]")
        cmds.connectAttr(f"{center_closest_point}.result.parameterU", f"{blendU_node}.input[1]")
        cmds.connectAttr(f"{blend_grp}.HorizontalFollow01", f"{blendU_node}.attributesBlender")

        cmds.connectAttr(f"{end_closest_point}.result.parameterV", f"{blendV_node}.input[0]")
        cmds.connectAttr(f"{center_closest_point}.result.parameterV", f"{blendV_node}.input[1]")
        cmds.connectAttr(f"{blend_grp}.VerticalFollow01", f"{blendV_node}.attributesBlender")

        # --- Conexión del BLEND a su propio slot dedicado (NO pisa el crudo) ---
        blend_index = self.BLEND_INDEX[self.side]
        cmds.connectAttr(f"{blendU_node}.output", f"{uvpin_node}.coordinate[{blend_index}].coordinateU")
        cmds.connectAttr(f"{blendV_node}.output", f"{uvpin_node}.coordinate[{blend_index}].coordinateV")

        # =========================================================
        # 7. LOCATOR FINAL DE ESTE LADO — sigue el resultado del BLEND
        # =========================================================
        end_locator = cmds.spaceLocator(name=f"{self.prefix}_mouthLocal_locator")[0]
        cmds.connectAttr(f"{uvpin_node}.outputMatrix[{blend_index}]", f"{end_locator}.offsetParentMatrix")

        return mid_lip_grp, end_lip_grp, end_local_off, end_local_trn