import maya.cmds as cmds
import spine_module
import controlsLibrary
import guides_module
import groups_module 


class HipModule(object):
    def __init__(self,root_guide ="root", 
                rig_name="Character",
                root_instance=None
                ):
                    
        self.root_guide = root_guide
        self.rig_name  = rig_name
        
        #self.ctrl_maker = controls_module.Controls(scale=5, color=17) # 17 es amarillo
        self.ctrl_style = "hipControl"
        self.group_maker = groups_module.ControlsGroups()
        self.root_instance = root_instance 

               
    def build(self):
        
        pos_hip = cmds.xform(self.root_guide,q=True, ws=True, t=True) 
        
        cmds.select(clear = True)
        
        hip_joint = cmds.joint(n=f"{self.rig_name}_hip_JNT", p=pos_hip)

        hip_end_pos =[
                    pos_hip[0],
                    pos_hip[1]-2.5,
                    pos_hip[2]
                    ]
                    
        hip_end_joint = cmds.joint(n=f"{self.rig_name}_hipEnd_JNT", p =hip_end_pos)
        
        #Controls(TO DO:Switch to wave ctl)
        
        name = f"{self.rig_name}_localHip_CTL"
        hipControl = controlsLibrary.create_control_from_lib(
            lib_name=self.ctrl_style, 
            final_name=name)
        
        # Cambio aquí
        hipControl_off = self.group_maker.create_rig_hierarchy(hipControl, self.root_guide)
        cmds.parentConstraint(hipControl, hip_joint)
        
        # Conectar el hip CTL como World Up End del IK de la espina
        ik_name = f"{self.rig_name}_spine_IK"
        if cmds.objExists(ik_name) and cmds.objExists(hipControl):
            cmds.connectAttr(f"{hipControl}.worldMatrix[0]", f"{ik_name}.dWorldUpMatrixEnd", force=True)
            print(f"Hip CTL conectado al twist de la espina.")
                
        # ORGANIZACIÓN FINAL
        rig_grp = (
            f"{self.root_instance.rig_name}_rig_GRP"
            if self.root_instance else None
        )
        if rig_grp  and cmds.objExists(rig_grp ):
            cmds.parent(hip_joint , rig_grp )
            
        
        # METER LOS CONTROLADORES DENTRO DEL LOCAL CONTROL            
        local_ctl = self.root_instance.localCtl if self.root_instance else None

        if local_ctl and cmds.objExists(local_ctl):
            cmds.parent(hipControl_off, local_ctl)
             
