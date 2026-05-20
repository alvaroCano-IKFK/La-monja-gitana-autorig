import maya.cmds as cmds
import guides_module
import controlsLibrary
import groups_module
import spine_module

class BodyModule(object):   
    def __init__(self, root_guide="root", 
                 rig_name="Character", 
                 root_instance=None):
        
        self.root_guide= root_guide
        self.rig_name= rig_name

        self.ctrl_style = "bodyControl"

        self.group_maker= groups_module.ControlsGroups()
        self.root_instance= root_instance
        

    def build(self):

        pos_spine = cmds.xform(self.root_guide, q=True, ws=True, t=True)
        cmds.select(clear=True)
        body_joint = cmds.joint(n=f"{self.rig_name}_body_JNT", p=pos_spine)

        #Control
        name = f"{self.rig_name}_body_CTL"
        bodyControl = controlsLibrary.create_control_from_lib(
            lib_name=self.ctrl_style, 
            final_name=name)
        bodyControl_off = self.group_maker.create_rig_hierarchy(bodyControl, self.root_guide)
        cmds.parentConstraint(bodyControl, body_joint)

        print("Body module built successfully.")
