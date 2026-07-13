import maya.cmds as cmds    
import guides_module
import controlsLibrary
from groups_module import ControlsGroups
from nodeCreator_module import NodeCreator
import rigRoot_module

class MouthModule(object):
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

    def build(self):
        mid_lip = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["mainFk"],
            final_name=f"{self.prefix}_mid_LIP_CTRL"
        )
        
        if cmds.objExists(mid_lip):
            # Cambiamos el string usando Python estándar y renombramos en Maya
            nuevo_nombre = mid_lip.replace("L_", "C_")
            mid_lip = cmds.rename(mid_lip, nuevo_nombre)
            
        mid_lip_grp = self.group_maker.create_rig_hierarchy(
            mid_lip, self.lip_mid, match_rotation=True, world_space=True
        )

            
        end_lip = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["mainFk"],
            final_name=f"{self.prefix}_end_LIP_CTRL"
        )
        end_lip_grp = self.group_maker.create_rig_hierarchy(
            end_lip, self.lip_end, match_rotation=True, world_space=True
        )



        #Se hace el rebuild de la nurbs para que sea de grado 3 y se pueda hacer el closest point on surface
        cmds.rebuildSurface(self.boca_surface, ch=0, rpo=1, rt=0, end=1, kr=0, kcp=0, kc=0, su=4, du=3, sv=4, dv=3, tol=0.01, fr=0, dir=2)
        
        #Mirror behaviour group
        self.main_rig_grp = cmds.group(em=True, n=f"{self.prefix}_mouthControls_GRP")
        #cmds.parent(end_lip_grp, self.main_rig_grp)
        
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
        
        
        # --- Creación de grupos para espacio local ---
        local_off, local_trn = self.group_maker.create_space_tracking_hierarchy(
            space_base_name=f"{self.prefix}_mouthLocal",
            target_joint=end_lip_grp,
            parent_group=None
        )
        
        

        # --- Si es el lado R, invertimos el espacio local ---
        if self.side == "R":
            # Creamos un grupo contenedor para el mirror del sistema local
            local_mirror_grp = cmds.group(em=True, n=f"{self.prefix}_mouthLocalMirror_GRP")
            
            # Hacemos que tenga la escala invertida en X
            cmds.setAttr(f"{local_mirror_grp}.scaleX", -1)
            
            # Si el módulo tiene acceso al root, lo organizamos bajo el rig_GRP o el mirror de los controles
            #if self.root_instance:
                #mirror_behavior_grp = f"{self.root_instance.rig_name}_mirrorBehaviour_GRP"
                #if cmds.objExists(mirror_behavior_grp):
                    #cmds.parent(local_mirror_grp, mirror_behavior_grp)
            
            # Metemos el local_off dentro de este grupo con escala negativa
            cmds.parent(local_off, local_mirror_grp)
            
            cmds.matchTransform(local_off,end_lip, pos=True, rot=True)
        
        # --- Limpieza previa por si se rehace el build (evita nodos huérfanos) ---
        stale_nodes = cmds.ls(f"{self.prefix}_C_mouth_Local_*_multMatrix_*") + \
                      cmds.ls(f"{self.prefix}_C_mouth_Local_*_decomposeMatrix_*")
        if stale_nodes:
            cmds.delete(stale_nodes)

        # --- Creación de nodos vía NodeCreator ---
        mult_localMatrix_node = NodeCreator(
            side=self.prefix,
            node_type="multMatrix",
            base_name="mouth",
            name="Local",
            tag="CTRL",
            parent=None,
            custom_suffix=None
        ).create()

        decompose_localMatrix_node = NodeCreator(
            side=self.prefix,
            node_type="decomposeMatrix",
            base_name="mouth",
            name="Local",
            tag="CTRL",
            parent=None,
            custom_suffix=None
        ).create()
        
        decompose_localTrn_node = NodeCreator(
            side=self.prefix,
            node_type="decomposeMatrix",
            base_name="mouth",
            name="Local",
            tag="CTRL",
            parent=None,
            custom_suffix=None
        ).create()

        # --- Conexiones en espacio local ---
        cmds.connectAttr(f"{end_lip}.matrix", f"{mult_localMatrix_node}.matrixIn[0]")
        cmds.connectAttr(f"{mult_localMatrix_node}.matrixSum", f"{decompose_localMatrix_node}.inputMatrix")
        cmds.connectAttr(f"{decompose_localMatrix_node}.outputTranslate", f"{local_trn}.translate")
        cmds.connectAttr(f"{decompose_localMatrix_node}.outputRotate", f"{local_trn}.rotate")
        cmds.connectAttr(f"{decompose_localMatrix_node}.outputScale", f"{local_trn}.scale")
        
        cmds.connectAttr(f"{local_trn}.worldMatrix[0]", f"{decompose_localTrn_node}.inputMatrix")
        
        locator = cmds.spaceLocator(name=f"{self.prefix}_mouthLocal_locator")[0]
        
        # --- Conexiones en espacio a la nurbs ---
        closest_point_node = NodeCreator(
            side=self.prefix,
            node_type="closestPointOnSurface",
            base_name="mouth",
            name="Local",
            tag="CTRL",
            parent=None,
            custom_suffix=None
        ).create()
        
        cmds.connectAttr(f"{self.boca_surface}.worldSpace[0]", f"{closest_point_node}.inputSurface")
        
        cmds.connectAttr(f"{decompose_localTrn_node}.outputTranslate", f"{closest_point_node}.inPosition")
        
        #cmds.connectAttr(f"{closest_point_node}.position", f"{locator}.translate")
        
        #sacar la rotacion del locator para que siga la normal de la superficie
        uvpin_node = NodeCreator(
            side=self.prefix,
            node_type="uvPin",
            base_name="mouth",
            name="Local",
            tag="CTRL",
            parent=None,
            custom_suffix=None
        ).create()
        
        cmds.connectAttr(f"{self.boca_surface}.worldSpace[0]", f"{uvpin_node}.deformedGeometry")
        cmds.connectAttr(f"{closest_point_node}.result.parameterU", f"{uvpin_node}.coordinate[0].coordinateU")
        cmds.connectAttr(f"{closest_point_node}.result.parameterV", f"{uvpin_node}.coordinate[0].coordinateV")
        
        cmds.connectAttr(f"{uvpin_node}.outputMatrix[0]", f"{locator}.offsetParentMatrix")
        cmds.setAttr(f"{uvpin_node}.normalAxis", 2)  # Set normal axis to Z
        cmds.setAttr(f"{uvpin_node}.tangentAxis", 0)  # Set up axis to X

        return mid_lip_grp, end_lip_grp, local_off, local_trn