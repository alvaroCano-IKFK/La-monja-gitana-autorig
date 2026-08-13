import maya.cmds as cmds    
import maya.mel as mel
import guides_module
import controlsLibrary
from groups_module import ControlsGroups
from nodeCreator_module import NodeCreator
import rigRoot_module

class JawModule(object):
    
    def __init__(self, 
                 jaw_root="jaw_root", 
                 jaw_end="jaw_end", 
                 root_instance=None, 
                 mouth_instances=None,      
                 rig_name="Character",
                 side="C"):
        

        self.jaw_root = jaw_root
        self.jaw_end = jaw_end
        self.group_maker = ControlsGroups()
        self.rig_name = rig_name
        self.root_instance = root_instance
        self.mouth_instances = mouth_instances or []
        self.styles = {"mainFk": "squareControl"}
        
        self.side = side
        self.prefix = f"{self.side}_{rig_name}"

        # Nodos que expone el modulo para que otros (la boca) puedan
        # engancharse sin tener que reconstruir los nombres a mano.
        self.jaw_upper_jnt = None
        self.jaw_lower_jnt = None
        self.jaw_upper_ctrl = None
        self.jaw_lower_ctrl = None
        self.jaw_upper_local_trn = None
        self.jaw_lower_local_trn = None
        
        
    def _offset_control_shape(self, ctrl, move=(0, 0, 0), rotate=(0, 0, 0), scale=1.0):
        """
        Mueve/rota/escala las CVs de un control sin tocar su transform.
        El pivote no se mueve y los canales quedan a 0.
        """
        shapes = cmds.listRelatives(ctrl, shapes=True, type="nurbsCurve", fullPath=True) or []
        if not shapes:
            cmds.warning(f"[Jaw] '{ctrl}' no tiene shapes de curva.")
            return

        # Todas las CVs de todas las shapes, de golpe
        cvs = []
        for shape in shapes:
            cvs.extend(cmds.ls(f"{shape}.cv[*]", flatten=True))

        pivot = cmds.xform(ctrl, q=True, ws=True, rp=True)

        if any(rotate):
            cmds.rotate(rotate[0], rotate[1], rotate[2], cvs, r=True, p=pivot, os=True)
        if scale != 1.0:
            cmds.scale(scale, scale, scale, cvs, r=True, p=pivot)
        if any(move):
            cmds.move(move[0], move[1], move[2], cvs, r=True, os=True)    

    def _get_rig_group(self, ctrl_grp, suffix):
        """
        Devuelve el grupo con ese sufijo dentro de la jerarquia que crea
        create_rig_hierarchy (GRP > SPC > OFF > SDK > ANIM).

        :param ctrl_grp: el _GRP raiz que devuelve create_rig_hierarchy
        :param suffix:   'SPC', 'OFF', 'SDK' o 'ANIM'
        """
        for node in cmds.listRelatives(ctrl_grp, allDescendents=True, type="transform") or []:
            if node.endswith(f"_{suffix}"):
                return node
        cmds.warning(f"[Jaw] No encuentro el grupo '_{suffix}' bajo '{ctrl_grp}'.")
        return None

    def _get_local_mult_matrix(self, ctrl):
        """
        Devuelve el multMatrix que cuelga del '.matrix' de un control.

        Lo buscamos por conexion y no por nombre: el sufijo final lo decide
        NodeCreator, asi que reconstruirlo con un f-string es fragil.
        '.matrix' es un output del control, asi que el multMatrix esta en el
        lado DESTINO de la conexion (source=False, destination=True).

        :param ctrl: nombre del control (ej. 'C_Character_jawLower_CTRL')
        :return:     nombre del multMatrix o None si no existe
        """
        if not cmds.objExists(ctrl):
            cmds.warning(f"[Jaw] El control '{ctrl}' no existe.")
            return None

        nodes = cmds.listConnections(
            f"{ctrl}.matrix",
            source=False,
            destination=True,
            type="multMatrix"
        ) or []

        if not nodes:
            cmds.warning(f"[Jaw] No encuentro ningun multMatrix conectado a '{ctrl}.matrix'.")
            return None

        return nodes[0]

    def _build_off_network(self, prefix, base_name, source_ctrl, source_ctrl_grp):
        """
        Crea el space-tracking local (_OFF / _TRN) de un control: el _TRN
        replica el movimiento LOCAL del control (su .matrix), no el global.

        Devuelve (local_off, local_trn).
        """
        local_off, local_trn = self.group_maker.create_space_tracking_hierarchy(
            space_base_name=f"{prefix}_{base_name}Local",
            target_joint=source_ctrl_grp,
            parent_group=None
        )

        mult_node = NodeCreator(
            side=prefix, node_type="multMatrix", base_name=base_name,
            name="Local", tag="CTRL", parent=None, custom_suffix=None
        ).create()
        decompose_node = NodeCreator(
            side=prefix, node_type="decomposeMatrix", base_name=base_name,
            name="Local", tag="CTRL", parent=None, custom_suffix=None
        ).create()
        # OJO: antes este nodo se creaba con los mismos argumentos que el
        # anterior, asi que Maya le metia un sufijo numerico para desambiguar.
        # Con un 'name' distinto el nombre queda limpio y predecible.
        decompose_trn_node = NodeCreator(
            side=prefix, node_type="decomposeMatrix", base_name=base_name,
            name="LocalTrn", tag="CTRL", parent=None, custom_suffix=None
        ).create()

        cmds.connectAttr(f"{source_ctrl}.matrix", f"{mult_node}.matrixIn[0]")
        cmds.connectAttr(f"{mult_node}.matrixSum", f"{decompose_node}.inputMatrix")
        cmds.connectAttr(f"{decompose_node}.outputTranslate", f"{local_trn}.translate")
        cmds.connectAttr(f"{decompose_node}.outputRotate", f"{local_trn}.rotate")
        cmds.connectAttr(f"{decompose_node}.outputScale", f"{local_trn}.scale")
        cmds.connectAttr(f"{local_trn}.worldMatrix[0]", f"{decompose_trn_node}.inputMatrix")

        return local_off, local_trn
    
    def _get_mouth_corner_controls(self):
            """
            Devuelve {side: ctrl} de las comisuras de la boca (end_LIP_CTRL).

            Primero mira las instancias de MouthModule que nos hayan pasado;
            si no hay, cae al nombre en escena. El nombre es determinista
            ({side}_{rig_name}_end_LIP_CTRL), asi que el fallback es seguro.
            """
            corners = {}

            for mouth in self.mouth_instances:
                ctrl = getattr(mouth, "end_lip_ctrl", None)
                if ctrl and cmds.objExists(ctrl):
                    corners[mouth.side] = ctrl

            if not corners:
                for side in ("L", "R"):
                    ctrl = f"{side}_{self.rig_name}_end_LIP_CTRL"
                    if cmds.objExists(ctrl):
                        corners[side] = ctrl

            if not corners:
                cmds.warning("[Jaw] No encuentro las comisuras de la boca. "
                            "Construye el MouthModule antes que el jaw.")
            return corners
        
    def _create_corner_joints(self):
            """Crea un JNT por comisura, en la posicion del control y orientado
            como el jaw_root (para que el rotateX del jaw sea el eje limpio)."""
            corners = self._get_mouth_corner_controls()
            corner_joints = {}

            for side, ctrl in corners.items():
                jnt_name = f"{side}_{self.rig_name}_jawCorner_JNT"
                if cmds.objExists(jnt_name):
                    corner_joints[side] = jnt_name
                    continue

                pos = cmds.xform(ctrl, q=True, ws=True, t=True)
                cmds.select(clear=True)
                jnt = cmds.joint(n=jnt_name, p=pos)
                cmds.matchTransform(jnt, self.jaw_root, rot=True, pos=False)
                cmds.makeIdentity(jnt, apply=True, r=True)

                corner_joints[side] = jnt

            return corner_joints
        
    def _constrain_corner_joints(self, corner_joints, jaw_upper_jnt,
                                 jaw_lower_jnt, driver_ctrl):
        """
        Constrainea cada comisura entre jawUpper y jawLower.
        Los dos pesos van conectados con valores complementarios: uno recibe
        el atributo directo y el otro el mismo atributo pasado por un reverse.
        """
        constraints = {}

        for side, corner_jnt in corner_joints.items():
            attr = f"{driver_ctrl}.{side}UpperLower"
            if not cmds.objExists(attr):
                cmds.warning(f"[Jaw] No existe el atributo '{attr}'.")
                continue

            existing = cmds.listRelatives(corner_jnt, type="parentConstraint") or []
            if existing:
                constraints[side] = existing[0]
                continue

            constraint = cmds.parentConstraint(
                jaw_upper_jnt, jaw_lower_jnt, corner_jnt, mo=True
            )[0]
            cmds.setAttr(f"{constraint}.interpType", 2)  # Shortest, evita flips

            # Emparejamos alias con target por nombre, no por indice: el orden
            # de los targets no siempre coincide con el orden en que los pasamos.
            targets = cmds.parentConstraint(constraint, q=True, targetList=True)
            weights = cmds.parentConstraint(constraint, q=True, weightAliasList=True)
            alias_by_target = dict(zip(targets, weights))

            upper_weight = alias_by_target[jaw_upper_jnt]
            lower_weight = alias_by_target[jaw_lower_jnt]

            reverse_node = NodeCreator(
                side=f"{side}_{self.rig_name}", node_type="reverse",
                base_name="jawCorner", name="UpperLower", tag="CTRL",
                parent=None, custom_suffix=None
            ).create()
            cmds.connectAttr(attr, f"{reverse_node}.inputX")

            if side == "L":
                cmds.connectAttr(attr, f"{constraint}.{upper_weight}")
                cmds.connectAttr(f"{reverse_node}.outputX", f"{constraint}.{lower_weight}")
            else:
                cmds.connectAttr(f"{reverse_node}.outputX", f"{constraint}.{upper_weight}")
                cmds.connectAttr(attr, f"{constraint}.{lower_weight}")

            constraints[side] = constraint

        return constraints


       
    def _constrain_joint_to_local_trn(self, local_trn, joint):
            """
            El _TRN conduce al joint. No al reves: los canales del _TRN ya vienen
            conectados desde el decomposeMatrix de _build_off_network.
            """
            if not cmds.objExists(local_trn):
                cmds.warning(f"[Jaw] No existe el TRN '{local_trn}'.")
                return None
            if not cmds.objExists(joint):
                cmds.warning(f"[Jaw] No existe el joint '{joint}'.")
                return None

            existing = cmds.listRelatives(joint, type="parentConstraint") or []
            if existing:
                return existing[0]

            return cmds.parentConstraint(local_trn, joint, mo=True)[0]   
                                        
    def build(self):
        """Construye el rig del jaw."""

        base_name = "jaw"

        # 1. POSICIONES REALES DE LAS GUIAS (para joints bind/ik/fk)
        pos_jaw_root = cmds.xform(self.jaw_root, q=True, ws=True, t=True)
        pos_jaw_end = cmds.xform(self.jaw_end,  q=True, ws=True, t=True)
        
        # 2. CREAR JOINTS DE RIG
        cmds.select(clear=True)
        jaw_upper_jnt = cmds.joint(n=f"{self.prefix}_jawUpper_JNT", p=pos_jaw_root)
        cmds.matchTransform(jaw_upper_jnt, self.jaw_root, rot=True, pos=False)
        
        cmds.select(clear=True)
        jaw_lower_jnt = cmds.joint(n=f"{self.prefix}_jawLower_JNT", p=pos_jaw_root)
        cmds.matchTransform(jaw_lower_jnt, self.jaw_root, rot=True, pos=False)
        
        #Controles con el local set up
        #UPPER CONTROL 
        jaw_upper_ctrl = controlsLibrary.create_control_from_lib(
                lib_name=self.styles["mainFk"],
                final_name=f"{self.prefix}_jawUpper_CTRL"
            )
        

        #UPPER CONTROL GROUP
        jaw_upper_grp = self.group_maker.create_rig_hierarchy(
            jaw_upper_ctrl, self.jaw_root, match_rotation=True, world_space=True
        )
        
        #UPPER CONTROL OFFSET
        self._offset_control_shape(jaw_upper_ctrl, move=(0, 2, 10))
        
        #UPPER CONTROL LOCAL OFF/TRN

        upper_off_name = f"{self.prefix}_jawUpperLocal_OFF"
        upper_trn_name = f"{self.prefix}_jawUpperLocal_TRN"
        if not cmds.objExists(upper_off_name):
            upperJaw_local_off, upperJaw_local_trn = self._build_off_network(
                prefix=self.prefix,
                base_name="jawUpper", source_ctrl=jaw_upper_ctrl, source_ctrl_grp=jaw_upper_grp
            )
        else:
            upperJaw_local_off = upper_off_name
            upperJaw_local_trn = upper_trn_name

        
        #LOWER CONTROL
        jaw_lower_ctrl = controlsLibrary.create_control_from_lib(
                lib_name=self.styles["mainFk"],
                final_name=f"{self.prefix}_jawLower_CTRL"
            )

        #LOWER CONTROL GROUP
        jaw_lower_grp = self.group_maker.create_rig_hierarchy(
            jaw_lower_ctrl, self.jaw_root, match_rotation=True, world_space=True
            
        )
        cmds.addAttr(jaw_lower_ctrl, ln = "extraAttrSep",nn = "EXTRA_ATTR",at = "enum",en = "------" ,k=False)
        cmds.setAttr(f"{jaw_lower_ctrl}.extraAttrSep", cb=True)  
        cmds.setAttr(f"{jaw_lower_ctrl}.extraAttrSep", l=True)
        
        cmds.addAttr(jaw_lower_ctrl, ln = "collision",nn = "Collision",at = "float",k=True, min=0, max=1, dv=0)
        cmds.addAttr(jaw_lower_ctrl, ln = "LUpperLower",nn = "L Jaw Upper <---> Lower",at = "float",k=True, min=0, max=1, dv=0.5)
        cmds.addAttr(jaw_lower_ctrl, ln = "RUpperLower",nn = "R Jaw Upper <---> Lower",at = "float",k=True, min=0, max=1, dv=0.5)
       
       
        #LOWER CONTROL OFFSET
        self._offset_control_shape(jaw_lower_ctrl, move=(0, -2, 10))
        
        #LOWER CONTROL LOCAL OFF/TRN
        lower_off_name = f"{self.prefix}_jawLowerLocal_OFF"
        lower_trn_name = f"{self.prefix}_jawLowerLocal_TRN"
        if not cmds.objExists(lower_off_name):
            lowerJaw_local_off, lowerJaw_local_trn = self._build_off_network(
                prefix=self.prefix,
                base_name="jawLower", source_ctrl=jaw_lower_ctrl, source_ctrl_grp=jaw_lower_grp
            )
        else:
            lowerJaw_local_off = lower_off_name
            lowerJaw_local_trn = lower_trn_name

        # 3. EXPONER LOS NODOS CLAVE
        # Para que el modulo de la boca (u otros) puedan engancharse sin
        # reconstruir los nombres con f-strings.
        # self.jaw_upper_jnt = jaw_upper_jnt
        # self.jaw_lower_jnt = jaw_lower_jnt
        # self.jaw_upper_ctrl = jaw_upper_ctrl
        # self.jaw_lower_ctrl = jaw_lower_ctrl
        # self.jaw_upper_local_trn = upperJaw_local_trn
        # self.jaw_lower_local_trn = lowerJaw_local_trn

        #CONEXIONES PARA Q EL LOWER EMPUJE AL UPPER
        #ROTACIONES
        
        floatMath_node = NodeCreator(
            side=self.prefix, node_type="floatMath", base_name=base_name,
            name="Local", tag="CTRL", parent=None, custom_suffix=None
        ).create()
        cmds.setAttr(f"{floatMath_node}.operation", 1) #Subtract
        
        # cmds.connectAttr(f"{jaw_lower_ctrl}.rotateX", f"{floatMath_node}.floatA")
        # cmds.connectAttr(f"{jaw_upper_ctrl}.rotateX", f"{floatMath_node}.floatB")
        
        clamp_node = NodeCreator(
            side=self.prefix, node_type="clamp", base_name=base_name,
            name="LocalClamp", tag="CTRL", parent=None, custom_suffix=None
        ).create()
        
        cmds.connectAttr(f"{floatMath_node}.outFloat", f"{clamp_node}.inputR")
        cmds.setAttr(f"{clamp_node}.minR", -360)
        
        floatMath02_node = NodeCreator(
            side=self.prefix, node_type="floatMath", base_name=base_name,
            name="Local02", tag="CTRL", parent=None, custom_suffix=None
        ).create()
        cmds.setAttr(f"{floatMath02_node}.operation", 1) #Subtract
        
        cmds.connectAttr(f"{clamp_node}.outputR", f"{floatMath02_node}.floatA")
        cmds.connectAttr(f"{jaw_lower_ctrl}.collision", f"{floatMath02_node}.floatB")

        # El resultado entra en el SDK del upper.
        # create_rig_hierarchy monta GRP > SPC > OFF > SDK > ANIM pero solo
        # devuelve el GRP, asi que bajamos por la jerarquia a buscar el SDK
        # en vez de reconstruir su nombre con un f-string.
        jaw_upper_sdk = self._get_rig_group(jaw_upper_grp, "SDK")
        if jaw_upper_sdk:
            cmds.connectAttr(f"{floatMath02_node}.outFloat", f"{jaw_upper_sdk}.rotateX")

        #TRANSLACIONES

        # Recuperamos el multMatrix del lower buscandolo por conexion.
        # Funciona igual tanto si acabamos de crear la red como si ya existia
        # de un build anterior (rama idempotente de arriba).
        lower_mult_node = self._get_local_mult_matrix(jaw_lower_ctrl)

        lower_decompose_node = None
        if lower_mult_node:
            lower_decompose_node = NodeCreator(
                side=self.prefix, node_type="decomposeMatrix", base_name="jawLower",
                name="LocalTranslate", tag="CTRL", parent=None, custom_suffix=None
            ).create()

            # matrixSum es un output: puede alimentar varios destinos a la vez,
            # asi que el decompose que ya cuelga de el sigue intacto.
            cmds.connectAttr(
                f"{lower_mult_node}.matrixSum",
                f"{lower_decompose_node}.inputMatrix",
                force=True
            )

            cmds.connectAttr(f"{lower_decompose_node}.outputRotateX", f"{floatMath_node}.floatA")
            
        multMatrix_node = NodeCreator(
            side=self.prefix, node_type="multMatrix", base_name=base_name,
            name="Local", tag="CTRL", parent=None, custom_suffix=None
        ).create()            
        
        cmds.connectAttr(f"{jaw_upper_ctrl}.matrix", f"{multMatrix_node}.matrixIn[0]")
        
        jaw_upper_anim = self._get_rig_group(jaw_upper_grp, "ANIM")
        if jaw_upper_anim:
            cmds.connectAttr(f"{jaw_upper_anim}.matrix", f"{multMatrix_node}.matrixIn[1]")
            
        
        upper_decompose_node = NodeCreator(
                side=self.prefix, node_type="decomposeMatrix", base_name="jawUpper",
                name="LocalTranslate", tag="CTRL", parent=None, custom_suffix=None
        ).create()     
        
        cmds.connectAttr(f"{multMatrix_node}.matrixSum", f"{upper_decompose_node}.inputMatrix")
        cmds.connectAttr(f"{upper_decompose_node}.outputRotateX", f"{floatMath_node}.floatB")
        
        
        #COMISURAS DE LA BOCA
        corner_joints = self._create_corner_joints()
        print(f"[Jaw] Corner joints: {corner_joints}")
        self._constrain_corner_joints(
            corner_joints, jaw_upper_jnt, jaw_lower_jnt, jaw_lower_ctrl
        )
        
        self._constrain_joint_to_local_trn(upperJaw_local_trn, jaw_upper_jnt)
        self._constrain_joint_to_local_trn(lowerJaw_local_trn, jaw_lower_jnt)
        
        return jaw_upper_grp, jaw_lower_grp