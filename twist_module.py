import maya.cmds as cmds
from functools import partial 
import os
import math
import json
import guides_module
import limbs_module
import leg_module
#import rigRoot_module
import curvature_module
from nodeCreator_module import NodeCreator

class TwistModule(object):  
    def __init__(self, name, side, parent=None, root_instance = None):
        self.name = name
        self.side = side
        self.parent = parent
        self.root_instance = root_instance

        self.start_joint = None
        self.mid_joint = None
        self.end_joint = None

        self.base_curve = None
        self.upper_curve = None
        self.lower_curve = None

        self.nonroll_upper_start = None
        self.nonroll_upper_end = None
        
        self.upper_twist_start = None
        self.upper_twist_end = None
        self.lower_twist_start = None
        self.lower_twist_end = None

        self.upper_motion_paths = []
        self.lower_motion_paths = []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _has_rotation_driver(node):
        """True si algo conduce la rotacion de este nodo."""
        for plug in ("rotate", "rotateX", "rotateY", "rotateZ", "offsetParentMatrix"):
            if cmds.listConnections(f"{node}.{plug}", source=True, destination=False):
                return True
        return False

    def _follows_rig(self, node):
        """
        Heuristica: comprueba si 'node' rota de verdad con el personaje.

        Sube por la jerarquia buscando o bien un driver de rotacion (un
        constraint, una conexion) o bien un control. Si no encuentra ninguna
        de las dos cosas, el nodo esta colgando de grupos inertes y su
        orientacion esta anclada al mundo.

        Es exactamente el caso de leg_GRP bajo rig_GRP: rig_GRP solo tiene un
        scaleConstraint, que conecta escala y no rotacion, asi que nada de esa
        rama gira con el rig.
        """
        current = node
        while current:
            if current.endswith("_CTL") or current.endswith("_CTRL"):
                return True
            if self._has_rotation_driver(current):
                return True
            current = (cmds.listRelatives(current, parent=True) or [None])[0]
        return False

    def basic_twist_setup(self, start_joint, mid_joint, end_joint, nonroll_ref=None):
        """
        Monta la cadena non roll y las dos cadenas de twist del segmento.

        Args:
            nonroll_ref (str): Nodo que da la REFERENCIA DE ROLL al non roll.
                Si no se pasa, se usa el padre de start_joint (la clavicula en
                el brazo, la cadera en la pierna), que es lo correcto en el
                99% de los casos. Ver el comentario largo junto al
                orientConstraint de ik_hdl_upper para entender por que esto no
                es opcional.
        """
        # NON ROLL
        self.nonroll_upper_start = cmds.duplicate(start_joint, po=True, n=f"{self.side}_{self.name}_upperNonRollStart_JNT")[0]
        if cmds.listRelatives(self.nonroll_upper_start, parent=True):
            cmds.parent(self.nonroll_upper_start, w=True)[0]

        self.nonroll_upper_end = cmds.duplicate(mid_joint, po=True, n=f"{self.side}_{self.name}_upperNonRollEnd_JNT")[0]
        if cmds.listRelatives(self.nonroll_upper_end, parent=True):
            cmds.parent(self.nonroll_upper_end, w=True)[0]

        cmds.matchTransform(self.nonroll_upper_start, start_joint, pos=True, rot=True)
        cmds.matchTransform(self.nonroll_upper_end, mid_joint, pos=True, rot=True)
        
        cmds.parent(self.nonroll_upper_end, self.nonroll_upper_start)
        cmds.select(cl=True)
        cmds.pointConstraint(start_joint, self.nonroll_upper_start)

        ik_hdl_upper = cmds.ikHandle(sj=self.nonroll_upper_start, ee=self.nonroll_upper_end, sol="ikSCsolver", name=f"{self.side}_{self.name}UpperNonRollIk_HDL")[0]
        cmds.pointConstraint(mid_joint, ik_hdl_upper, mo=False)

        # ------------------------------------------------------------------
        # REFERENCIA DE ROLL DEL NON ROLL  (no quitar: aqui estaba el bug)
        # ------------------------------------------------------------------
        # El ikSCsolver no solo apunta la cadena al handle: tambien le pasa la
        # ROTACION del handle, y eso es lo que fija el roll de la cadena.
        #
        # Con solo el pointConstraint de arriba esa rotacion no la conduce
        # nadie: se queda con el valor del momento de la creacion, congelada en
        # el espacio local del handle. Y el handle acaba colgando de
        # twist_GRP > C_twist_GRP > <rig>_rig_GRP, que en rigRoot_module solo
        # recibe un scaleConstraint. O sea que rig_GRP NO rota con el rig, y el
        # roll del non roll queda anclado al MUNDO.
        #
        # Consecuencia: al girar el global, el local o el body, el solver lee
        # esa diferencia como twist y hace rodar la cadena non roll el mismo
        # angulo que has girado. Y como de nonroll_upper_start cuelga el
        # upper_twist_start, y de el sale el worldUpMatrix de los motionPath
        # del segmento upper, se lleva por delante el twist, las bendies y la
        # piel. Pasaba en brazos y piernas, en IK y en FK.
        #
        # La referencia correcta es el PADRE del segmento (clavicula / cadera):
        # ese si rota con el personaje, y el non roll sigue sin heredar el
        # twist del propio hombro, que es lo unico que debe ignorar.
        if nonroll_ref is None:
            nonroll_ref = (cmds.listRelatives(start_joint, parent=True) or [None])[0]

        if nonroll_ref and cmds.objExists(nonroll_ref):
            if not self._follows_rig(nonroll_ref):
                # Le paso esto al brazo y funciona, a la pierna y no: el muslo
                # cuelga de leg_GRP, un grupo vacio bajo rig_GRP. Si la
                # referencia no gira con el personaje, el arreglo no arregla
                # nada, asi que mejor cantarlo aqui que descubrirlo girando el
                # master.
                cmds.warning(f"[{self.side}_{self.name}] '{nonroll_ref}' no parece seguir al "
                             "rig: ningun control ni driver de rotacion en su jerarquia. El "
                             "non roll seguira rodando al girar el personaje. Pasa un "
                             "nonroll_ref explicito (el control raiz del segmento).")

            cmds.orientConstraint(nonroll_ref, ik_hdl_upper, mo=True)
            print(f"[TwistModule] {self.side}_{self.name}: non roll referenciado a "
                  f"'{nonroll_ref}'.")
        else:
            cmds.warning(f"[{self.side}_{self.name}] El non roll se queda sin referencia de "
                         f"roll ({start_joint} no tiene padre y no se paso nonroll_ref). "
                         "Rodara al girar el rig: pasale un nodo que siga al personaje.")
        # ------------------------------------------------------------------

        # TWIST
        self.upper_twist_start = cmds.duplicate(start_joint, po=True, n=f"{self.side}_{self.name}_upperTwistStart_JNT")[0]
        if cmds.listRelatives(self.upper_twist_start, parent=True):
            cmds.parent(self.upper_twist_start, w=True)[0]

        self.upper_twist_end = cmds.duplicate(mid_joint, po=True, n=f"{self.side}_{self.name}_upperTwistEnd_JNT")[0]
        if cmds.listRelatives(self.upper_twist_end, parent=True):
            cmds.parent(self.upper_twist_end, w=True)[0]

        cmds.matchTransform(self.upper_twist_start, start_joint, pos=True, rot=True)
        cmds.matchTransform(self.upper_twist_end, mid_joint, pos=True, rot=True)

        cmds.parent(self.upper_twist_end, self.upper_twist_start)

        # Emparentar bajo el non roll ANTES de crear el IK y limpiar orientacion:
        # asi rotateX del twist es directamente el twist relativo al non roll.
        cmds.parent(self.upper_twist_start, self.nonroll_upper_start)
        cmds.setAttr(f"{self.upper_twist_start}.translate", 0, 0, 0)
        cmds.setAttr(f"{self.upper_twist_start}.rotate", 0, 0, 0)
        cmds.setAttr(f"{self.upper_twist_start}.jointOrient", 0, 0, 0)

        cmds.select(cl=True)
        ik_hdl_upper_twist = cmds.ikHandle(sj=self.upper_twist_start, ee=self.upper_twist_end, sol="ikSCsolver", name=f"{self.side}_{self.name}UpperTwist_HDL")[0]

        # Posicion: el codo (sigue el stretch). Orientacion: el hombro -> aporta el roll.
        cmds.pointConstraint(mid_joint, ik_hdl_upper_twist, mo=False)
        cmds.orientConstraint(start_joint, ik_hdl_upper_twist, mo=True)

        self.lower_twist_start = cmds.duplicate(mid_joint, po=True, n=f"{self.side}_{self.name}_lowerTwistStart_JNT")[0]
        cmds.parent(self.lower_twist_start, mid_joint)

        self.lower_twist_end = cmds.duplicate(end_joint, po=True, n=f"{self.side}_{self.name}_lowerTwistEnd_JNT")[0]
        if cmds.listRelatives(self.lower_twist_end, parent=True):
            cmds.parent(self.lower_twist_end, w=True)[0]

        cmds.matchTransform(self.lower_twist_start, mid_joint, pos=True, rot=True)
        cmds.matchTransform(self.lower_twist_end, end_joint, pos=True, rot=True)

        cmds.parent(self.lower_twist_end, self.lower_twist_start)
        cmds.select(cl=True)
        ik_hdl_lower_twist = cmds.ikHandle(sj=self.lower_twist_start, ee=self.lower_twist_end, sol="ikSCsolver", name=f"{self.side}_{self.name}LowerTwist_HDL")[0]

        cmds.parentConstraint(end_joint, ik_hdl_lower_twist, mo=True)

        return [self.nonroll_upper_start, ik_hdl_upper, ik_hdl_upper_twist, ik_hdl_lower_twist]
    
    def create_twist_joints(self, motion_paths_list, segment_name):
        twist_joints = []
        for i, mpa_node in enumerate(motion_paths_list):
            cmds.select(cl=True)
            joint_name = f"{self.side}_{self.name}_{segment_name}Twist_0{i+1}_JNT"
            twist_jnt = cmds.joint(n=joint_name)

            cmds.connectAttr(f"{mpa_node}.allCoordinates", f"{twist_jnt}.translate")
            cmds.connectAttr(f"{mpa_node}.rotate", f"{twist_jnt}.rotate")
            
            twist_joints.append(twist_jnt)

        for jnt in twist_joints:
            cmds.setAttr(f"{jnt}.inheritsTransform", 0) 
        return twist_joints

        
    def create_basic_curve(self, start_joint, mid_joint, end_joint,
                        aim_axis="x", up_axis="y",
                        front_axis_idx=None, up_axis_idx=None,
                        source_curve=None, nonroll_ref=None):   # ← parámetros nuevos
        
        self.start_joint = start_joint
        self.mid_joint   = mid_joint
        self.end_joint   = end_joint

        # nonroll_ref viaja tal cual hasta el orientConstraint del handle del
        # non roll. None = se deduce del padre de start_joint.
        base_twist = self.basic_twist_setup(start_joint, mid_joint, end_joint,
                                            nonroll_ref=nonroll_ref)

        # ==============================================================
        # CURVAS DE SEGMENTO
        # ==============================================================
        if source_curve and cmds.objExists(source_curve):
            # Usamos la degree2_curve del CurvatureModule directamente.
            # NO se duplica — el detach se hace sobre ella misma.
            self.base_curve = source_curve
            print(f"[TwistModule] Usando degree2_curve de CurvatureModule: '{source_curve}'")
        else:
            # Fallback: crea una curva propia
            pos_start = cmds.xform(start_joint, q=True, ws=True, t=True)
            pos_mid   = cmds.xform(mid_joint,   q=True, ws=True, t=True)
            pos_end   = cmds.xform(end_joint,   q=True, ws=True, t=True)
            self.base_curve = cmds.curve(
                degree=2, p=[pos_start, pos_mid, pos_end],
                name=f"{self.side}_{self.name}BaseDriver_CRV"
            )
            print(f"[TwistModule] Curva base creada internamente (fallback).")
        cmds.setAttr(f"{self.base_curve}.inheritsTransform", 0)


        # El detach SIEMPRE se hace aquí sobre self.base_curve
        detach_result = cmds.detachCurve(
            f"{self.base_curve}.u[0.5]",
            ch=True,
            k=[True, True],
            rpo=False   # keepOriginal=True, no destruye la degree2_curve
        )
        self.upper_curve = cmds.rename(detach_result[0],
                                    f"{self.side}_{self.name}UpperSegment_CRV")
        self.lower_curve = cmds.rename(detach_result[1],
                                    f"{self.side}_{self.name}LowerSegment_CRV")
        
        cmds.setAttr(f"{self.upper_curve}.inheritsTransform", 0)
        cmds.setAttr(f"{self.lower_curve}.inheritsTransform", 0)

        history     = cmds.listHistory(self.upper_curve)
        detach_node = cmds.ls(history, type="detachCurve")[0]
        cmds.setAttr(f"{detach_node}.parameter[0]", 0.5)
            

        cmds.rename(self.base_curve, f"{self.side}_{self.name}BaseDriver_CRV")

        axis_map = {"x": 0, "y": 1, "z": 2, "xneg": 0, "yneg": 1, "zneg": 2}
            
        if front_axis_idx is None:
            front_axis_idx = axis_map.get(aim_axis.lower(), 0)
        if up_axis_idx is None:
            up_axis_idx = axis_map.get(up_axis.replace("neg","").lower(), 1)

        vector_map = {
                "x": (1.0, 0.0, 0.0),
                "y": (0.0, 1.0, 0.0),
                "z": (0.0, 0.0, 1.0),
                "xneg": (-1.0,  0.0,  0.0),
                "yneg": ( 0.0, -1.0,  0.0),
                "zneg": ( 0.0,  0.0, -1.0),
            }
            
            # El vector se obtiene de forma pura según lo que dictaminó el módulo padre
        up_vector = vector_map.get(up_axis.lower(), (0.0, 1.0, 0.0))

        self.upper_motion_paths = []
        self.lower_motion_paths = []
        self.upper_twist_joints = []
        self.lower_twist_joints = []

        for crv in [self.upper_curve, self.lower_curve]:
            crv_shape = cmds.listRelatives(crv, shapes=True)[0]
                
            if crv == self.upper_curve:
                segment_name = "upper"
                target_list = self.upper_motion_paths
                twist_start_joint = self.upper_twist_start
            else:
                segment_name = "lower"
                target_list = self.lower_motion_paths
                twist_start_joint = self.lower_twist_start

            # upper: upper_twist_start es hijo del non roll -> su rotateX ya es el twist limpio
            # lower: lower_twist_start es hijo del mid_joint -> igual
            twist_source = f"{twist_start_joint}.rotateX"

            # Inversión matemática del valor de rotación frontTwist para comportamiento de espejo en R
            if self.side == "R":
                md_mirror = NodeCreator(
                        side=self.side, node_type="multiplyDivide", 
                        base_name=self.name, name=f"{segment_name}Mirror", 
                        tag="invert", parent=None, custom_suffix="MDN"
                    )
                md_mirror_node = md_mirror.create()
                cmds.connectAttr(twist_source, f"{md_mirror_node}.input1X")
                cmds.setAttr(f"{md_mirror_node}.input2X", -1.0)
                final_twist_source = f"{md_mirror_node}.outputX"
            else:
                final_twist_source = twist_source

            md_path = NodeCreator(side=self.side, node_type="multiplyDivide", base_name=self.name, name=segment_name, tag="segment", parent=None, custom_suffix="MDN")
            md_node = md_path.create()

            cmds.connectAttr(final_twist_source, f"{md_node}.input1X")
            cmds.connectAttr(final_twist_source, f"{md_node}.input1Y")
            cmds.connectAttr(final_twist_source, f"{md_node}.input1Z")

            for i in range(5):
                motion_path = NodeCreator(side=self.side, node_type="motionPath", base_name=self.name, name=segment_name, tag="segment", parent=None, custom_suffix="MPA")
                motion_path_node = motion_path.create()
                cmds.connectAttr(f"{crv_shape}.worldSpace[0]", f"{motion_path_node}.geometryPath")
                    
                cmds.setAttr(f"{motion_path_node}.fractionMode", True)
                cmds.setAttr(f"{motion_path_node}.follow", True)

                cmds.setAttr(f"{motion_path_node}.frontAxis", front_axis_idx)
                cmds.setAttr(f"{motion_path_node}.upAxis", up_axis_idx)

                    # Método estable usando el vector calculado
                cmds.setAttr(f"{motion_path_node}.worldUpType", 2)
                cmds.setAttr(f"{motion_path_node}.worldUpVector", up_vector[0], up_vector[1], up_vector[2])
                
                if segment_name == "upper":
                    # Conectamos la matriz mundial del joint nonroll al worldUpMatrix del motionPath
                    cmds.connectAttr(f"{self.nonroll_upper_start}.worldMatrix[0]", f"{motion_path_node}.worldUpMatrix")
                else:
                    # Conectamos la matriz mundial del codo/rodilla (mid_joint) al worldUpMatrix del motionPath
                    cmds.connectAttr(f"{mid_joint}.worldMatrix[0]", f"{motion_path_node}.worldUpMatrix")
                # ==============================================================
                    
                                  
                #if self.side == "R":
                    #cmds.setAttr(f"{motion_path_node}.inverseUp", 1)
                    #cmds.setAttr(f"{motion_path_node}.inverseFront", 1)

                u_value = 0.01 + ((i / 4.0) * 0.98)
                cmds.setAttr(f"{motion_path_node}.uValue", u_value)

                target_list.append(motion_path_node)

                if i == 0:
                    pass
                elif i == 4:
                    cmds.connectAttr(final_twist_source, f"{motion_path_node}.frontTwist")
                elif i == 1:    
                    cmds.setAttr(f"{md_node}.input2X", u_value)
                    cmds.connectAttr(f"{md_node}.outputX", f"{motion_path_node}.frontTwist")
                elif i == 2:  
                    cmds.setAttr(f"{md_node}.input2Y", u_value)
                    cmds.connectAttr(f"{md_node}.outputY", f"{motion_path_node}.frontTwist")
                elif i == 3:  
                    cmds.setAttr(f"{md_node}.input2Z", u_value)
                    cmds.connectAttr(f"{md_node}.outputZ", f"{motion_path_node}.frontTwist")

                
        self.upper_twist_joints = self.create_twist_joints(self.upper_motion_paths, "upper")
        self.lower_twist_joints = self.create_twist_joints(self.lower_motion_paths, "lower")
            
        #cmds.parent(self.upper_twist_joints,start_joint )

        #cmds.parentConstraint(start_joint, self.upper_curve, mo=True)
        #cmds.parentConstraint(mid_joint, self.lower_curve, mo=True)

        # ---- ORGANIZACIÓN ----
        # general_twist_GRP: singleton — se crea solo si no existe todavía.
        # La primera extremidad lo crea; las siguientes lo reutilizan.
        general_twist_grp_name = "C_twist_GRP"
        if not cmds.objExists(general_twist_grp_name):
            self.general_twist_GRP = cmds.group(em=True, n=general_twist_grp_name)
        else:
            self.general_twist_GRP = general_twist_grp_name

        # twist_GRP individual por extremidad: recoge todo excepto lowerTwistStart,
        # que debe quedarse emparentado bajo el bind mid_joint.
        twist_GRP = cmds.group(em=True, n=f"{self.side}_{self.name}_twist_GRP")

        # BaseDriver_CRV (la curva original renombrada, puede estar suelta)
        base_driver_crv = f"{self.side}_{self.name}BaseDriver_CRV"
        if cmds.objExists(base_driver_crv):
            if not cmds.listRelatives(base_driver_crv, parent=True):
                cmds.parent(base_driver_crv, twist_GRP)
        # Las curvas upper/lower solo se emparentan al twist_GRP si son propias de este módulo.
        # Si vienen del CurvatureModule (source_curve), ya viven en su propio grupo.
        if cmds.objExists(self.upper_curve) and cmds.objExists(self.lower_curve):
            cmds.parent(self.upper_curve, self.lower_curve, twist_GRP)

            # Joints de twist (creados por create_twist_joints, nacen sueltos)
        for jnt in self.upper_twist_joints + self.lower_twist_joints:
            if cmds.objExists(jnt) and not cmds.listRelatives(jnt, parent=True):
                cmds.parent(jnt, twist_GRP)

            # nonroll_upper_start ya lleva dentro:
            #   - nonroll_upper_end
            #   - upper_twist_start (con upper_twist_end)
        nonroll_start = base_twist[0]  # nonroll_upper_start
        ik_handles    = base_twist[1:] # ik_hdl_upper, ik_hdl_upper_twist, ik_hdl_lower_twist

        if cmds.objExists(nonroll_start):
            if not cmds.listRelatives(nonroll_start, parent=True):
                cmds.parent(nonroll_start, twist_GRP)

            # IK handles sueltos
        for hdl in ik_handles:
            if cmds.objExists(hdl):
                if not cmds.listRelatives(hdl, parent=True):
                        cmds.parent(hdl, twist_GRP)

            # Emparentar el grupo individual bajo el general
        cmds.parent(twist_GRP, self.general_twist_GRP)

        self.twist_GRP = twist_GRP
            
        rig_grp = f"{self.root_instance.rig_name}_rig_GRP" if self.root_instance else None
        if rig_grp and cmds.objExists(rig_grp):
            current_parent = cmds.listRelatives(self.general_twist_GRP, parent=True)
            if not current_parent or current_parent[0] != rig_grp:
                cmds.parent(self.general_twist_GRP, rig_grp)
                
            
        return self.general_twist_GRP