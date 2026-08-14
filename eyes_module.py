import maya.cmds as cmds    
import guides_module
import controlsLibrary
from groups_module import ControlsGroups
from nodeCreator_module import NodeCreator
import rigRoot_module

class EyesModule(object):

    def __init__(self, 
                 eye_mid="eye_mid",
                 eye_inner_corner="eye_inner_corner",
                 eye_outer_corner="eye_outer_corner",
                 eyelid_up="eyelid_up",
                 eyelid_low="eyelid_low",
                 eyelid_up02="eyelid_up02",
                 eyelid_up03="eyelid_up03",
                 eyelid_low02="eyelid_low02",
                 eyelid_low03="eyelid_low03",
                 root_instance=None,   
                 rig_name="Character",
                 side="L"):
        

        self.eye_mid = eye_mid
        self.eye_inner_corner = eye_inner_corner
        self.eye_outer_corner = eye_outer_corner

        self.eyelid_up = eyelid_up
        self.eyelid_low = eyelid_low

        self.eyelid_up02 = eyelid_up02
        self.eyelid_up03 = eyelid_up03

        self.eyelid_low02 = eyelid_low02
        self.eyelid_low03 = eyelid_low03

        self.group_maker = ControlsGroups()
        self.rig_name = rig_name
        self.root_instance = root_instance
        self.styles = {"mainFk": "circleControl"}
        
        self.side = side
        self.prefix = f"{self.side}_{rig_name}"

        # Guias que llevan un segundo control (Sub) ademas del principal
        self.sub_control_guides = [
            self.eye_inner_corner,
            self.eye_outer_corner,
            self.eyelid_up,
            self.eyelid_low,
        ]

        # Joints creados a partir de las guias
        self.eye_joints = {}
        self.joints_group = None

        # Curvas de los parpados
        self.upper_curve = None
        self.lower_curve = None

        # Controles y setup local
        self.eye_controls = {}
        self.eye_control_groups = {}
        self.eye_local_offs = {}
        self.eye_local_trns = {}

        # Segundos controles (Sub) y su setup local
        self.eye_sub_controls = {}
        self.eye_sub_control_groups = {}
        self.eye_sub_local_offs = {}
        self.eye_sub_local_trns = {}

    # ------------------------------------------------------------------
    # SETUP LOCAL (mismo helper que el modulo de la boca)
    # ------------------------------------------------------------------
    def _build_off_network(self, prefix, base_name, source_ctrl, source_ctrl_grp):
        """
        Crea el space-tracking local de un control.
        Devuelve (local_off, local_trn).
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

    def _build_eye_joints(self):
        """
        Crea un joint nuevo por cada joint de guia del ojo, en la misma posicion y orientacion.
        Los agrupa todos bajo un unico grupo del modulo.
        """
        guides = [
            self.eye_mid,
            self.eye_inner_corner,
            self.eye_outer_corner,
            self.eyelid_up,
            self.eyelid_low,
            self.eyelid_up02,
            self.eyelid_up03,
            self.eyelid_low02,
            self.eyelid_low03,
        ]

        # Limpieza de una build anterior para poder relanzar el script
        self.joints_group = f"{self.prefix}_eyeJoints_GRP"
        if cmds.objExists(self.joints_group):
            cmds.delete(self.joints_group)

        self.eye_joints = {}
        created_joints = []

        for guide in guides:
            # Acepta la guia con lado ("L_eye_mid") o sin el ("eye_mid")
            guide_node = None
            if cmds.objExists(guide):
                guide_node = guide
            elif cmds.objExists(f"{self.side}_{guide}"):
                guide_node = f"{self.side}_{guide}"

            if guide_node is None:
                cmds.warning(f"[EyesModule] No se encontro la guia {guide}, se omite su joint.")
                continue

            joint_name = f"{self.prefix}_{guide}_JNT"
            if cmds.objExists(joint_name):
                cmds.delete(joint_name)

            cmds.select(clear=True)
            new_joint = cmds.joint(name=joint_name)
            cmds.matchTransform(new_joint, guide_node, position=True, rotation=True)

            self.eye_joints[guide] = new_joint
            created_joints.append(new_joint)

        if not created_joints:
            cmds.warning("[EyesModule] No se creo ningun joint del ojo.")
            self.joints_group = None
            return None

        self.joints_group = cmds.group(created_joints, name=self.joints_group)
        cmds.select(clear=True)

        return self.joints_group

    def _get_ordered_eyelid_joints(self, upper=True):
        """
        Devuelve la lista de joints del parpado ordenados de esquina interna a esquina externa.
        Son 5 joints: inner_corner, secundario interno, central, secundario externo, outer_corner.
        """
        if upper:
            ordered_guides = [
                self.eye_inner_corner,
                self.eyelid_up02,
                self.eyelid_up,
                self.eyelid_up03,
                self.eye_outer_corner,
            ]
        else:
            ordered_guides = [
                self.eye_inner_corner,
                self.eyelid_low02,
                self.eyelid_low,
                self.eyelid_low03,
                self.eye_outer_corner,
            ]

        return [f"{self.prefix}_{guide}_JNT" for guide in ordered_guides]

    def _build_eyelid_curves(self):
        """
        Crea las curvas de curvatura de los parpados (superior e inferior):
        1. Curva de grado 1 con un CV en la posicion de cada joint (5 CVs).
        2. rebuildCurve a grado 3, 2 spans (2+3 = 5 CVs -> mismo conteo, misma correspondencia 1 a 1).
        3. Cada joint queda asociado al CV que ocupa su posicion.

        Solo se construye cuando existen los 5 joints de esa linea. Si falta alguno, no hace nada.
        """
        for upper in (True, False):
            line_name = "eyelidUpperLine" if upper else "eyelidLowerLine"
            curve_name = f"{self.prefix}_{line_name}_CRV"

            if cmds.objExists(curve_name):
                cmds.delete(curve_name)

            ordered_joints = self._get_ordered_eyelid_joints(upper=upper)
            if not all(cmds.objExists(jnt) for jnt in ordered_joints):
                cmds.warning(f"[EyesModule] Faltan joints para construir {curve_name}.")
                continue

            positions = [cmds.xform(jnt, q=True, ws=True, t=True) for jnt in ordered_joints]

            curve_transform = cmds.curve(d=1, p=positions, n=curve_name)
            cmds.rebuildCurve(
                curve_transform, ch=0, rpo=1, rt=0, end=1, kr=0, kcp=0, kep=1, kt=0,
                s=2, d=3, tol=0.01
            )
            cmds.setAttr(f"{curve_transform}.lineWidth", 3)

            if upper:
                self.upper_curve = curve_transform
            else:
                self.lower_curve = curve_transform

        cmds.select(clear=True)

        return self.upper_curve, self.lower_curve

    def build(self):
        """
        Metodo principal del modulo. Construye los joints del ojo a partir de las guias,
        las curvas de los parpados y un control (con sus grupos y su setup local) por joint.
        Las esquinas y los parpados central superior e inferior llevan un segundo control (Sub).
        """
        self._build_eye_joints()
        if self.joints_group is None:
            return None

        self._build_eyelid_curves()

        # =========================================================
        # CONTROLES + GRUPOS + SETUP LOCAL (OFF / TRN) POR CADA JOINT
        # Mismo patron que levator / depresor / pinch de la boca.
        # =========================================================
        self.eye_controls = {}
        self.eye_control_groups = {}
        self.eye_local_offs = {}
        self.eye_local_trns = {}

        self.eye_sub_controls = {}
        self.eye_sub_control_groups = {}
        self.eye_sub_local_offs = {}
        self.eye_sub_local_trns = {}

        for guide, joint in self.eye_joints.items():
            ctrl_name = f"{self.prefix}_{guide}_CTRL"
            if not cmds.objExists(ctrl_name):
                ctrl = controlsLibrary.create_control_from_lib(
                    lib_name=self.styles["mainFk"],
                    final_name=ctrl_name
                )

                ctrl_grp = self.group_maker.create_rig_hierarchy(
                    ctrl, joint, match_rotation=True, world_space=True
                )
            else:
                ctrl = ctrl_name
                ctrl_grp = cmds.listRelatives(ctrl, parent=True)[0]

            off_name = f"{self.prefix}_{guide}Local_OFF"
            trn_name = f"{self.prefix}_{guide}Local_TRN"
            if not cmds.objExists(off_name):
                local_off, local_trn = self._build_off_network(
                    prefix=self.prefix, base_name=guide,
                    source_ctrl=ctrl, source_ctrl_grp=ctrl_grp
                )
            else:
                local_off, local_trn = off_name, trn_name

            self.eye_controls[guide] = ctrl
            self.eye_control_groups[guide] = ctrl_grp
            self.eye_local_offs[guide] = local_off
            self.eye_local_trns[guide] = local_trn

            # ---- Segundo control (Sub) solo en esquinas y parpados centrales ----
            if guide not in self.sub_control_guides:
                continue

            sub_ctrl_name = f"{self.prefix}_{guide}Sub_CTRL"
            if not cmds.objExists(sub_ctrl_name):
                sub_ctrl = controlsLibrary.create_control_from_lib(
                    lib_name=self.styles["mainFk"],
                    final_name=sub_ctrl_name
                )

                sub_ctrl_grp = self.group_maker.create_rig_hierarchy(
                    sub_ctrl, joint, match_rotation=True, world_space=True
                )
                # El Sub cuelga del control principal para que herede su movimiento
                cmds.parent(sub_ctrl_grp, ctrl)
            else:
                sub_ctrl = sub_ctrl_name
                sub_ctrl_grp = cmds.listRelatives(sub_ctrl, parent=True)[0]

            sub_off_name = f"{self.prefix}_{guide}SubLocal_OFF"
            sub_trn_name = f"{self.prefix}_{guide}SubLocal_TRN"
            if not cmds.objExists(sub_off_name):
                sub_local_off, sub_local_trn = self._build_off_network(
                    prefix=self.prefix, base_name=f"{guide}Sub",
                    source_ctrl=sub_ctrl, source_ctrl_grp=sub_ctrl_grp
                )
            else:
                sub_local_off, sub_local_trn = sub_off_name, sub_trn_name

            self.eye_sub_controls[guide] = sub_ctrl
            self.eye_sub_control_groups[guide] = sub_ctrl_grp
            self.eye_sub_local_offs[guide] = sub_local_off
            self.eye_sub_local_trns[guide] = sub_local_trn

        cmds.select(clear=True)

        return self.joints_group