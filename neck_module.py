import maya.cmds as cmds
import controls_module
import spine_module


class NeckModule(object):
    def __init__(self, neck_root="neck_root", neck_end="neck_end", rig_name="Character", num_joints=5,root_instance= None):
        self.neck_root = neck_root
        self.neck_end = neck_end
        self.rig_name = rig_name
        self.num_joints = num_joints
        
        self.joints = []
        self.curve = None 
        self.ctrl_maker = controls_module.Controls(scale=3, color=17)
        self.ctrl_grp =None
        self.neck_grp = None
        self.root_instance = root_instance 

    def build(self):
        
        self.ctrl_grp = cmds.group(em=True, n=f"{self.rig_name}_neckContols_GRP")
        self.neck_grp = cmds.group(em=True, n=f"{self.rig_name}_neck_GRP")
        
        if not cmds.objExists(self.neck_root) or not cmds.objExists(self.neck_end):
            cmds.error(f"Guías no encontradas")

        pos_root = cmds.xform(self.neck_root, q=True, ws=True, t=True)
        pos_head = cmds.xform(self.neck_end, q=True, ws=True, t=True)

        # 1. CREACIÓN DE JOINTS
        self.joints = []
        for i in range(self.num_joints):
            t = i / float(self.num_joints - 1)
            pos = [pos_root[j] + (pos_head[j] - pos_root[j]) * t for j in range(3)]
            cmds.select(clear=True)
            jnt = cmds.joint(p=pos, n=f"{self.rig_name}_neck_{i+1:02d}_JNT")
            if self.joints:
                cmds.parent(jnt, self.joints[-1])
            self.joints.append(jnt)

        cmds.joint(self.joints[0], e=True, oj="yzx", sao="zup", ch=True, zso=True)
        
        # 2. CURVA Y CLUSTERS
        self.curve = cmds.curve(d=1, p=[pos_root, pos_head], n=f"{self.rig_name}_neck_CRV")
        cls_base = cmds.cluster(f"{self.curve}.cv[0]", n=f"{self.rig_name}_neckBase_CLS")[1]
        cls_head = cmds.cluster(f"{self.curve}.cv[1]", n=f"{self.rig_name}_neckHead_CLS")[1]
        
        cmds.parent(self.curve,cls_base,cls_head, self.neck_grp)
        
            
        # 3. SPLINE IK
        ik_results = cmds.ikHandle(
            sj=self.joints[0], 
            ee=self.joints[-1], 
            sol="ikSplineSolver", 
            c=self.curve, 
            ccv=False, 
            pcv=False,
            n=f"{self.rig_name}_neck_IKH"
        )
        ik_h = ik_results[0]
        
        cmds.parent(ik_h, self.neck_grp)
        
        # 4. CONFIGURACIÓN DEL TWIST (Atributos base)
        cmds.setAttr(f"{ik_h}.dTwistControlEnable", 1)
        cmds.setAttr(f"{ik_h}.dWorldUpType", 4) # Object Up (Start/End)
        cmds.setAttr(f"{ik_h}.dForwardAxis", 2) # Y axis
        cmds.setAttr(f"{ik_h}.dWorldUpAxis", 6) # Z axis
        
        # Vectores Up
        cmds.setAttr(f"{ik_h}.dWorldUpVectorX", 1)
        cmds.setAttr(f"{ik_h}.dWorldUpVectorEndX", 1)
        cmds.setAttr(f"{ik_h}.dWorldUpVectorY", 0)
        cmds.setAttr(f"{ik_h}.dWorldUpVectorEndY", 0)
        
        # 5. CONTROLADORES
        # Control Base (Cuello)
        neck_ctl = self.ctrl_maker.circle_ctl_builder(name=f"{self.rig_name}_neck_CTL")
        neck_grp = cmds.group(neck_ctl, n=f"{neck_ctl}_GRP")
        cmds.delete(cmds.parentConstraint(self.joints[0], neck_grp)) 
        cmds.parentConstraint(neck_ctl, cls_base, mo=True)
        
        
        
        # Control Punta (Cabeza)
        head_ctl = self.ctrl_maker.square_ctl_builder(name=f"{self.rig_name}_head_CTL")
        head_grp = cmds.group(head_ctl, n=f"{head_ctl}_GRP")
        cmds.delete(cmds.parentConstraint(self.joints[-1], head_grp))
        cmds.parentConstraint(head_ctl, cls_head, mo=True)
        
        cmds.parentConstraint(neck_ctl,self.joints[0])
        cmds.parentConstraint(neck_ctl,head_ctl, mo=True)
        
        cmds.parent(neck_grp,head_grp, self.ctrl_grp)

        
        # 6. CONEXIONES FINALES (Aquí se usa lo que ya existe)
        chest_ctl_name = f"{self.rig_name}_chestFix_CTL"
        
        
        # Conexión Inicial (World Up Matrix)
        if cmds.objExists(chest_ctl_name):
            # Conectamos la matriz del pecho
            cmds.connectAttr(f"{chest_ctl_name}.worldMatrix[0]", f"{ik_h}.dWorldUpMatrix", f=True)
        else:
            # Si no hay pecho, conectamos el control base del cuello
            cmds.connectAttr(f"{neck_ctl}.worldMatrix[0]", f"{ik_h}.dWorldUpMatrix", f=True)

        # Conexión Final (World Up Matrix End)
        # Ahora head_ctl SÍ existe como variable
        cmds.connectAttr(f"{head_ctl}.worldMatrix[0]", f"{ik_h}.dWorldUpMatrixEnd", f=True)
        

        # ORGANIZACIÓN FINAL
        rig_grp = (
            f"{self.root_instance.rig_name}_rig_GRP"
            if self.root_instance else None
        )
        if rig_grp  and cmds.objExists(rig_grp ):
            cmds.parent(self.joints[0] , rig_grp )
            cmds.parent(self.neck_grp , rig_grp )
            
            
        
        # METER LOS CONTROLADORES DENTRO DEL LOCAL CONTROL            
        local_ctl = self.root_instance.localCtl if self.root_instance else None

        if local_ctl and cmds.objExists(local_ctl):
            cmds.parent(self.ctrl_grp, local_ctl)

        print("Neck Module construido con éxito.")