import maya.cmds as cmds
import controlsLibrary
from groups_module import ControlsGroups
import guides_module
import spine_module


class NeckModule(object):
    def __init__(self, neck_root="neck_root", neck_end="neck_end", rig_name="Character", num_joints=5, root_instance=None):
        self.neck_root = neck_root
        self.neck_end = neck_end
        self.rig_name = rig_name
        self.num_joints = num_joints

        self.joints = []
        self.curve = None
        self.styles = {"mainIk": "squareControl",
                       "mainFk": "circleControl"}

        self.group_maker = ControlsGroups()

        self.ctrl_grp = None
        self.neck_grp = None
        self.root_instance = root_instance

    def build(self):

        self.ctrl_grp = cmds.group(em=True, n=f"{self.rig_name}_neckContols_GRP")
        self.neck_grp = cmds.group(em=True, n=f"{self.rig_name}_neckRig_GRP")

        if not cmds.objExists(self.neck_root) or not cmds.objExists(self.neck_end):
            cmds.error("Guías no encontradas")

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
        # IMPORTANTE: la curva se queda en world space hasta el final.
        # Emparentarla antes de terminar con los clusters rompe los handles.
        self.curve = cmds.curve(d=1, p=[pos_root, pos_head], n=f"{self.rig_name}_neck_CRV")

        cls_base = cmds.cluster(f"{self.curve}.cv[0]", n=f"{self.rig_name}_neckBase_CLS")[1]
        cls_head = cmds.cluster(f"{self.curve}.cv[1]", n=f"{self.rig_name}_neckHead_CLS")[1]

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

        # 4. CONFIGURACIÓN DEL TWIST
        cmds.setAttr(f"{ik_h}.dTwistControlEnable", 1)
        cmds.setAttr(f"{ik_h}.dWorldUpType", 4)   # Object Up (Start/End)
        cmds.setAttr(f"{ik_h}.dForwardAxis", 2)    # Y axis
        cmds.setAttr(f"{ik_h}.dWorldUpAxis", 6)    # Z axis

        cmds.setAttr(f"{ik_h}.dWorldUpVectorX", 1)
        cmds.setAttr(f"{ik_h}.dWorldUpVectorEndX", 1)
        cmds.setAttr(f"{ik_h}.dWorldUpVectorY", 0)
        cmds.setAttr(f"{ik_h}.dWorldUpVectorEndY", 0)

        # 5. CONTROLADORES

        # --- Control Base (Cuello) ---
        name01 = f"{self.rig_name}_neck_CTRL"
        neck_ctl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["mainFk"],
            final_name=name01
        )
        neck_gen = self.group_maker.create_rig_hierarchy(neck_ctl, self.joints[0])

        pivot = cmds.xform(neck_ctl, q=True, ws=True, rp = True)
        shapes = cmds.listRelatives(neck_ctl, s=True)
        for shape in shapes:
            num_cvs = cmds.getAttr(f"{shape}.spans") + cmds.getAttr(f"{shape}.degree")
            cvs = [f"{shape}.cv[{j}]" for j in range(num_cvs)]
            cmds.rotate(10, 0, 90, cvs, r=True, p=pivot, ws=True)

        # --- Control Punta (Cabeza) ---
        name02 = f"{self.rig_name}_head_CTRL"
        head_ctl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["mainIk"],
            final_name=name02
        )
        head_gen = self.group_maker.create_rig_hierarchy(head_ctl, self.joints[-1])

        # =================================================================
        # 6. ORGANIZACIÓN EN EL OUTLINER (¡VA PRIMERO!)
        # =================================================================
        # Primero estructuramos limpiamente todas las piezas del Rig en sus grupos
        cmds.parent(neck_gen, head_gen, self.ctrl_grp)
        
        cmds.parent(cls_base, self.neck_grp)
        cmds.parent(cls_head, self.neck_grp)
        cmds.parent(self.curve, self.neck_grp)
        cmds.parent(ik_h, self.neck_grp)


        # =================================================================
        # 7. CONSTRAINTS Y RELACIONES (¡AHORA SÍ!)
        # =================================================================
        # Ya que todo está en su grupo final en el Outliner, hacemos los constraints seguros
        cmds.parentConstraint(neck_ctl, cls_base, mo=True)
        cmds.parentConstraint(head_ctl, cls_head, mo=True)
        
        # El control del cuello maneja al joint raíz del cuello
        cmds.parentConstraint(neck_ctl, self.joints[0], mo=True)
        
        # El cuello lidera jerárquicamente al grupo de la cabeza
        cmds.parentConstraint(neck_ctl, head_gen, mo=True)


        # =================================================================
        # 8. CONEXIONES FINALES (Twist world up matrix)
        # =================================================================
        chest_ctl_name = f"{self.rig_name}_chestFix_CTL"

        if cmds.objExists(chest_ctl_name):
            cmds.connectAttr(f"{chest_ctl_name}.worldMatrix[0]", f"{ik_h}.dWorldUpMatrix", f=True)
        else:
            cmds.connectAttr(f"{neck_ctl}.worldMatrix[0]", f"{ik_h}.dWorldUpMatrix", f=True)

        cmds.connectAttr(f"{head_ctl}.worldMatrix[0]", f"{ik_h}.dWorldUpMatrixEnd", f=True)


        # =================================================================
        # 9. ORGANIZACIÓN FINAL EN LOS GRUPOS MAESTROS
        # =================================================================
        rig_grp = (
            f"{self.root_instance.rig_name}_rig_GRP"
            if self.root_instance else None
        )
        if rig_grp and cmds.objExists(rig_grp):
            cmds.parent(self.joints[0], rig_grp)
            cmds.parent(self.neck_grp, rig_grp)

        # Colocar el contenedor de controles dentro del control local global
        local_ctl = self.root_instance.localCtl if self.root_instance else None
        if local_ctl and cmds.objExists(local_ctl):
            cmds.parent(self.ctrl_grp, local_ctl)

        # CONEXIÓN SEGURA CON EL PECHO:
        # Reemplazamos tu antiguo cmds.parent(neck_gen, chestControl) por un parentConstraint.
        # Esto evita alterar la jerarquía pura de tus módulos y mantiene el Outliner impecable.
        chestControl = f"{self.rig_name}_chestFix_CTL"
        if cmds.objExists(chestControl):
            cmds.parentConstraint(chestControl, neck_gen, mo=True)
            print("Conectado el grupo del cuello (neck_gen) al control del pecho mediante constraint.")

        print("Neck Module construido con éxito.")