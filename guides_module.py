import maya.cmds as cmds
from functools import partial 
import os
import math
import json
import spine_module
import limbs_module
import fingers_module
import neck_module
import chest_module
import hip_module
import leg_module
import foot_module
import groups_module
import rigRoot_module
import mirror_module
import arm_right_module
import right_leg_module
import skinning_module
        
########################################################################
#SPINE
########################################################################
        
class SpineGuides(object):
    """
    Crea les guies de la spine.

    """
    def __init__(self, spine_root, spine_chest, spine_position):
        self.spine_root = spine_root
        self.spine_end = spine_chest
        self.spine_position = spine_position
        self.guides_group = None 

    def spine_guides(self):
        #Crea el joint root de les guies de la spine
        root_joint = cmds.joint(p=(0, 0, 0), name=self.spine_root)
        if not root_joint:
            print(f"Error creando la joint: {self.spine_root}")
            return
        
        #Crea el joint final de les guies de la spine
        end_joint = cmds.joint(p=self.spine_position, name=self.spine_end)
        if not end_joint:
            print(f"Error creando la joint: {self.spine_end}")
            return

        #Crea el grup de les guies de la spine
        cmds.select(root_joint, end_joint, r=True)
        self.guides_group = cmds.group(root_joint, n="spine_guides_GRP")
        if self.guides_group is None:
            print("Error al crear el grupo de guías.")
        
########################################################################
#NECK
########################################################################
        
class NeckGuides(object):
    """
    Crea les guies del coll.

    """
    def __init__(self, neck_root, neck_end, root_pos, end_pos):
        self.neck_root = neck_root
        self.neck_end = neck_end
        self.root_pos = root_pos
        self.end_pos = end_pos
        self.guides_group = None 
    
    def neck_guides(self):
        cmds.select(clear=True)
        #Crea el joint d inici de la guia del neck
        neck_root = cmds.joint(p=self.root_pos, n=self.neck_root)
        if not neck_root:
            print(f"Error creando la joint: {self.neck_root}")
            return
        
        #Crea el joint del final de la guia del neck
        neck_end = cmds.joint(p=self.end_pos, n=self.neck_end)
        if not neck_end:
            print(f"Error creando la joint: {self.neck_end}")
            return
        
        cmds.joint(neck_root, e=True, oj="yzx", sao="zup", ch=True, zso=True)
        cmds.setAttr(f"{neck_end}.jointOrientX", 0)
        cmds.setAttr(f"{neck_end}.jointOrientY", 0)
        cmds.setAttr(f"{neck_end}.jointOrientZ", 0)
        
        #Crea el grup de les guies del coll
        self.guides_group = cmds.group(neck_root, n="neck_guides_GRP")
        if self.guides_group is None:
            print("Error al crear el grupo de guías del cuello.")
        
        cmds.select(clear = True)
        
########################################################################
#LIMB
########################################################################
        
class LimbGuides(object):
    """
    Classe per crear les guies dels bracos i cames.

    """
    def __init__(self, limb_root, limb_mid, limb_end,
                 limb_root_pos, limb_mid_pos, limb_end_pos):

        self.limb_root = limb_root
        self.limb_mid = limb_mid
        self.limb_end = limb_end
        
        self.limb_root_pos = limb_root_pos
        self.limb_mid_pos = limb_mid_pos
        self.limb_end_pos = limb_end_pos
        
        self.joint_orient = "xyz"   
        self.up_axis      = "yup"  
        
        self.guides_group = None
    
    def create_chain(self):
        """
        Crea la cadena de joints i la orienta automaticament

        """
        cmds.select(clear=True)
        
        hierarchy_root = None

        #Crea tres joints, d inici, mig i final 
        root = cmds.joint(n=self.limb_root, p=self.limb_root_pos)
        mid = cmds.joint(n=self.limb_mid, p=self.limb_mid_pos)
        end = cmds.joint(n=self.limb_end, p=self.limb_end_pos)

        if not hierarchy_root:
            hierarchy_root = root

        # Força a que els joints apuntin sempre en l eix X
        cmds.joint(root, edit=True, oj=self.joint_orient, sao=self.up_axis, ch=True, zso=True)

        #Crea el grup de limb        
        self.guides_group = cmds.group(hierarchy_root, n="limb_guides_GRP")

        # L ultim joint s orienta sempre tot a 0
        cmds.setAttr(f"{end}.jointOrient", 0, 0, 0)
        
        return self.guides_group

########################################################################
#ARM
########################################################################

class ArmGuides(LimbGuides):
    """
    Hereda de la classe limbs i crea la clavicula, completant el brac
    """
    def __init__(self, limb_root, limb_mid, limb_end, clavicule_root,
                 limb_root_pos, limb_mid_pos, limb_end_pos, clavicule_root_pos):

        super(ArmGuides, self).__init__(
            limb_root, limb_mid, limb_end,
            limb_root_pos, limb_mid_pos, limb_end_pos
        )

        self.clavicule = clavicule_root
        self.clavicule_pos = clavicule_root_pos
        
        self.shoulder_joint = self.limb_root
        self.elbow_joint    = self.limb_mid
        self.wrist_joint    = self.limb_end

    def create_chain(self):
        """
        Crea la clavicula 

        """
        super(ArmGuides, self).create_chain()

        root = self.limb_root
        end  = self.limb_end

        if self.clavicule:
            cmds.select(clear=True)
            #Crea el joint de la clavicula
            hierarchy_root = cmds.joint(n=self.clavicule, p=self.clavicule_pos)

            #Emparenta la clavicula amb el primer joint del brac
            cmds.parent(root, hierarchy_root)

            cmds.joint(hierarchy_root, edit=True, oj=self.joint_orient, sao=self.up_axis, ch=True, zso=True)
            #cmds.setAttr(f"{end}.jointOrient", 0, 0, 0)  

            cmds.parent(root, world=True)
            cmds.delete(self.guides_group)

            #Crea el grup de guies del brac 
            cmds.parent(root, hierarchy_root)
            self.guides_group = cmds.group(hierarchy_root, n="arm_guides_GRP")

        return self.guides_group

############################################################################
#LEG
############################################################################

class LegGuides(LimbGuides):
    """
    Hereda de la classe limbs i fa la cama
    """
    def __init__(self, limb_root, limb_mid, limb_end,
                 limb_root_pos, limb_mid_pos, limb_end_pos):
        
        super(LegGuides, self).__init__(limb_root, limb_mid, limb_end, limb_root_pos, limb_mid_pos, limb_end_pos)
        
        #Configura el grup, l’orientacio i el joint final de la cama
        self.group_name = "leg_guides_GRP"
        self.joint_orient = "xzy"
        self.up_axis = "zdown"
        self.ankle_joint = self.limb_end

                                             
########################################################################
#FINGER
########################################################################

class FingerGuides(object):
    """
    Crea les guies dels dits. 

    """

    def __init__(self, parent_joint, name, offsets):
        self.parent_joint = parent_joint
        self.name = name
        self.offsets = offsets
        self.joints = []

    def finger_guides(self):
        #Agafa la posicio del joint del canell 
        wrist_pos = cmds.xform(self.parent_joint, q=True, ws=True, t=True)
    
        cmds.select(clear=True)
        
        #Crea els joints dels dits a partir de les dades definides
        for i, offset in enumerate(self.offsets):
    
            pos = (
                wrist_pos[0] + offset[0],
                wrist_pos[1] + offset[1],
                wrist_pos[2] + offset[2]
            )
    
            jnt_name = f"{self.name}_{i+1:02d}"
            jnt = cmds.joint(n=jnt_name, p=pos)
    
            self.joints.append(jnt)
    
        #Emparentar el root del dit amb el canell
        cmds.parent(self.joints[0], self.parent_joint)

############################################################
# HAND
############################################################

class HandGuides(object):
    """
    Crea les guies de la ma.

    """

    def __init__(self, arm_instance):
        self.arm = arm_instance
        self.fingers = []
        self.group = None

    def hand_guides(self):
        
        #Agafa el joint del canel
        wrist = self.arm.wrist_joint

        #Dades dels dits
        finger_data = {
            "L_index":  [(1,0,1),(2,0,1),(3,0,1),(4,0,1),(5,0,1)],
            "L_middle": [(1,0,0),(2,0,0),(3,0,0),(4,0,0),(5,0,0)],
            "L_ring":   [(1,0,-1),(2,0,-1),(3,0,-1),(4,0,-1),(5,0,-1)],
            "L_pinky":  [(1,0,-2),(2,0,-2),(3,0,-2),(4,0,-2),(5,0,-2)],
            "L_thumb":  [(1,0,1),(1,-1,2),(2,-1,2),(3,-1,2)]
        }
        


        #Crea les guies dels dits a partir de les dades definides
        for name, offsets in finger_data.items():

            finger = FingerGuides(wrist, name, offsets)
            finger.finger_guides()
            self.fingers.append(finger)
            
        # =========================================================================
        # RE-ORIENTACIÓN ANATÓMICA DEL PULGAR (Para comodidad del animador)
        # =========================================================================
        
        # --- LADO IZQUIERDO (L) ---
        # Asegúrate de que estos nombres coinciden con los que genera tu rig de guías
        thumb_l_root = "L_thumb_01"   # O "L_thumb_1", revisa tu Outliner
        thumb_l_med  = "L_thumb_02"   # O "L_thumb_2"
        
        if cmds.objExists(thumb_l_root) and cmds.objExists(thumb_l_med):
            # 1. Almacenamos el abuelo (wrist) para no perder la jerarquía superior
            parent_wrist = cmds.listRelatives(thumb_l_root, parent=True)[0]
            
            # 2. Desemparentamos el hijo temporalmente para que no se mueva de su posición en el espacio
            cmds.parent(thumb_l_med, world=True)
            
            # 3. Forzamos la orientación base del eje X hacia donde estaba el hijo
            cmds.joint(thumb_l_root, edit=True, oj="xyz", sao="zup", zso=True)
            
            # 4. Metemos el TWIST en el Joint Orient X para encarar el eje de flexión hacia la palma
            # Ajusta este valor (ej. 30, 45, 60) hasta que veas que el eje Z o Y apunta hacia donde se cierra el puño
            cmds.setAttr(f"{thumb_l_root}.jointOrientY", -90)
            
            # 5. Volvemos a emparentar la cadena del pulgar
            cmds.parent(thumb_l_med, thumb_l_root)
            
            # 6. Limpiamos al hijo para que su orientación mire recta hacia la punta del pulgar
            cmds.joint(thumb_l_med, edit=True, oj="xyz", sao="yup", ch=True, zso=True)
        #Agrupa les guies de la ma
        #self.group = cmds.group(wrist, n="hand_guides_GRP")
        
        
############################################################
#FOOT
############################################################

class FootGuides(object):
    """
    Crea les guies del peu. 

    """

    def __init__(self, leg_instance, ball_name, tip_name,heel_name,
                 ball_offset, tip_offset, heel_offset):
        self.leg = leg_instance
        self.ball_name = ball_name
        self.tip_name = tip_name
        self.heel_name = heel_name
        self.ball_offset = ball_offset
        self.tip_offset = tip_offset
        self.heel_offset = heel_offset
        self.joints = []

    def foot_guides(self):

        ankle = self.leg.ankle_joint
        ankle_pos = cmds.xform(ankle, q=True, ws=True, t=True)

        cmds.select(clear=True)
        
        #heel position
        heel_pos =(
            ankle_pos[0] + self.heel_offset[0],
            ankle_pos[1] + self.heel_offset[1],
            ankle_pos[2] + self.heel_offset[2]
        ) 
        
        heel= cmds.joint(n=self.heel_name, p=heel_pos)
        
        cmds.select(clear =True)
        
        #Ball position
        ball_pos = (
            ankle_pos[0] + self.ball_offset[0],
            ankle_pos[1] + self.ball_offset[1],
            ankle_pos[2] + self.ball_offset[2]
        )

        ball = cmds.joint(n=self.ball_name, p=ball_pos)

        #Tip position
        tip_pos = (
            ankle_pos[0] + self.tip_offset[0],
            ankle_pos[1] + self.tip_offset[1],
            ankle_pos[2] + self.tip_offset[2]
        )

        tip = cmds.joint(n=self.tip_name, p=tip_pos)

        self.joints = [ball, tip, heel]

        #Parentar ball al ankle
        cmds.parent(ball, ankle)
        cmds.parent(heel, ankle) 


############################################################
# TOES (dits del peu)
############################################################

class ToesGuides(object):
    """
    Crea les guies dels dits del peu, penjades de la guia del ball.

    Cada dit es una cadena de 4 joints (proximal, mitja, distal i punta), que es
    exactament el que necessita el ToesModule per fer IK amb la falange distal
    lliure, igual que a la ma.

    Els offsets son relatius a la posicio del ball. La Y baixa una mica joint a
    joint per donar als dits una corba natural cap avall: aixo li serveix al
    modul per detectar sol el pla de flexio, sense haver de forcar cap eix.

    Si vols mes o menys joints per dit, nomes cal afegir o treure tuples: el
    modul llegeix la cadena de guies sencera, sigui de la llargada que sigui.
    """

    # Offsets (X, Y, Z) respecte del ball. X negatiu = costat intern (dit gros).
    DEFAULT_TOES = {
        "bigToe":   [(-1.00, 0.00, 0.20), (-1.02, -0.05, 1.30),
                     (-1.04, -0.18, 2.00), (-1.05, -0.35, 2.45)],
        "indexToe": [(-0.40, 0.00, 0.25), (-0.42, -0.05, 1.30),
                     (-0.44, -0.18, 1.95), (-0.45, -0.35, 2.35)],
        "midToe":   [(0.20, 0.00, 0.22), (0.22, -0.05, 1.20),
                     (0.24, -0.18, 1.80), (0.25, -0.35, 2.15)],
        "ringToe":  [(0.75, 0.00, 0.15), (0.78, -0.05, 1.05),
                     (0.80, -0.18, 1.60), (0.82, -0.35, 1.90)],
        "pinkyToe": [(1.25, 0.00, 0.05), (1.30, -0.05, 0.85),
                     (1.32, -0.18, 1.30), (1.34, -0.35, 1.55)],
    }

    def __init__(self, foot_instance, side="L", toe_data=None):
        self.foot = foot_instance
        self.side = side
        self.toe_data = toe_data if toe_data else self.DEFAULT_TOES
        self.toes = []

    def toes_guides(self):
        # El ball es el "metatars": tots els dits pengen d'ell
        ball = self.foot.ball_name

        if not cmds.objExists(ball):
            cmds.warning("No existe la guia del ball ({0}): no puedo crear los "
                         "dedos del pie.".format(ball))
            return

        # Reaprofita FingerGuides, que ja crea una cadena a partir d'offsets
        for name, offsets in self.toe_data.items():
            toe_name = "{0}_{1}".format(self.side, name)

            toe = FingerGuides(ball, toe_name, offsets)
            toe.finger_guides()
            self.toes.append(toe)

        cmds.select(clear=True)
        return self.toes

############################################################
#BOCA🫦
############################################################
class BocaGuides(object):
    """
    Genera los jointsa de la boca y la surface
    """
    def __init__(self, lips_NRB, lip_mid, lip_end,
                 lip_in01="L_lip_in01", lip_in02="L_lip_in02",
                 make_surface=True):
        self.boca_surface = lips_NRB
        self.lip_mid = lip_mid
        self.lip_end = lip_end

        # Dos guias intermedias entre el mid y la comisura. La de dentro
        # conduce el depresor/levator y la de fuera los pinch.
        self.lip_in01 = lip_in01
        self.lip_in02 = lip_in02

        # La NURBS solo la necesita el sistema viejo (closestPointOnSurface,
        # uvPin). En el sistema simple no se usa; se deja a True por si hay que
        # volver atras, pero se puede apagar sin romper nada.
        self.make_surface = make_surface

        # True: lip_in01 / lip_in02 cuelgan de lip_end, para que el mirror las
        # arrastre sin tocar module_specs. Ver la nota en create_boca().
        self.parent_in_between_to_end = True
        
    # Posiciones base de las guias. Si mueves el mid o la comisura, las dos
    # intermedias se recolocan solas.
    MID_POSITION = (0, 24, 10)
    END_POSITION = (2.5, 24, 9)
    END_ROTATE_Y = 45

    def _create_surface(self):
        """
        La NURBS de la boca. Solo la usa el sistema viejo (closestPointOnSurface
        y uvPin); el simple no la toca. Se sigue creando por defecto para poder
        volver atras, y se apaga con make_surface=False.
        """
        surface = cmds.nurbsPlane(n=self.boca_surface, ax=(0, 1, 0),
                                  w=10, lr=1, d=1, u=4, v=4)[0]
        cmds.setAttr(f"{surface}.translateY", 24)
        cmds.setAttr(f"{surface}.translateZ", 10)
        cmds.setAttr(f"{surface}.rotateX", 90)

        #Dar una posicion base a la forma de la nurbs
        cmds.select(surface + ".cv[4][0:4]", r=True)
        cmds.select(surface + ".cv[0][0:4]", add=True)
        cmds.move(0, 0, -4, r=True)

        cmds.select(surface + ".cv[1][0:4]", r=True)
        cmds.select(surface + ".cv[3][0:4]", add=True)
        cmds.move(0, 0, -1, r=True)

        return surface

    def create_boca(self):
        surface = None

        #Crea la surface de la boca
        if self.make_surface:
            surface = self._create_surface()

        #Crea els joints de la boca
        cmds.select(clear=True)
        lip_mid_joint = cmds.joint(n=self.lip_mid, p=self.MID_POSITION)
        cmds.select(clear=True)
        lip_end_joint = cmds.joint(n=self.lip_end, p=self.END_POSITION)
        cmds.setAttr(f"{lip_end_joint}.rotateY", self.END_ROTATE_Y)

        # Las dos intermedias: repartidas a 1/3 y 2/3 entre el mid y la
        # comisura, con la rotateY interpolada igual, para que la cadena salga
        # abriendose de forma progresiva y no de golpe en la comisura.
        in_between = []
        for name, fraction in ((self.lip_in01, 1.0 / 3.0),
                               (self.lip_in02, 2.0 / 3.0)):
            position = [start + (end - start) * fraction
                        for start, end in zip(self.MID_POSITION, self.END_POSITION)]

            cmds.select(clear=True)
            joint = cmds.joint(n=name, p=position)
            cmds.setAttr(f"{joint}.rotateY", self.END_ROTATE_Y * fraction)
            in_between.append(joint)

        # Las intermedias cuelgan de la comisura a proposito.
        #
        # mirror_module no espeja joints sueltos: espeja las RAICES que le
        # dice module_specs, y mirrorJoint se lleva la jerarquia entera de cada
        # una. Colgandolas de L_lip_end quedan cubiertas por la raiz que la
        # boca ya tenia declarada, sin tocar module_specs.
        #
        # Efecto secundario que hay que conocer: al mover la comisura, las dos
        # intermedias la acompañan. Para colocar guias suele ser comodo, pero
        # si prefieres moverlas sueltas, desengancha aqui y añade
        # "L_lip_in01" y "L_lip_in02" a los mirror_roots de la boca.
        if self.parent_in_between_to_end:
            for joint in in_between:
                cmds.parent(joint, lip_end_joint)

        members = [lip_mid_joint, lip_end_joint]
        if not self.parent_in_between_to_end:
            members += in_between
        if surface:
            members.insert(0, surface)

        self.guides_group = cmds.group(members, n="boca_guides_GRP")

        cmds.select(clear=True)

        return self.guides_group
        
class JawGuides(object):
    """
    Crea les guies de la jaw.
    """
    def __init__(self, jaw_root, jaw_end, root_pos, end_pos):
        self.jaw_root = jaw_root
        self.jaw_end = jaw_end
        self.root_pos = root_pos
        self.end_pos = end_pos
        self.guides_group = None

    def jaw_guides(self):
        cmds.select(clear=True)

        # Crea el joint root de les guies de la jaw
        rootJaw_joint = cmds.joint(p=self.root_pos, name=self.jaw_root)
        if not rootJaw_joint:
            print(f"Error creando la joint: {self.jaw_root}")
            return

        # Crea el joint final de les guies de la jaw
        endJaw_joint = cmds.joint(p=self.end_pos, name=self.jaw_end)
        if not endJaw_joint:
            print(f"Error creando la joint: {self.jaw_end}")
            return

        # Crea el grup de les guies de la jaw
        self.guides_group = cmds.group(rootJaw_joint, n="jaw_guides_GRP")
        if self.guides_group is None:
            print("Error al crear el grupo de guías de la jaw.")

        cmds.select(clear=True)  

class EyeGuides(object):
    """
    Crea les guies de l'ull: el centre, el seu end i el direct.

    Les guies de parpella ja no existeixen: la seva posicio surt de la corba de
    loop que es construeix des de l'edge de la malla (veure EyesModule).
    """
    def __init__(self, eye_mid, eye_mid_end, eye_direct,
                 eye_position=(2, 26, 9),
                 eye_mid_end_position=(2, 26, 10),
                 eye_direct_position=(2, 26, 20)):

        self.eye_mid = eye_mid
        self.eye_mid_end = eye_mid_end
        self.eye_direct = eye_direct

        # Las posiciones siguen siendo parametros: eye_guides() las lee como
        # self.eye_position / self.eye_mid_end_position / self.eye_direct_position.
        # Al quitarlas del __init__ la llamada de create_guides() seguia pasando
        # seis argumentos contra una firma de tres.
        self.eye_position = eye_position
        self.eye_mid_end_position = eye_mid_end_position
        self.eye_direct_position = eye_direct_position

        self.guides_group = None

    def eye_guides(self):
        # Parelles nom / posicio de totes les joints de l'ull
        joints_info = [
            (self.eye_mid, self.eye_position),
            (self.eye_mid_end, self.eye_mid_end_position),
            (self.eye_direct, self.eye_direct_position),

        ]

        created_joints = []

        for joint_name, joint_position in joints_info:
            # Es deselecciona abans de cada joint perque surtin independents i no encadenades
            cmds.select(clear=True)
            new_joint = cmds.joint(p=joint_position, name=joint_name)
            if not new_joint:
                print(f"Error creando la joint: {joint_name}")
                return
            created_joints.append(new_joint)

        # Crea el grup de les guies de l'ull
        self.guides_group = cmds.group(created_joints, n="L_eye_guides_GRP")
        if self.guides_group is None:
            print("Error al crear el grupo de guías del ojo.")

        cmds.select(clear=True)

#########################################################################
#EYEBROWS
#########################################################################

class EyebrowsGuides(object):
    """
    Crea automàticament 10 guies de les celles a partir de les posicions de referència.
    """
    def __init__(self, eyebrow_root, eyebrow_end, root_pos=(0, 24, 10), end_pos=(2.5, 24, 9)):
        self.eyebrow_root = eyebrow_root
        self.eyebrow_end = eyebrow_end
        self.root_pos = root_pos
        self.end_pos = end_pos
        self.guides_group = None

    def eyebrows_guides(self):
        cmds.select(clear=True)
        
        created_joints = []
        num_joints = 10  

        for i in range(num_joints):
            t = i / float(num_joints - 1)
            
            current_pos = [
                round(self.root_pos[j] + (self.end_pos[j] - self.root_pos[j]) * t, 4)
                for j in range(3)
            ]

            joint_name = f"{self.eyebrow_root}_{i+1:02d}"
            
            current_joint = cmds.joint(p=current_pos, name=joint_name)
            if not current_joint:
                print(f"Error creant el joint: {joint_name}")
                return
                
            created_joints.append(current_joint)

        self.guides_group = cmds.group(created_joints, n="eyebrows_guides_GRP")
        if self.guides_group is None:
            print("Error al crear el grup de guies de les celles.")

        cmds.select(clear=True)
        return self.guides_group

class EyebrowSkullGuides(object):
    """
    Crea la NURBS con forma de craneo por la que deslizan las cejas.

    Se hace como dice el documento: una curva de perfil en vista lateral y un
    revolve alrededor del eje Y. Asi la superficie envuelve la frente y la
    costura queda atras, fuera de la zona de la ceja, que es donde no molesta.

    La forma es solo un punto de partida. Ajustala a mano sobre el modelo antes
    de construir el rig: lo unico que importa es que cubra toda la zona por la
    que se mueven las cejas, con margen por arriba si se va a usar la fila de la
    frente.
    """

    def __init__(self, surface_name="eyebrow_skull_NRB",
                 profile=None, center=(0.0, 34.0, 0.0), sections=12):
        self.surface_name = surface_name
        self.center = center
        self.sections = sections

        # Perfil en el plano YZ, de arriba abajo. (Z hacia delante, Y arriba),
        # relativo a center. Sale una cupula achatada tipo frente.
        self.profile = profile or [
            (0.0, 4.0, 0.0),
            (0.0, 3.6, 2.2),
            (0.0, 2.4, 3.6),
            (0.0, 0.8, 4.2),
            (0.0, -1.0, 4.3),
            (0.0, -2.6, 4.0),
        ]

        self.guides_group = None

        

    def create_skull(self):
        if cmds.objExists(self.surface_name):
            cmds.warning(f"[Guides] '{self.surface_name}' ya existe, no se "
                         "vuelve a crear.")
            return self.surface_name

        points = [(self.center[0] + p[0],
                   self.center[1] + p[1],
                   self.center[2] + p[2]) for p in self.profile]

        profile_curve = cmds.curve(d=3, p=points, n=f"{self.surface_name}_profile_CRV")

        # Revolve alrededor de Y, pasando por el centro. startSweep 180 para que
        # la costura caiga en la nuca y no en la frente.
        surface = cmds.revolve(
            profile_curve,
            ch=False,
            po=0,
            ax=(0, 1, 0),
            pivot=self.center,
            sections=self.sections,
            degree=3,
            startSweep=180,
            endSweep=540,
            n=self.surface_name,
        )[0]

        cmds.delete(profile_curve)

        # Rebuild para tener una parametrizacion limpia y previsible, igual que
        # se hace con la superficie de la boca.
        cmds.rebuildSurface(surface, ch=0, rpo=1, kr=0, kcp=0, kc=0,
                            su=8, du=3, sv=6, dv=3)

        self.guides_group = cmds.group(surface, n="eyebrowSkull_guides_GRP")
        cmds.select(clear=True)
        return self.guides_group

class NoseGuides(object):
    """
    Crea les guies del nas.

    Noms SENSE sufix _JNT: skinning_module duplica qualsevol joint de l escena
    que acabi en JNT, i les guies acabarien com a joints de skin.

    Les aletes nomes existeixen a +X (prefix L_). El costat R el treu
    nose_module mirallant la X, igual que la boca: no cal MIRROR.
    """

    def __init__(self, nose_root, nose_tip, root_pos=(0, 24, 10), tip_pos=(0, 24, 12),
                 nostril_base="L_nose_nostrilBase", nostril="L_nose_nostril",
                 nostril_base_pos=(0.3, 24, 11), nostril_pos=(0.6, 24, 11)):
        self.nose_root = nose_root
        self.nose_tip = nose_tip
        self.root_pos = root_pos
        self.tip_pos = tip_pos
        self.nostril_base = nostril_base
        self.nostril = nostril
        self.nostril_base_pos = nostril_base_pos
        self.nostril_pos = nostril_pos
        self.guides_group = None

    def _guide(self, name, position):
        #select(clear) abans de cada joint: si no, cmds.joint penja el nou del
        #que estigui seleccionat i les quatre guies acaben encadenades.
        cmds.select(clear=True)
        return cmds.joint(p=position, name=name)

    def nose_guides(self):
        guides = [
            self._guide(self.nose_root, self.root_pos),
            self._guide(self.nose_tip, self.tip_pos),
            self._guide(self.nostril_base, self.nostril_base_pos),
            self._guide(self.nostril, self.nostril_pos),
        ]

        # Crea el grup de les guies del nas
        self.guides_group = cmds.group(guides, n="nose_guides_GRP")

        cmds.select(clear=True)

##### INSTANCIAS #####

class CharacterGuides(object):
    """
    Crea les guies del personatge i les agrupa sota "guides_GRP".

    Ja no les crea totes sempre: create_guides() rep la recepta de la finestra
    i nomes crea les guies dels moduls que hi ha a l arbre. I es pot cridar mes
    d un cop: si guides_GRP ja existeix, les guies que ja hi son no es tornen a
    crear, i les noves s afegeixen al grup existent.
    """

    GUIDES_ROOT = "guides_GRP"
    GUIDES_OFFSET_Y = 32.5

    #: Guia que demostra que un bloc de guies ja existeix a l escena. Si hi es,
    #: aquell bloc no es torna a crear: aixi es pot afegir un modul a l arbre,
    #: tornar a donar a GUIDES, i nomes apareixen les guies noves.
    PRESENCE = {
        "spine":   "root",
        "neck":    "neck_root",
        "arm":     "L_clavicule",
        "finger":  "L_index_01",
        "leg":     "L_hip",
        "toes":    "L_bigToe_01",
        #Ja no "boca_surface": la boca nova no la fa servir. C_lip_mid es la
        #guia que sempre necessita.
        "mouth":   "C_lip_mid",
        "jaw":     "jaw_root",
        "eye":     "L_eye_mid",
        "eyebrow": "L_eyebrow_root_01",
        "skull":   "eyebrow_skull_NRB",
        "nose":    "nose_root",
    }

    def __init__(self):
        # Añadimos una variable para guardar la instancia del spine
        self.spine_rig = None
        self.all_guides_grp = None

        #Resultat de l ultima crida, per poder-lo consultar
        self.created = []
        self.skipped = []

    # ------------------------------------------------------------------
    # QUE CAL CREAR
    # ------------------------------------------------------------------
    @staticmethod
    def _blocks_from_recipe(recipe):
        """
        Tradueix la recepta a blocs de guies.

        Un modul no sempre es un bloc: la cama porta el peu (el reverse foot va
        sempre), els dits del peu (modul "toe") pengen del ball de la cama, el
        spine va sempre (el chest i el hip en depenen) i les celles
        porten la NURBS del crani per on llisquen.

        recipe=None vol dir "totes", que es com funcionava abans.
        """
        if recipe is None:
            return ["spine", "neck", "arm", "finger", "leg", "toes",
                    "mouth", "jaw", "eye", "eyebrow", "skull"]

        types = {entry["type"] for entry in recipe}

        blocks = []

        #El spine va sempre: el chest i el hip del build son passos fixos que
        #en llegeixen les guies. El coll ja no: ara es un modul opcional.
        blocks.append("spine")
        if "neck" in types:
            blocks.append("neck")

        #Els dits pengen del canell: sense les guies del brac no tenen d on
        #penjar. Si l usuari ha posat dits sense brac, es crea el brac igual.
        if "arm" in types or "finger" in types:
            blocks.append("arm")
        if "finger" in types:
            blocks.append("finger")

        #Igual que els dits de la ma amb el brac: els dits del peu pengen del
        #ball, que surt de les guies de la cama i el peu.
        if "leg" in types or "toe" in types:
            blocks.append("leg")
        if "toe" in types:
            blocks.append("toes")

        if "mouth" in types:
            blocks.append("mouth")
        if "jaw" in types:
            blocks.append("jaw")
        if "eye" in types:
            blocks.append("eye")
        if "eyebrow" in types:
            blocks += ["eyebrow", "skull"]
        if "nose" in types:
            blocks.append("nose")

        return blocks

    # ------------------------------------------------------------------
    # CREACIO
    # ------------------------------------------------------------------
    def create_guides(self, recipe=None):
        """
        Crea les guies dels moduls de la recepta i les agrupa sota guides_GRP.

        Args:
            recipe (list): la recepta de la finestra. None = totes les guies.

        Returns:
            list: els blocs de guies que s han creat en aquesta crida
        """
        self.created = []
        self.skipped = []

        blocks = self._blocks_from_recipe(recipe)

        if recipe is not None:
            types = {entry["type"] for entry in recipe}
            if "finger" in types and "arm" not in types:
                cmds.warning("[Guides] Hi ha dits pero no brac: es creen igualment "
                             "les guies del brac, que es d on pengen els dits.")
            if "toe" in types and "leg" not in types:
                cmds.warning("[Guides] Hi ha dits del peu pero no cama: es creen "
                             "igualment les guies de la cama, que es d on pengen.")

        new_groups = []

        #Instancies que necessiten els blocs que depenen d un altre. Si el pare
        #ja existia a l escena, es fa servir un substitut amb nomes el nom del
        #joint, que es l unic que en llegeixen HandGuides i ToesGuides.
        arm_instance = None
        foot_instance = None

        for block in blocks:
            if cmds.objExists(self.PRESENCE[block]):
                self.skipped.append(block)
                continue

            if block == "spine":
                #Crea les guies de la spine
                spine_instance = SpineGuides("root", "chest", (0, 10, 0))
                spine_instance.spine_guides()
                new_groups.append(spine_instance.guides_group)

            elif block == "neck":
                #Crea les guies del coll
                neck_instance = NeckGuides("neck_root", "neck_end", (0, 20, 0), (0, 23, 0.5))
                neck_instance.neck_guides()
                new_groups.append(neck_instance.guides_group)

            elif block == "arm":
                #Crea les guies del brac
                arm_instance = ArmGuides(
                    "L_shoulder", "L_elbow", "L_wrist", "L_clavicule",
                    (3, 12, 0),
                    (13, 12, -0.1),
                    (23, 12, 0),
                    (0, 12, 0)
                )
                arm_instance.create_chain()
                new_groups.append(arm_instance.guides_group)

            elif block == "finger":
                #Crea les guies de la ma a partir del brac
                if arm_instance is None:
                    arm_instance = _ExistingJoints(wrist_joint="L_wrist")
                hand_instance = HandGuides(arm_instance)
                hand_instance.hand_guides()
                #Els dits pengen del canell: no tenen grup propi que agrupar.

            elif block == "leg":
                #Crea les guies de la cama
                leg_instance = LegGuides(
                    "L_hip", "L_knee", "L_ankle",
                    (3, -10, 0),
                    (3, -20, 0.2),
                    (3, -30, 0)
                )
                leg_instance.create_chain()
                new_groups.append(leg_instance.guides_group)

                #El peu va sempre amb la cama: el reverse foot no es opcional
                foot_instance = FootGuides(
                    leg_instance,
                    "L_ball",
                    "L_toe_tip",
                    "L_heel",
                    (0, -2, 3),
                    (0, -2, 6),
                    (0, -2, -3)
                )
                foot_instance.foot_guides()

            elif block == "toes":
                #Crea les guies dels dits del peu a partir del ball
                if foot_instance is None:
                    foot_instance = _ExistingJoints(ball_name="L_ball")
                toes_instance = ToesGuides(foot_instance, side="L")
                toes_instance.toes_guides()

            elif block == "mouth":
                #Crea les guies de la boca
                boca_instance = BocaGuides("boca_surface", "C_lip_mid", "L_lip_end",
                                           lip_in01="L_lip_in01", lip_in02="L_lip_in02")
                boca_instance.create_boca()
                new_groups.append(boca_instance.guides_group)

            elif block == "jaw":
                #Crea les guies de la jaw
                jaw_instance = JawGuides("jaw_root", "jaw_end", (0, 21, 5), (0, 19, 9))
                jaw_instance.jaw_guides()
                new_groups.append(jaw_instance.guides_group)

            elif block == "eye":
                #Crea les guies de l'ull
                eye_instance = EyeGuides(
                    "L_eye_mid",
                    "L_eye_mid_end",
                    "L_eye_direct",
                    (2, 26, 9),
                    (2, 26, 10),
                    (2, 26, 20)
                )
                eye_instance.eye_guides()
                new_groups.append(eye_instance.guides_group)

            elif block == "eyebrow":
                #Crea les guies de les celles
                eyebrows_instance = EyebrowsGuides("L_eyebrow_root", "L_eyebrow_end",
                                                   root_pos=(0, 34, 10), end_pos=(2.5, 34, 9))
                eyebrows_instance.eyebrows_guides()
                new_groups.append(eyebrows_instance.guides_group)

            elif block == "nose":
                #Crea les guies del nas
                nose_instance = NoseGuides("nose_root", "nose_tip",
                                           root_pos=(0, 27, 10), tip_pos=(0, 25, 12))
                nose_instance.nose_guides()
                new_groups.append(nose_instance.guides_group)

            elif block == "skull":
                #Crea la NURBS del crani per la que llisquen les celles.
                #El centre va a l'altura de les guies de les celles (Y = 34) perque
                #despres tot el guides_GRP es mou junt.
                skull_instance = EyebrowSkullGuides("eyebrow_skull_NRB", center=(0, 34, 0))
                skull_instance.create_skull()
                new_groups.append(skull_instance.guides_group)

            self.created.append(block)

        self._group_new_guides(new_groups)
        self._report()

        cmds.select(clear=True)

        return list(self.created)

    # ------------------------------------------------------------------
    # AGRUPAR
    # ------------------------------------------------------------------
    def _group_new_guides(self, groups):
        """
        Posa els grups nous sota guides_GRP.

        Totes les guies es creen a les seves posicions "crues", pensades per
        quedar al seu lloc quan guides_GRP puja GUIDES_OFFSET_Y.

        - Si guides_GRP no existeix, es crea amb els grups nous i es puja,
          exactament com abans.
        - Si ja existeix, els grups nous hi entren en RELATIU: conserven la
          posicio local i per tant reben el mateix desplacament (i escala, si
          l has escalat) que la resta de guies. En absolut quedarien
          GUIDES_OFFSET_Y per sota de les altres.
        """
        groups = [g for g in groups if g and cmds.objExists(g)]

        if not groups:
            if not self.created:
                return None
            #Nomes s han creat blocs sense grup propi (dits, dits del peu), que
            #ja pengen d una guia existent: no hi ha res a agrupar.
            return self.all_guides_grp

        if cmds.objExists(self.GUIDES_ROOT):
            cmds.parent(groups, self.GUIDES_ROOT, relative=True)
            self.all_guides_grp = self.GUIDES_ROOT
        else:
            self.all_guides_grp = cmds.group(groups, n=self.GUIDES_ROOT)
            cmds.setAttr(f"{self.all_guides_grp}.translateY", self.GUIDES_OFFSET_Y)

        return self.all_guides_grp

    def _report(self):
        if self.created:
            print("[Guides] Creades: {}".format(", ".join(self.created)))
        if self.skipped:
            print("[Guides] Ja existien, no es toquen: {}".format(", ".join(self.skipped)))
        if not self.created and not self.skipped:
            cmds.warning("[Guides] No hi havia cap guia a crear.")


class _ExistingJoints(object):
    """
    Substitut minim d ArmGuides / FootGuides per quan les guies del pare ja
    existien a l escena d una crida anterior. HandGuides nomes llegeix
    wrist_joint i ToesGuides nomes llegeix ball_name, aixi que amb el nom n hi
    ha prou.
    """

    def __init__(self, **names):
        for key, value in names.items():
            setattr(self, key, value)