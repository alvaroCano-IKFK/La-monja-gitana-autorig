import maya.cmds as cmds
import controlsLibrary

class RigRoot(object):
    def __init__(self, rig_name = "Character"):
        self.groups = None
        self.controls = None
        self.rig_name = rig_name
        self.styles = {"global": "masterWalkControl",
                              "local": "localControl"}
        self.mirror_grp = None
    def build(self):
        self.groups = []
        
        masterGroup = cmds.group(em=True, n = f"{self.rig_name}_GRP")
        rigGroup = cmds.group(em=True,n = f"{self.rig_name}_rig_GRP")
        globalRoot = cmds.group(em=True,n = f"{self.rig_name}_C_globalRoot_GRP")
        globalRootAnim = cmds.group(em=True,n = f"{self.rig_name}_C_globalRoot_ANIM")
        localRoot = cmds.group(em=True,n = f"{self.rig_name}_C_localRoot_GRP")
        localRootAnim = cmds.group(em=True,n = f"{self.rig_name}_C_localRoot_ANIM")
        skeleton = cmds.group(em=True, n=f"{self.rig_name}_C_skeleton_GRP")
        guides = cmds.group(em=True, n=f"{self.rig_name}_guides_GRP" )
        controls = cmds.group(em=True, n=f"{self.rig_name}_controls_GRP" )
        
        group_name = f"{self.rig_name}_mirrorBehaviour_GRP"
        if cmds.objExists(group_name):
            cmds.delete(group_name)
            
        self.mirror_grp = cmds.group(em=True, name=group_name)
        cmds.setAttr(f"{self.mirror_grp}.scaleX", -1)
        print(f"Grupo {self.mirror_grp} creado")

        ###################################################
        
        self.controls = []
        
        globalCtl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["global"], 
            final_name=f"{self.rig_name}_global_CTL"
        )
        
        cmds.addAttr(globalCtl, ln="Global_Scale", at="double", min=0.01, max=100, dv=1,k=True)
        cmds.connectAttr(f"{globalCtl}.Global_Scale", f"{globalRoot}.scaleX")
        cmds.connectAttr(f"{globalCtl}.Global_Scale", f"{globalRoot}.scaleY")
        cmds.connectAttr(f"{globalCtl}.Global_Scale", f"{globalRoot}.scaleZ")
        cmds.setAttr(f"{globalCtl}.sx",e=True,l=True,k=False,cb=False)
        cmds.setAttr(f"{globalCtl}.sy",e=True,l=True,k=False,cb=False)
        cmds.setAttr(f"{globalCtl}.s",e=True,l=True,k=False,cb=False)

        self.localCtl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["local"], 
            final_name=f"{self.rig_name}_local_CTL"
        ) 
        
        cmds.parent(globalCtl,globalRootAnim)
        cmds.parent(self.localCtl,localRootAnim)
        
        cmds.parent(rigGroup,masterGroup)
        cmds.parent(globalRoot,controls)
        cmds.parent(globalRootAnim,globalRoot)
        cmds.parent(localRoot,globalCtl)
        cmds.parent(localRootAnim,localRoot)
        cmds.parent(skeleton, masterGroup)
        cmds.parent(guides,masterGroup)
        cmds.parent(controls,masterGroup)
        cmds.parent(self.mirror_grp, self.localCtl)  

        self.groups.extend([masterGroup,
                           rigGroup,
                           globalRoot,
                           globalRootAnim,
                           localRoot,
                           localRootAnim,
                           skeleton])
        
        self.controls.extend([globalCtl,self.localCtl])
        
        

            
  