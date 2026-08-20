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
        self.module_grp = None

    def build(self):
        self.module_grp = cmds.group(em=True, n=f"{self.prefix}__GRP")
        jnt_grp = cmds.group(em=True, n=f"{self.prefix}_jnt_GRP", p=self.module_grp)

        created_joints = []
        base_prefix = self.guide_prefix.replace("L_", "").replace("R_", "")

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

        main_ctrl = None
        if created_joints:
            main_ctl_grp = cmds.group(em=True, n=f"{self.prefix}_main_ctrl_GRP", p=self.module_grp)

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

            sub_indices = {
                "In": 1,
                "Mid": mid_idx,
                "Out": self.num_joints,
            }
            corner_labels = ("In", "Out")

            sub_ctl_grp = cmds.group(em=True, n=f"{self.prefix}_sub_ctl_GRP", p=main_ctl_grp)

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
                cmds.parent(sub_ctl_gen, sub_ctl_grp)

                rel_name = f"{self.side.lower()}_eyebrowsMain_REL"
                rel_grp= cmds.group(em=True, n=rel_name)

                temp_constraint_p = cmds.parentConstraint(main_ctl, rel_grp, mo=False)
                temp_constraint_s = cmds.parentConstraint(sub_ctrl, rel_grp, mo=False)
                cmds.delete(temp_constraint_p, temp_constraint_s)

                cmds.parent(rel_grp, main_ctl_grp)

                hierarchy_transforms = []
                current_node = main_ctl
                while current_node and current_node != main_ctl_grp:
                    parents = cmds.listRelatives(current_node, parent=True, type="transform")
                    if parents:
                        hierarchy_transforms.append(current_node)
                        current_node = parents[0]
                    else:
                        break

                matrix_inputs = hierarchy_transforms + [main_ctl]

                mult_node_creator = NodeCreator(
                    side=self.side, 
                    node_type="multMatrix", 
                    base_name=f"{self.rig_name}_eyebrow", 
                    name="main", 
                    tag="matrix", 
                    parent=None, 
                    custom_suffix=None
                )
                multMatrix_node = mult_node_creator.create()
                dec_node_creator = NodeCreator(
                    side=self.side, 
                    node_type="decomposeMatrix", 
                    base_name=f"{self.rig_name}_eyebrow", 
                    name="main", 
                    tag="matrix", 
                    parent=None, 
                    custom_suffix=None
                )
                decMatrix_node = dec_node_creator.create()

                for i, input_node in enumerate(matrix_inputs):
                    cmds.connectAttr(f"{input_node}.worldMatrix[0]", f"{multMatrix_node}.matrixIn[{i}]", f=True)

                cmds.connectAttr(f"{multMatrix_node}.matrixSum", f"{decMatrix_node}.inputMatrix", f=True)

                cmds.connectAttr(f"{decMatrix_node}.outputTranslate", f"{rel_grp}.translate", f=True)
                cmds.connectAttr(f"{decMatrix_node}.outputRotate", f"{rel_grp}.rotate", f=True)
                cmds.connectAttr(f"{decMatrix_node}.outputScale", f"{rel_grp}.scale", f=True)

                self.controls.append(sub_ctrl)
                self.control_groups.append(sub_ctl_gen)

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
                    cmds.parent(tangent_ctl_gen, sub_ctl_grp)
                    cmds.delete(tangent_loc)

                    self.controls.append(tangent_ctl)
                    self.control_groups.append(tangent_ctl_gen)


        print(f"Build {self.prefix} complet amb èxit.")