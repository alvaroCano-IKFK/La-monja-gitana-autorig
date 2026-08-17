import groups_module
import maya.cmds as cmds
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
        
        self.rig_joints = []
        self.controls = []
        self.control_groups = []
        self.module_grp = None

    def build(self):
        self.module_grp = cmds.group(em=True, n=f"{self.prefix}__GRP")
        jnt_grp = cmds.group(em=True, n=f"{self.prefix}_jnt_GRP", p=self.module_grp)
        ctrl_grp_all = cmds.group(em=True, n=f"{self.prefix}_ctrl_GRP", p=self.module_grp)

        created_joints = []
        
        for i in range(1, self.num_joints + 1):
            base_prefix = self.guide_prefix.replace("L_", "").replace("R_", "")
            guide_name = f"{self.side}_{base_prefix}_{i:02d}"
            
            if cmds.objExists(guide_name):
                pos = cmds.xform(guide_name, q=True, ws=True, t=True)
                rot = cmds.xform(guide_name, q=True, ws=True, ro=True)
                
                cmds.select(clear=True)
                jnt_name = f"{self.prefix}_{i:02d}_bind_JNT"
                jnt = cmds.joint(name=jnt_name, p=pos)
                cmds.setAttr(f"{jnt}.rotate", *rot)
                created_joints.append(jnt)
                
                ctrl_name = f"{self.prefix}_{i:02d}_CTRL"
                ctrl = controlsLibrary.create_control_from_lib(
                    lib_name=self.control_style,
                    final_name=ctrl_name
                )
                
                ctrl_gen = self.group_maker.create_rig_hierarchy(ctrl, guide_name)
                cmds.parent(ctrl_gen, ctrl_grp_all)

                cmds.parentConstraint(ctrl, jnt, mo=True)
                
                self.controls.append(ctrl)
                self.control_groups.append(ctrl_gen)
            else:
                cmds.warning(f" No s'ha trobat la guia: {guide_name}")

        if created_joints:
            cmds.parent(created_joints[0], jnt_grp)

        rig_grp = f"{self.root_instance.rig_name}_rig_GRP" if self.root_instance else None
        if rig_grp and cmds.objExists(rig_grp):
            cmds.parent(self.module_grp, rig_grp)
            
        print(f"Build {self.prefix} complet amb èxit.")