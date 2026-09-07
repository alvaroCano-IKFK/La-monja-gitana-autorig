import maya.cmds as cmds
import math
import groups_module
import guides_module
import controlsLibrary
from groups_module import ControlsGroups
from nodeCreator_module import NodeCreator
import rigRoot_module


class EyebrowsModule(object):

    def __init__(self, guide_prefix="L_eyebrow_root", num_joints=10, rig_name="Character", side="L", root_instance=None, **kwargs):
        self.guide_prefix = guide_prefix
        self.num_joints = num_joints
        self.side = side
        self.rig_name = rig_name
        self.prefix = f"{self.side}_{rig_name}_eyebrow"

        self.group_maker = groups_module.ControlsGroups()
        self.root_instance = root_instance
        self.control_style = "circleControl"

        self.main_control_style = kwargs.get("main_control_style", self.control_style)
        self.corner_control_style = kwargs.get("corner_control_style", self.control_style)
        self.tangent_control_style = kwargs.get("tangent_control_style", self.control_style)

        self.rig_joints = []
        self.controls = []
        self.control_groups = []

        # NOTE: kept for backward compatibility with any external code that
        # reads this attribute. Joints and controls are no longer parented
        # under a single shared "module" group (see build()), so this stays
        # unused / None.
        self.module_grp = None

        # Top level roots, kept separate on purpose.
        self.joints_grp = None
        self.controls_grp = None
        self.local_grp = None

        # Local (matrix driven) mirror hierarchy bookkeeping.
        self.local_joints = {}
        self.local_transforms = {}
        self.local_curve = None

    # ------------------------------------------------------------------
    # Matrix chain helpers
    # ------------------------------------------------------------------
    def _build_relative_matrix(self, driver_ctrl, top_grp, node_base_name, node_name_tag):

        hierarchy_transforms = []
        current_node = cmds.listRelatives(driver_ctrl, parent=True, type="transform")

        while current_node:
            node_name = current_node[0]
            hierarchy_transforms.append(node_name)

            if node_name == top_grp:
                break

            current_node = cmds.listRelatives(node_name, parent=True, type="transform")

        matrix_inputs = list(reversed(hierarchy_transforms)) + [driver_ctrl]

        mult_node_creator = NodeCreator(
            side=self.side,
            node_type="multMatrix",
            base_name=node_base_name,
            name=node_name_tag,
            tag="matrix",
            parent=None,
            custom_suffix=None
        )
        multMatrix_node = mult_node_creator.create()

        dec_node_creator = NodeCreator(
            side=self.side,
            node_type="decomposeMatrix",
            base_name=node_base_name,
            name=node_name_tag,
            tag="matrix",
            parent=None,
            custom_suffix=None
        )
        decMatrix_node = dec_node_creator.create()

        for i, input_node in enumerate(matrix_inputs):
            cmds.connectAttr(f"{input_node}.matrix", f"{multMatrix_node}.matrixIn[{i}]", f=True)

        cmds.connectAttr(f"{multMatrix_node}.matrixSum", f"{decMatrix_node}.inputMatrix", f=True)

        return decMatrix_node

    def _connect_decompose_to_transform(self, decompose_node, target):

        for out_attr, in_attr in (
            ("outputTranslate", "translate"),
            ("outputRotate", "rotate"),
            ("outputScale", "scale"),
        ):
            src = f"{decompose_node}.{out_attr}"
            dest = f"{target}.{in_attr}"
            if not cmds.isConnected(src, dest):
                cmds.connectAttr(src, dest, f=True)

    def _create_relative_group(self, driver_ctrl, driven_ctrl, parent_grp, top_grp, rel_name):
        rel_grp = cmds.group(em=True, n=rel_name)

        temp_constraint_p = cmds.parentConstraint(driver_ctrl, rel_grp, mo=False)
        temp_constraint_s = cmds.parentConstraint(driven_ctrl, rel_grp, mo=False)
        cmds.delete(temp_constraint_p, temp_constraint_s)

        cmds.parent(rel_grp, parent_grp)

        decompose_node = self._build_relative_matrix(
            driver_ctrl=driver_ctrl,
            top_grp=top_grp,
            node_base_name=f"{self.rig_name}_eyebrow",
            node_name_tag="main"
        )
        self._connect_decompose_to_transform(decompose_node, rel_grp)

        return rel_grp

    # ------------------------------------------------------------------
    # Local joint helper
    # ------------------------------------------------------------------
    def _create_local_joint(self, parent_trn, name):

        cmds.select(clear=True)
        jnt = cmds.joint(name=name)
        cmds.parent(jnt, parent_trn, relative=True)
        return jnt

    # ------------------------------------------------------------------
    # Bezier curve
    # ------------------------------------------------------------------
    def _create_local_bezier_curve(self):

        required_labels = ("In", "InTan", "Mid", "OutTan", "Out")
        if not all(label in self.local_joints for label in required_labels):
            cmds.warning(" No es poden trobar tots els joints locals necessaris per crear la bezierCurve.")
            return None

        in_jnt = self.local_joints["In"]
        in_tan_jnt = self.local_joints["InTan"]
        mid_jnt = self.local_joints["Mid"]
        out_tan_jnt = self.local_joints["OutTan"]
        out_jnt = self.local_joints["Out"]

        in_pos = cmds.xform(in_jnt, q=True, ws=True, t=True)
        in_tan_pos = cmds.xform(in_tan_jnt, q=True, ws=True, t=True)
        mid_pos = cmds.xform(mid_jnt, q=True, ws=True, t=True)
        out_tan_pos = cmds.xform(out_tan_jnt, q=True, ws=True, t=True)
        out_pos = cmds.xform(out_jnt, q=True, ws=True, t=True)

        # Estimate the Mid anchor's tangent handles along the In->Out
        # direction so the curve stays close to the original, roughly
        # linear guide placement. Tune tangent_scale to taste.
        tangent_scale = 0.15
        mid_dir = [out_pos[axis] - in_pos[axis] for axis in range(3)]
        mid_in_tan_pos = [mid_pos[axis] - mid_dir[axis] * tangent_scale for axis in range(3)]
        mid_out_tan_pos = [mid_pos[axis] + mid_dir[axis] * tangent_scale for axis in range(3)]

        line_crv = cmds.curve(d=1, p=[in_pos, mid_pos, out_pos], n=f"{self.prefix}_local_curve_TEMP")
        bezier_result = cmds.nurbsCurveToBezier(line_crv)
        bezier_crv = bezier_result[0] if bezier_result else line_crv
        bezier_crv = cmds.rename(bezier_crv, f"{self.prefix}_local_BCRV")

        # CV order for an open cubic bezier with 3 anchors / 2 spans:
        # [InAnchor, InTangentOut, MidTangentIn, MidAnchor, MidTangentOut, OutTangentIn, OutAnchor]
        cv_positions = [
            in_pos,
            in_tan_pos,
            mid_in_tan_pos,
            mid_pos,
            mid_out_tan_pos,
            out_tan_pos,
            out_pos,
        ]
        for i, pos in enumerate(cv_positions):
            cmds.xform(f"{bezier_crv}.cv[{i}]", ws=True, t=pos)

        # Drive the curve live from the local joints. The end anchors and
        # their single tangent handle follow their matching Tan joint
        # one-to-one; the Mid anchor and its two (estimated) tangent
        # handles all follow the Mid joint rigidly, preserving the tuned
        # offsets computed above.
        skin_joints = [in_jnt, in_tan_jnt, mid_jnt, out_tan_jnt, out_jnt]
        skin_cluster = cmds.skinCluster(skin_joints, bezier_crv, tsb=True, n=f"{self.prefix}_local_curve_SKIN")[0]

        cv_weights = {
            0: in_jnt,
            1: in_tan_jnt,
            2: mid_jnt,
            3: mid_jnt,
            4: mid_jnt,
            5: out_tan_jnt,
            6: out_jnt,
        }
        for cv_index, jnt in cv_weights.items():
            cmds.skinPercent(skin_cluster, f"{bezier_crv}.cv[{cv_index}]", transformValue=[(jnt, 1.0)])

        self.local_curve = bezier_crv
        return bezier_crv

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def build(self):
        base_prefix = self.guide_prefix.replace("L_", "").replace("R_", "")

        # ------------------------------------------------------------
        # 1) JOINTS -- own top level group, fully separate from controls.
        # ------------------------------------------------------------
        jnt_grp = cmds.group(em=True, n=f"{self.prefix}_jnt_GRP")
        self.joints_grp = jnt_grp

        created_joints = []
        for i in range(1, self.num_joints + 1):
            guide_name = f"{self.side}_{base_prefix}_{i:02d}"

            if cmds.objExists(guide_name):
                pos = cmds.xform(guide_name, q=True, ws=True, t=True)
                rot = cmds.xform(guide_name, q=True, ws=True, ro=True)

                cmds.select(clear=True)
                jnt_name = f"{self.prefix}_{i:02d}_bind_JNT"
                jnt = cmds.joint(name=jnt_name, p=pos)
                cmds.setAttr(f"{jnt}.rotate", *rot)
                created_joints.append(jnt)
            else:
                cmds.warning(f" No s'ha trobat la guia: {guide_name}")

        if created_joints:
            cmds.parent(created_joints[0], jnt_grp)

        self.rig_joints = created_joints

        if not created_joints:
            return

        # ------------------------------------------------------------
        # 2) MAIN CONTROL -- own top level group.
        # ------------------------------------------------------------
        main_ctl_grp = cmds.group(em=True, n=f"{self.prefix}_main_ctrl_GRP")
        self.controls_grp = main_ctl_grp

        mid_idx = max(1, math.ceil(self.num_joints / 2.0))
        mid_guide_name = f"{self.side}_{base_prefix}_{mid_idx:02d}"

        main_ctl = controlsLibrary.create_control_from_lib(
            lib_name=self.main_control_style,
            final_name=f"{self.prefix}_Main_CTRL"
        )
        main_ctl_gen = self.group_maker.create_rig_hierarchy(main_ctl, mid_guide_name)
        cmds.parent(main_ctl_gen, main_ctl_grp)

        if not cmds.attributeQuery("slide", node=main_ctl, exists=True):
            cmds.addAttr(
                main_ctl,
                longName="slide",
                attributeType="float",
                defaultValue=1.0,
                minValue=0.0,
                maxValue=1.0,
                keyable=True
            )

        self.controls.append(main_ctl)
        self.control_groups.append(main_ctl_gen)

        # ------------------------------------------------------------
        # 3) LOCAL MIRROR OF THE MAIN CONTROL
        #    MainLocal_OFF > MainLocal_TRN, matrix driven from main_ctl.
        #    The same decomposeMatrix also feeds the "Main_REL" group,
        #    which is what was missing before (item 1 in the request).
        # ------------------------------------------------------------
        main_local_off = cmds.group(em=True, n=f"{self.prefix}MainLocal_OFF")
        main_local_trn = cmds.group(em=True, n=f"{self.prefix}MainLocal_TRN", p=main_local_off)
        self.local_grp = main_local_off
        self.local_transforms["Main"] = main_local_trn

        main_decompose = self._build_relative_matrix(
            driver_ctrl=main_ctl,
            top_grp=main_ctl_grp,
            node_base_name=f"{self.rig_name}_eyebrow",
            node_name_tag="mainLocal"
        )

        main_rel_grp = cmds.group(em=True, n=f"{self.prefix}Main_REL", p=main_ctl_grp)
        self._connect_decompose_to_transform(main_decompose, main_rel_grp)
        self._connect_decompose_to_transform(main_decompose, main_local_trn)

        # ------------------------------------------------------------
        # 4) IN / MID / OUT CONTROLS + their relative & local setups.
        # ------------------------------------------------------------
        sub_indices = {
            "In": 1,
            "Mid": mid_idx,
            "Out": self.num_joints,
        }
        corner_labels = ("In", "Out")

        for label, idx in sub_indices.items():
            sub_guide_name = f"{self.side}_{base_prefix}_{idx:02d}"
            if not cmds.objExists(sub_guide_name):
                cmds.warning(f" No s'ha trobat la guia: {sub_guide_name}")
                continue

            sub_ctrl_name = f"{self.prefix}_{label}_CTRL"
            sub_ctrl = controlsLibrary.create_control_from_lib(
                lib_name=self.corner_control_style,
                final_name=sub_ctrl_name
            )
            sub_ctl_gen = self.group_maker.create_rig_hierarchy(sub_ctrl, sub_guide_name)
            cmds.parent(sub_ctl_gen, main_ctl)

            rel_name = f"{self.side}_eyebrows{label}Main_REL"
            self._create_relative_group(
                driver_ctrl=main_ctl,
                driven_ctrl=sub_ctrl,
                parent_grp=sub_ctl_gen,
                top_grp=main_ctl_grp,
                rel_name=rel_name
            )

            self.controls.append(sub_ctrl)
            self.control_groups.append(sub_ctl_gen)

            # -- Local setup for this control, nested under MainLocal_TRN --
            local_off = cmds.group(em=True, n=f"{self.prefix}{label}Local_OFF", p=main_local_trn)
            local_trn = cmds.group(em=True, n=f"{self.prefix}{label}Local_TRN", p=local_off)
            self.local_transforms[label] = local_trn

            sub_decompose = self._build_relative_matrix(
                driver_ctrl=sub_ctrl,
                top_grp=main_ctl_grp,
                node_base_name=f"{self.rig_name}_eyebrow",
                node_name_tag=f"{label.lower()}Local"
            )
            self._connect_decompose_to_transform(sub_decompose, local_trn)

            local_jnt = self._create_local_joint(local_trn, f"{self.prefix}{label}Local_JNT")
            self.local_joints[label] = local_jnt

            if label in corner_labels:
                neighbour_idx = 2 if label == "In" else self.num_joints - 1
                neighbour_guide = f"{self.side}_{base_prefix}_{neighbour_idx:02d}"

                sub_pos = cmds.xform(sub_guide_name, q=True, ws=True, t=True)
                if cmds.objExists(neighbour_guide):
                    nb_pos = cmds.xform(neighbour_guide, q=True, ws=True, t=True)
                else:
                    nb_pos = sub_pos

                tangent_factor = 0.3
                tangent_pos = [
                    sub_pos[0] + (nb_pos[0] - sub_pos[0]) * tangent_factor,
                    sub_pos[1] + (nb_pos[1] - sub_pos[1]) * tangent_factor,
                    sub_pos[2] + (nb_pos[2] - sub_pos[2]) * tangent_factor,
                ]

                tangent_loc = cmds.spaceLocator(n=f"{sub_ctrl_name}_tangent_TEMP")[0]
                cmds.xform(tangent_loc, ws=True, t=tangent_pos)

                tangent_ctl_name = f"{self.prefix}_{label}Tan_CTRL"
                tangent_ctl = controlsLibrary.create_control_from_lib(
                    lib_name=self.tangent_control_style,
                    final_name=tangent_ctl_name
                )
                tangent_ctl_gen = self.group_maker.create_rig_hierarchy(tangent_ctl, tangent_loc)
                cmds.parent(tangent_ctl_gen, sub_ctrl)
                cmds.delete(tangent_loc)

                tan_rel_name = f"{self.side}_eyebrows{label}TanMain_REL"
                self._create_relative_group(
                    driver_ctrl=sub_ctrl,
                    driven_ctrl=tangent_ctl,
                    parent_grp=tangent_ctl_gen,
                    top_grp=sub_ctl_gen,
                    rel_name=tan_rel_name
                )

                self.controls.append(tangent_ctl)
                self.control_groups.append(tangent_ctl_gen)

                # -- Local setup for the tangent control, nested under
                #    this control's own Local_TRN (mirrors driver=sub_ctrl,
                #    top_grp=sub_ctl_gen like the tangent's REL group does) --
                tan_label = f"{label}Tan"
                tan_local_off = cmds.group(em=True, n=f"{self.prefix}{tan_label}Local_OFF", p=local_trn)
                tan_local_trn = cmds.group(em=True, n=f"{self.prefix}{tan_label}Local_TRN", p=tan_local_off)
                self.local_transforms[tan_label] = tan_local_trn

                tan_decompose = self._build_relative_matrix(
                    driver_ctrl=tangent_ctl,
                    top_grp=sub_ctl_gen,
                    node_base_name=f"{self.rig_name}_eyebrow",
                    node_name_tag=f"{label.lower()}TanLocal"
                )
                self._connect_decompose_to_transform(tan_decompose, tan_local_trn)

                tan_local_jnt = self._create_local_joint(tan_local_trn, f"{self.prefix}{tan_label}Local_JNT")
                self.local_joints[tan_label] = tan_local_jnt

        # ------------------------------------------------------------
        # 5) BEZIER CURVE riding on top of the local joints.
        # ------------------------------------------------------------
        self._create_local_bezier_curve()