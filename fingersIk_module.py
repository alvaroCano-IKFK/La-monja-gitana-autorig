import math

import maya.cmds as cmds


class FingersIkModule(object):
    """Setup IK de los dedos: ikHandle, control de punta, twist y space switch.

    Esto vivia dentro de fingers_module. Se ha sacado aqui porque el IK de los
    dedos es la mitad del modulo y no lo usa nadie mas: si en la receta no esta
    marcada la feature 'ik', este archivo ni se instancia.

    CONTRATO CON EL MODULO PADRE
    ----------------------------
    Recibe la instancia de FingersModule y usa de ella tres cosas, nada mas:

        parent._create_ctrl(lib_name, final_name)   crear control de la libreria
        parent._safe_parent(node, new_parent)       parent con proteccion de ciclos
        parent.group_maker                          ControlsGroups

    Se pasan por el padre en vez de duplicarlas porque _safe_parent tiene
    mensajes de aviso que hablan de los grupos de dedos: duplicarlo significaria
    arreglar el mismo bug dos veces. Es el mismo patron que ya usa
    twist_module, que tambien recibe parent=self.
    """

    #: Nombre del atributo de seguimiento en el control IK. Se declara como
    #: atributo de clase para que ToesIkModule solo tenga que cambiarlo.
    FOLLOW_ATTR = "FollowHand"
    FOLLOW_NICE = "Follow Hand"

    def __init__(self, parent, side="L", prefix="L_Character",
                 pref_angle=8.0,
                 ik_start_index=1,
                 ik_tip_rotation=True,
                 ik_follow_hand=0.0,
                 curl_axis_override=None,
                 ctrls_master_grp=None,
                 ikh_master_grp=None):

        self.parent = parent
        self.side   = side
        self.prefix = prefix

        # Estilos de control. Se heredan del modulo de dedos si los tiene, para
        # que el control IK siga saliendo con la misma forma que antes de
        # separar los dos modulos. El setdefault es la red de seguridad por si
        # alguien instancia este modulo sin padre completo.
        self.styles = dict(getattr(parent, "styles", None) or {})
        self.styles.setdefault("fingerIk", "squareControl")

        # Grados de "pre-doblado" que se le meten al RP solver para que sepa
        # hacia donde tiene que doblar el dedo.
        self.pref_angle = pref_angle

        # Joint por el que empieza el ikHandle (1 = se salta el metacarpo).
        self.ik_start_index = ik_start_index

        # True: el effector se queda en la articulacion distal y la rotacion
        # del control orienta la ultima falange.
        self.ik_tip_rotation = ik_tip_rotation

        # Valor por defecto de FollowHand: 0 = el dedo se queda clavado en
        # mundo aunque muevas el brazo, 1 = viaja con la mano.
        self.ik_follow_hand = ik_follow_hand

        # Si algun dedo dobla al reves: {"thumb": "-z"}
        self.curl_axis_override = curl_axis_override or {}

        self.ctrls_master_grp = ctrls_master_grp
        self.ikh_master_grp   = ikh_master_grp

    # ------------------------------------------------------------------ #
    #  ATAJOS AL PADRE
    # ------------------------------------------------------------------ #
    @property
    def group_maker(self):
        return self.parent.group_maker

    def _create_ctrl(self, lib_name, final_name):
        return self.parent._create_ctrl(lib_name, final_name)

    def _safe_parent(self, node, new_parent):
        return self.parent._safe_parent(node, new_parent)

    # ------------------------------------------------------------------ #
    #  MATEMATICAS BASICAS
    #
    #  Copiadas de fingers_module a proposito: asi este modulo se puede
    #  importar y probar solo, sin arrastrar la clase de dedos entera. Son
    #  cinco funciones de una linea, no compensa montar un modulo de utilidades
    #  para esto.
    # ------------------------------------------------------------------ #
    @staticmethod
    def _sub(a, b):
        return [a[i] - b[i] for i in range(3)]

    @staticmethod
    def _scale(a, f):
        return [a[i] * f for i in range(3)]

    @staticmethod
    def _dot(a, b):
        return sum(a[i] * b[i] for i in range(3))

    @staticmethod
    def _cross(a, b):
        return [a[1] * b[2] - a[2] * b[1],
                a[2] * b[0] - a[0] * b[2],
                a[0] * b[1] - a[1] * b[0]]

    @staticmethod
    def _mag(a):
        return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])

    @classmethod
    def _norm(cls, a):
        m = cls._mag(a)
        if m < 1e-9:
            return [0.0, 0.0, 0.0]
        return [a[0] / m, a[1] / m, a[2] / m]

    @classmethod
    def _local_axes(cls, node):
        """Ejes locales X, Y, Z del nodo expresados en mundo."""
        m = cmds.getAttr(f"{node}.worldMatrix[0]")
        return [cls._norm([m[0], m[1], m[2]]),
                cls._norm([m[4], m[5], m[6]]),
                cls._norm([m[8], m[9], m[10]])]

    # ------------------------------------------------------------------ #
    #  DETECCIÓN DEL EJE DE CURVATURA (la parte importante para el pulgar)
    # ------------------------------------------------------------------ #
    def detect_curl_normal(self, chain):
        """Devuelve la normal (en mundo) del plano en el que ya está doblada la cadena.

        Se queda con el tramo que más se dobla de todo el dedo. Si el dedo está
        perfectamente recto no se puede deducir nada y devuelve None.
        """
        pts = [cmds.xform(j, q=True, ws=True, t=True) for j in chain]
        best_n, best_mag = None, 0.0

        for i in range(len(pts) - 2):
            v1 = self._norm(self._sub(pts[i + 1], pts[i]))
            v2 = self._norm(self._sub(pts[i + 2], pts[i + 1]))
            n = self._cross(v1, v2)
            m = self._mag(n)
            if m > best_mag:
                best_mag, best_n = m, n

        if best_n is not None and best_mag > 1e-3:
            return self._norm(best_n)
        return None

    def fallback_curl_normal(self, all_chains):
        """Plan B cuando un dedo está totalmente recto: el eje 'a través de la palma'.

        Se calcula con el vector que va de la raíz del primer dedo a la del último
        (normalmente pulgar -> meñique), invertido en el lado derecho.
        """
        roots = [c[0] for c in all_chains if c]
        if len(roots) < 2:
            return None

        p_first = cmds.xform(roots[0], q=True, ws=True, t=True)
        p_last = cmds.xform(roots[-1], q=True, ws=True, t=True)
        across = self._norm(self._sub(p_last, p_first))
        if self._mag(across) < 1e-6:
            return None
        if self.side == "R":
            across = self._scale(across, -1.0)
        return across

    def apply_preferred_angles(self, chain, normal, finger_name,
                               start_idx=None, end_idx=None):
        """Pre-dobla la cadena IK en el plano correcto y guarda el preferred angle.

        Se calculan primero TODOS los ejes y después se aplican, porque al rotar
        un joint cambian las matrices de mundo de sus hijos.

        start_idx / end_idx acotan los joints que realmente resuelve el solver
        (el effector no se rota, así que no necesita preferred angle).
        """
        attrs = ("rotateX", "rotateY", "rotateZ")
        plan = []

        first = 1 if start_idx is None else max(0, start_idx)
        last = len(chain) - 1 if end_idx is None else end_idx
        solved = chain[first:last]
        if not solved:
            solved = chain[1:-1]

        override = self.curl_axis_override.get(finger_name)
        if override:
            token = override.strip().lower()
            sign = -1.0 if token.startswith("-") else 1.0
            axis = token.lstrip("+-")
            idx = {"x": 0, "y": 1, "z": 2}.get(axis, 2)
            for j in solved:
                plan.append((j, attrs[idx], sign))
        else:
            if normal is None:
                cmds.warning(f"[fingers] '{finger_name}' no tiene curvatura natural en la guía "
                             f"y no pude deducir un plan B. Se queda solo con FK/IK recto.")
                return False
            for j in solved:
                axes = self._local_axes(j)
                dots = [self._dot(normal, a) for a in axes]
                idx = max(range(3), key=lambda i: abs(dots[i]))
                if abs(dots[idx]) < 1e-4:
                    continue
                plan.append((j, attrs[idx], 1.0 if dots[idx] > 0 else -1.0))

        if not plan:
            return False

        for j, attr, sign in plan:
            try:
                cmds.setAttr(f"{j}.{attr}", self.pref_angle * sign)
            except Exception:
                pass

        cmds.joint(chain[0], edit=True, ch=True, spa=True)   # setPreferredAngles

        for j, attr, _ in plan:
            try:
                cmds.setAttr(f"{j}.{attr}", 0)
            except Exception:
                pass
        return True

    # ------------------------------------------------------------------ #
    #  IK
    # ------------------------------------------------------------------ #
    def create_finger_ik(self, ik_chain, bind_wrist, finger_name, parent_grp=None,
                         curl_normal=None):
        """Monta el ikHandle (RP solver) del dedo y su control en la punta."""
        if len(ik_chain) < 3:
            cmds.warning(f"[fingers] '{finger_name}' tiene menos de 3 joints, sin IK.")
            return None, None

        # Comprobamos que no haya huesos de longitud cero (rompen el solver)
        for a, b in zip(ik_chain[:-1], ik_chain[1:]):
            pa = cmds.xform(a, q=True, ws=True, t=True)
            pb = cmds.xform(b, q=True, ws=True, t=True)
            if self._mag(self._sub(pb, pa)) < 1e-4:
                cmds.warning(f"[fingers] '{finger_name}' tiene un hueso de longitud 0 "
                             f"({a} -> {b}), me salto el IK.")
                return None, None

        # 1. ¿Dónde empieza y dónde acaba el solver?
        #
        #    Para que la ROTACIÓN del control sirva de algo, el ikHandle NO puede
        #    llegar hasta la punta: si llegase, el solver decidiría también la
        #    orientación de la última falange y no quedaría nada que animar.
        #    Así que el effector se queda en la articulación distal (chain[-2]) y
        #    esa falange se orienta a mano con un orientConstraint al control.
        start_idx = self.ik_start_index
        end_idx = len(ik_chain) - 2 if self.ik_tip_rotation else len(ik_chain) - 1

        if end_idx - start_idx < 2:
            start_idx = max(0, end_idx - 2)
        free_tip = self.ik_tip_rotation and (end_idx - start_idx >= 2)
        if not free_tip:
            # Cadena demasiado corta: volvemos al modo clásico (sin rotación útil)
            end_idx = len(ik_chain) - 1
            start_idx = max(0, min(self.ik_start_index, end_idx - 2))
            if end_idx - start_idx < 2:
                cmds.warning(f"[fingers] '{finger_name}' es demasiado corto para el RP solver.")
                return None, None
            cmds.warning(f"[fingers] '{finger_name}' no tiene joints suficientes para "
                         f"liberar la última falange: la rotación del control IK no hará nada.")

        # 2. Preferred angles ANTES de crear el handle (solo en los joints que resuelve)
        self.apply_preferred_angles(ik_chain, curl_normal, finger_name,
                                    start_idx=start_idx, end_idx=end_idx)

        # 3. ikHandle
        ik_h, ik_eff = cmds.ikHandle(sj=ik_chain[start_idx], ee=ik_chain[end_idx],
                                     sol="ikRPsolver",
                                     n=f"{self.prefix}_{finger_name}_IKH")
        cmds.rename(ik_eff, f"{self.prefix}_{finger_name}_EFF")
        cmds.setAttr(f"{ik_h}.visibility", 0)
        try:
            cmds.setAttr(f"{ik_h}.snapEnable", 0)
        except Exception:
            pass

        # 3. Control IK en la punta del dedo
        ctrl_name = f"{self.prefix}_{finger_name}_ik_CTRL"
        ik_ctrl = self._create_ctrl(self.styles["fingerIk"], ctrl_name)
        ik_gen = self.group_maker.create_rig_hierarchy(ik_ctrl, ik_chain[-1])

        parent_grp = parent_grp or self.ctrls_master_grp
        if parent_grp:
            self._safe_parent(ik_gen, parent_grp)

        # OJO: aquí NO se hace parentConstraint al wrist. El control IK vive en
        # espacio mundo para que el dedo se quede clavado cuando mueves el brazo.
        # El seguimiento a la mano es opcional vía atributo FollowHand.
        self.create_ik_space_switch(ik_gen, ik_ctrl, bind_wrist, finger_name, parent_grp)

        # El handle vive fuera de la jerarquía de controles (por el scaleX -1 del lado R)
        if self.ikh_master_grp and cmds.objExists(self.ikh_master_grp):
            cmds.parent(ik_h, self.ikh_master_grp)

        # Null hijo del control, colocado en la articulación distal. Es lo que
        # arrastra el handle: al ROTAR el control, este null orbita alrededor del
        # pivote del control (la punta del dedo), así que la última falange gira
        # dejando la yema donde estaba. Al mover el control, lo arrastra entero.
        # Uso un pointConstraint (no parentConstraint) porque solo lee posición en
        # mundo y así no le afecta el scaleX -1 del lado derecho.
        ik_target = cmds.group(em=True, n=f"{self.prefix}_{finger_name}_ikTarget_TRN",
                               p=ik_ctrl)
        cmds.matchTransform(ik_target, ik_chain[end_idx], pos=True, rot=False, scl=False)
        cmds.setAttr(f"{ik_target}.visibility", 0)
        cmds.pointConstraint(ik_target, ik_h, mo=False)

        # La última falange (el joint que hace de effector) queda fuera del solver,
        # así que su orientación la manda directamente el control.
        if free_tip:
            cmds.orientConstraint(ik_ctrl, ik_chain[end_idx], mo=True)

        # 4. Twist en vez de pole vector (5 pole vectors en una mano es un infierno)
        if not cmds.attributeQuery("Twist", node=ik_ctrl, exists=True):
            cmds.addAttr(ik_ctrl, ln="Twist", at="double", dv=0, k=True)
        mdl = cmds.createNode("multDoubleLinear",
                              n=f"{self.prefix}_{finger_name}_twist_MDL")
        cmds.setAttr(f"{mdl}.input2", 1.0 if self.side == "L" else -1.0)
        cmds.connectAttr(f"{ik_ctrl}.Twist", f"{mdl}.input1")
        cmds.connectAttr(f"{mdl}.output", f"{ik_h}.twist")

        return ik_ctrl, ik_h

    # ------------------------------------------------------------------ #
    #  SPACE SWITCH DEL CONTROL IK  (mundo <-> mano)
    # ------------------------------------------------------------------ #
    def create_ik_space_switch(self, ik_gen, ik_ctrl, bind_wrist, finger_name, parent_grp):
        """Dos espacios para el control IK del dedo.

        - WORLD: un grupo estático. Es el que manda por defecto, así que si mueves
          los controles IK/FK del brazo, el dedo se queda donde está (mano apoyada
          en el suelo, agarrando algo que no se mueve, etc).
        - HAND: un grupo constreñido al wrist bind. Con FollowHand = 1 el control
          IK viaja con la mano, como hacía antes.

        Los dos grupos se crean EXACTAMENTE encima del grupo del control, así que
        el offset es cero y el switch no da saltos.
        """
        spaces_grp = cmds.group(em=True,
                                n=f"{self.prefix}_{finger_name}_ikSpaces_GRP",
                                p=parent_grp)
        cmds.setAttr(f"{spaces_grp}.visibility", 0)

        space_world = cmds.group(em=True,
                                 n=f"{self.prefix}_{finger_name}_ikSpaceWorld_GRP",
                                 p=spaces_grp)
        space_hand = cmds.group(em=True,
                                n=f"{self.prefix}_{finger_name}_ikSpaceHand_GRP",
                                p=spaces_grp)

        cmds.matchTransform(space_world, ik_gen)
        cmds.matchTransform(space_hand, ik_gen)

        if cmds.objExists(bind_wrist):
            cmds.parentConstraint(bind_wrist, space_hand, mo=True)

        if not cmds.attributeQuery(self.FOLLOW_ATTR, node=ik_ctrl, exists=True):
            cmds.addAttr(ik_ctrl, ln=self.FOLLOW_ATTR, nn=self.FOLLOW_NICE, at="double",
                         min=0, max=1, dv=self.ik_follow_hand, k=True)

        pc = cmds.parentConstraint(space_world, space_hand, ik_gen, mo=True)[0]
        cmds.setAttr(f"{pc}.interpType", 2)      # shortest, para que no flipee

        aliases = cmds.parentConstraint(pc, q=True, weightAliasList=True)
        world_alias, hand_alias = aliases[0], aliases[1]

        rev = cmds.createNode("reverse", n=f"{self.prefix}_{finger_name}_ikFollow_REV")
        cmds.connectAttr(f"{ik_ctrl}.{self.FOLLOW_ATTR}", f"{rev}.inputX")
        cmds.connectAttr(f"{rev}.outputX", f"{pc}.{world_alias}")
        cmds.connectAttr(f"{ik_ctrl}.{self.FOLLOW_ATTR}", f"{pc}.{hand_alias}")

        return pc

    # ------------------------------------------------------------------ #
    #  ENTRADA DESDE EL MODULO DE DEDOS
    # ------------------------------------------------------------------ #
    def build_finger(self, ik_chain, bind_wrist, finger_name, parent_grp,
                     curl_normal):
        """Punto de entrada unico. Devuelve (ik_ctrl, ik_handle)."""
        return self.create_finger_ik(ik_chain, bind_wrist, finger_name,
                                     parent_grp=parent_grp,
                                     curl_normal=curl_normal)


class ToesIkModule(FingersIkModule):
    """IK de los dedos del pie.

    Es igual que el de la mano salvo el space switch: el dedo del pie se queda
    clavado en el suelo mientras el talon despega, y el espacio alternativo es
    el pie, no la muneca.

    Esta clase existe porque ToesModule hereda de FingersModule y sobreescribia
    create_ik_space_switch. Al sacar el IK a su propio modulo, ese override
    dejaba de tener efecto: create_finger_ik llama a self.create_ik_space_switch
    y ese self ya no es el modulo de dedos, es el de IK. La solucion es que el
    modulo de dedos diga QUE clase de IK quiere (FingersModule.IK_BUILDER) y los
    pies apunten a esta.
    """

    FOLLOW_ATTR = "FollowFoot"
    FOLLOW_NICE = "Follow Foot"

    def create_ik_space_switch(self, ik_gen, ik_ctrl, bind_ball, toe_name, parent_grp):
        """Dos espacios para el control IK del dedo del pie.

        - WORLD: grupo estático. Con FollowFoot = 0 el dedo se queda clavado en
          el suelo aunque el pie ruede: es justo lo que se quiere para que los
          dedos se queden pegados al suelo mientras el talón despega.
        - FOOT: grupo constreñido al ball bind. Con FollowFoot = 1 el control
          viaja con el pie.
        """
        spaces_grp = cmds.group(em=True,
                                n=f"{self.prefix}_{toe_name}_ikSpaces_GRP",
                                p=parent_grp)
        cmds.setAttr(f"{spaces_grp}.visibility", 0)

        space_world = cmds.group(em=True,
                                 n=f"{self.prefix}_{toe_name}_ikSpaceWorld_GRP",
                                 p=spaces_grp)
        space_foot = cmds.group(em=True,
                                n=f"{self.prefix}_{toe_name}_ikSpaceFoot_GRP",
                                p=spaces_grp)

        cmds.matchTransform(space_world, ik_gen)
        cmds.matchTransform(space_foot, ik_gen)

        if cmds.objExists(bind_ball):
            cmds.parentConstraint(bind_ball, space_foot, mo=True)

        if not cmds.attributeQuery(self.FOLLOW_ATTR, node=ik_ctrl, exists=True):
            cmds.addAttr(ik_ctrl, ln=self.FOLLOW_ATTR, nn=self.FOLLOW_NICE,
                         at="double", min=0, max=1, dv=self.ik_follow_hand, k=True)

        pc = cmds.parentConstraint(space_world, space_foot, ik_gen, mo=True)[0]
        cmds.setAttr(f"{pc}.interpType", 2)      # shortest, para que no flipee

        aliases = cmds.parentConstraint(pc, q=True, weightAliasList=True)
        world_alias, foot_alias = aliases[0], aliases[1]

        rev = cmds.createNode("reverse", n=f"{self.prefix}_{toe_name}_ikFollow_REV")
        cmds.connectAttr(f"{ik_ctrl}.{self.FOLLOW_ATTR}", f"{rev}.inputX")
        cmds.connectAttr(f"{rev}.outputX", f"{pc}.{world_alias}")
        cmds.connectAttr(f"{ik_ctrl}.{self.FOLLOW_ATTR}", f"{pc}.{foot_alias}")

        return pc