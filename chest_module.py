import maya.cmds as cmds

import guides_module
#import limbs_module
import spine_module
import controlsLibrary
import groups_module 
import limbModule 

class ChestModule(object):
    def __init__(self,chest_guide = "chest", rig_name = "Character",root_instance=None):
        self.chest_guide = chest_guide
        self.rig_name  = rig_name
        
        #self.ctrl_maker = controls_module.Controls(scale=5, color=17)
        self.ctrl_style = "chestControl"
        self.group_maker = groups_module.ControlsGroups()
                
        self.joints = []
        self.chest_ctrl_grp = None
        self.root_instance = root_instance
                
    def build(self):
        #JOINTS
        
        pos_chest = cmds.xform(self.chest_guide, q=True, ws=True, t=True)

        cmds.select(clear = True)
        
        
        chestFix_joint = cmds.joint(n=f"{self.rig_name}_chestFix_JNT", p = pos_chest)
        
        chest_end_pos =[
                    pos_chest[0],
                    pos_chest[1]-2.5,
                    pos_chest[2]
                    ]
        cmds.select(clear = True)
        
        spineFix_joint = cmds.joint(n=f"{self.rig_name}_spineFix_JNT", p = pos_chest)
        

        cmds.select(clear = True)        
                    
        chest_end = cmds.joint(n=f"{self.rig_name}_chestFixEnd_JNT", p = chest_end_pos)
        
        

        cmds.select(clear = True)
        
        #Falta cambiar la orientacion del joint chestFixEnd
        
        chest_fix_end_pos =[
                    pos_chest[0],
                    pos_chest[1]+2.5,
                    pos_chest[2]
                    ]        
                    
        cmds.select(clear = True)            
        
        localChest_end = cmds.joint(n=f"{self.rig_name}_localChest_JNT", p = chest_fix_end_pos)
        
        #ORDER
        cmds.parent(chest_end, chestFix_joint)
        cmds.parent(localChest_end,spineFix_joint)
        
        
        #CONTROLS 
        name = f"{self.rig_name}_chestFix_CTL"
        chestControl = controlsLibrary.create_control_from_lib(
            lib_name=self.ctrl_style, 
            final_name=name)
        
        # Cambio aquí
        chestContol_off = self.group_maker.create_rig_hierarchy(chestControl, chestFix_joint)
        
        cmds.parentConstraint(chestControl, spineFix_joint, mo=False)
        
        #Conexion con la spine
        
        cmds.aimConstraint(f"{self.rig_name}_spine_3_JNT",chestFix_joint,
                           mo = False, 
                           aim = (0,-1,0),
                           u = (1,0,0),
                           wut = "objectrotation",
                           wu = (0,0,1),
                           wuo = f"{self.rig_name}_chestFix_CTL"
                           ) 
        
        cmds.pointConstraint(chestControl,chestFix_joint)
        
        ik_name = f"{self.rig_name}_spine_IK"
        if cmds.objExists(ik_name) and cmds.objExists(chestControl):
            cmds.connectAttr(f"{chestControl}.worldMatrix[0]", f"{ik_name}.dWorldUpMatrix", force=True)
            print(f"Chest CTL conectado al twist de la espina.")
            
            
        # ORGANIZACIÓN FINAL
        rig_grp = (
            f"{self.root_instance.rig_name}_rig_GRP"
            if self.root_instance else None
        )
        if rig_grp  and cmds.objExists(rig_grp ):
            cmds.parent(chestFix_joint , rig_grp )
            cmds.parent(spineFix_joint , rig_grp )
            
        
        # METER LOS CONTROLADORES DENTRO DEL LOCAL CONTROL            
        local_ctl = self.root_instance.localCtl if self.root_instance else None

        if local_ctl and cmds.objExists(local_ctl):
            cmds.parent(chestContol_off, local_ctl)
             
        
