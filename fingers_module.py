import re
import math

import maya.cmds as cmds
import controlsLibrary
import groups_module

try:
    from nodeCreator_module import NodeCreator
except Exception:
    NodeCreator = None


class FingersModule(object):
    """Módulo de dedos con setup IK/FK y switch independiente por dedo.

    - La cadena BIND se sigue calcando de las guías (posición + orientación exacta).
    - Se duplican dos cadenas (_fk_JNT / _ik_JNT) y se mezclan con pairBlend,
      igual que en limbs_module.
    - El eje de curvatura (preferred angle) se DETECTA por geometría dedo a dedo,
      así que el pulgar funciona aunque esté orientado distinto y arranque en la
      misma posición que el primer joint del índice.
    """

    # ------------------------------------------------------------------ #
    #  INIT
    # ------------------------------------------------------------------ #
    def __init__(self, wrist_guide="wrist", rig_name="Character", side="L",
                 root_instance=None,
                 build_ik=True,
                 pref_angle=8.0,
                 settings_ctrl=None,
                 ik_follow_hand=0.0):

        self.wrist_guide = wrist_guide
        self.rig_name    = rig_name
        self.side        = side

        self.styles = {
            "finger":   "fingerControl",
            "fingerIk": "squareControl",
            "switch":   "switchControl02",
        }

        self.group_maker = groups_module.ControlsGroups()

        self.joints_master_grp = None
        self.ctrls_master_grp  = None
        self.ikh_master_grp    = None
        self.root_instance     = root_instance

        self.prefix = f"{self.side}_{self.rig_name}"
        self.names  = ["clavicule", "shoulder", "elbow", "wrist"]

        # --- opciones IK ---
        self.build_ik   = build_ik
        self.pref_angle = pref_angle          # grados de "pre-doblado" para el RP solver
        self.settings_ctrl = settings_ctrl    # si le pasas un control existente, cuelga ahí los atributos

        # Valor por defecto del atributo FollowHand de los controles IK:
        #   0 = el control IK se queda en el sitio aunque muevas el brazo (dedo clavado)
        #   1 = el control IK viaja con la mano
        self.ik_follow_hand = ik_follow_hand

        # Joint por el que empieza el ikHandle (1 = se salta el metacarpo).
        self.ik_start_index = 1
        # True: el effector se queda en la articulación distal y la rotación del
        # control IK orienta la última falange (aplastarla contra una mesa, etc).
        self.ik_tip_rotation = True

        # Si algún dedo dobla al revés, fuerza aquí su eje local de curvatura.
        # Ej: self.curl_axis_override = {"thumb": "-z", "pinky": "y"}
        self.curl_axis_override = {}

        # Info generada en el build: {finger_name: {...}}
        self.fingers_data = {}

    # ------------------------------------------------------------------ #
    #  MATEMÁTICAS BÁSICAS (sin numpy, que en mayapy a veces da guerra)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _sub(a, b):
        return [a[i] - b[i] for i in range(3)]

    @staticmethod
    def _add(a, b):
        return [a[i] + b[i] for i in range(3)]

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
        """Devuelve los ejes locales X, Y, Z del nodo expresados en mundo."""
        m = cmds.getAttr(f"{node}.worldMatrix[0]")
        return [cls._norm([m[0], m[1], m[2]]),
                cls._norm([m[4], m[5], m[6]]),
                cls._norm([m[8], m[9], m[10]])]

    # ------------------------------------------------------------------ #
    #  UTILIDADES DE NOMBRES / CONTROLES
    # ------------------------------------------------------------------ #
    def _clean_finger_name(self, guide):
        """'L_thumb_01_guide' -> 'thumb'  (para nombrar atributos y grupos)."""
        n = guide.split("|")[-1].split(":")[-1]
        for token in ("_guide", "_Guide", "_GUIDE", "_guides", "_GUIDES", "_JNT", "_jnt"):
            n = n.replace(token, "")
        for p in ("L_", "R_", "l_", "r_"):
            if n.startswith(p):
                n = n[2:]
                break
        n = re.sub(r"[^A-Za-z0-9_]", "_", n)
        n = re.sub(r"[_0-9]+$", "", n)          # se come el "_01" final
        if not n:
            n = "finger"
        if n[0].isdigit():
            n = "f_" + n
        return n

    def _create_ctrl(self, lib_name, final_name):
        """Crea un control de la librería, con red de seguridad por si el estilo no existe."""
        if cmds.objExists(final_name):
            return final_name
        try:
            return controlsLibrary.create_control_from_lib(lib_name=lib_name,
                                                           final_name=final_name)
        except Exception as e:
            cmds.warning(f"[fingers] No pude crear '{lib_name}' ({e}). Uso un círculo por defecto.")
            return cmds.circle(n=final_name, nr=(1, 0, 0), r=1.0, ch=False)[0]

    def _safe_parent(self, node, new_parent):
        """cmds.parent con protección contra ciclos.

        La causa típica de 'Cannot parent an object to one of its children'
        aquí es que el nodo ya existía de un build anterior (por el patrón
        'if cmds.objExists(...): return' usado en _create_ctrl / creación de
        grupos) y ya estaba colgado en otra parte de la jerarquía. En vez de
        petar el build entero, avisamos y seguimos.
        """
        if not node or not new_parent or node == new_parent:
            return
        if not cmds.objExists(node) or not cmds.objExists(new_parent):
            return

        current_parents = cmds.listRelatives(node, parent=True, fullPath=True) or []
        new_parent_full = cmds.ls(new_parent, long=True)[0]
        if current_parents and current_parents[0] == new_parent_full:
            return  # ya está donde tiene que estar

        descendants = cmds.listRelatives(node, ad=True, fullPath=True) or []
        if new_parent_full in descendants:
            cmds.warning(
                f"[fingers] Salto el parent de '{node}' bajo '{new_parent}': "
                f"'{new_parent}' ya es descendiente de '{node}' (probablemente "
                f"un nodo reciclado de un build anterior). Borra el rig de dedos "
                f"viejo ({self.prefix}_Fingers_CTRL_GRP / {self.prefix}_Fingers_IKH_GRP) "
                f"y reconstruye desde cero."
            )
            return

        cmds.parent(node, new_parent)

    def _cleanup_previous_build(self):
        """Borra un build anterior de dedos de este mismo lado/rig antes de
        empezar uno nuevo, para no arrastrar nodos reciclados a mitad de la
        jerarquía (causa principal del error de parent en ciclo)."""
        ctrl_grp_name = f"{self.prefix}_Fingers_CTRL_GRP"
        ikh_grp_name = f"{self.prefix}_Fingers_IKH_GRP"
        for grp in (ctrl_grp_name, ikh_grp_name):
            if cmds.objExists(grp):
                cmds.delete(grp)

    def _make_pairblend(self, finger_name, part):
        """pairBlend usando tu NodeCreator si está disponible."""
        if NodeCreator is not None:
            try:
                return NodeCreator(side=self.side,
                                   node_type="pairBlend",
                                   base_name=self.prefix,
                                   name=f"{finger_name}_{part}",
                                   tag="blend",
                                   parent=None,
                                   custom_suffix=None).create()
            except Exception:
                pass
        return cmds.createNode("pairBlend",
                               n=f"{self.prefix}_{finger_name}_{part}_blend")

    # ------------------------------------------------------------------ #
    #  GUÍAS Y CADENAS
    # ------------------------------------------------------------------ #
    def get_finger_roots(self):
        """Obtiene las guías raíz de los dedos como hijos del wrist_guide."""
        return cmds.listRelatives(self.wrist_guide, c=True, type="joint") or []

    def build_finger_from_guides(self, guide_root):
        """Construye una cadena de joints calcando la jerarquía y rotación exacta de las guías."""
        # 1. Encontrar la cadena de guías respetando el orden jerárquico descendente
        guide_chain = [guide_root]
        current = guide_root
        while True:
            children = cmds.listRelatives(current, c=True, type="joint")
            if not children:
                break
            guide_chain.append(children[0])
            current = children[0]

        rig_chain = []
        cmds.select(clear=True)

        # 2. Crear los joints copiando posición Y orientación de cada guía
        for guide in guide_chain:
            jnt_name = f"{self.prefix}_{guide}_JNT"
            new_joint = cmds.joint(n=jnt_name)

            temp_constraint = cmds.parentConstraint(guide, new_joint, mo=False)
            cmds.delete(temp_constraint)

            # Las rotaciones se van al jointOrient
            cmds.makeIdentity(new_joint, apply=True, t=0, r=1, s=0, n=0, pn=1)

            rig_chain.append(new_joint)

        cmds.select(clear=True)
        return rig_chain

    def duplicate_chain(self, chain, suffix):
        """Duplica una cadena bind y la renombra insertando _fk_ / _ik_ antes del _JNT."""
        dup = cmds.duplicate(chain[0], rc=True)
        new_chain = [dup[0]]
        kids = cmds.listRelatives(dup[0], ad=True, type="joint") or []
        kids.reverse()
        new_chain += kids

        out = []
        for src, new in zip(chain, new_chain):
            base = src[:-4] if src.endswith("_JNT") else src
            out.append(cmds.rename(new, f"{base}_{suffix}_JNT"))
        return out

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
    #  CONTROL DE AJUSTES (donde viven los switches IK/FK)
    # ------------------------------------------------------------------ #
    def get_or_create_settings_ctrl(self, bind_wrist, all_chains):
        """Devuelve el control donde colgar los atributos IK_FK de cada dedo."""
        if self.settings_ctrl and cmds.objExists(self.settings_ctrl):
            return self.settings_ctrl

        name = f"{self.prefix}_fingersSettings_CTRL"
        if cmds.objExists(name):
            self.settings_ctrl = name
            return name

        ctrl = self._create_ctrl(self.styles["switch"], name)
        target = bind_wrist if cmds.objExists(bind_wrist) else self.wrist_guide
        gen = self.group_maker.create_rig_hierarchy(ctrl, target)

        if self.ctrls_master_grp:
            self._safe_parent(gen, self.ctrls_master_grp)

        # Lo colocamos un poco más allá de las puntas de los dedos
        wrist_pos = cmds.xform(target, q=True, ws=True, t=True)
        tips = [cmds.xform(c[-1], q=True, ws=True, t=True) for c in all_chains if c]
        if tips:
            avg = [sum(t[i] for t in tips) / float(len(tips)) for i in range(3)]
            direction = self._sub(avg, wrist_pos)
            cmds.xform(gen, ws=True, t=self._add(wrist_pos, self._scale(direction, 1.6)))

        if cmds.objExists(bind_wrist):
            cmds.parentConstraint(bind_wrist, gen, mo=True)

        if not cmds.attributeQuery("FINGERS", node=ctrl, exists=True):
            cmds.addAttr(ctrl, ln="FINGERS", nn="FINGERS", at="enum", en="------", k=True)
            cmds.setAttr(f"{ctrl}.FINGERS", lock=True, cb=True)

        self.settings_ctrl = ctrl
        return ctrl

    # ------------------------------------------------------------------ #
    #  FK
    # ------------------------------------------------------------------ #
    def create_finger_controls(self, fk_chain, bind_wrist, parent_grp=None):
        """Crea controles FK para cada joint del dedo (menos la punta) y los constriñe al wrist."""
        controls = []
        parent_grp = parent_grp or self.ctrls_master_grp

        for i, jnt in enumerate(fk_chain[:-1]):
            ctrl_name = jnt.replace("_JNT", "_CTRL")
            ctrl = self._create_ctrl(self.styles["finger"], ctrl_name)

            grp = self.group_maker.create_rig_hierarchy(ctrl, jnt)
            cmds.parentConstraint(ctrl, jnt, mo=True)

            if i == 0:
                if parent_grp:
                    self._safe_parent(grp, parent_grp)
                if cmds.objExists(bind_wrist):
                    cmds.parentConstraint(bind_wrist, grp, mo=True)
            elif controls:
                self._safe_parent(grp, controls[-1])

            controls.append(ctrl)

        return controls

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

        if not cmds.attributeQuery("FollowHand", node=ik_ctrl, exists=True):
            cmds.addAttr(ik_ctrl, ln="FollowHand", nn="Follow Hand", at="double",
                         min=0, max=1, dv=self.ik_follow_hand, k=True)

        pc = cmds.parentConstraint(space_world, space_hand, ik_gen, mo=True)[0]
        cmds.setAttr(f"{pc}.interpType", 2)      # shortest, para que no flipee

        aliases = cmds.parentConstraint(pc, q=True, weightAliasList=True)
        world_alias, hand_alias = aliases[0], aliases[1]

        rev = cmds.createNode("reverse", n=f"{self.prefix}_{finger_name}_ikFollow_REV")
        cmds.connectAttr(f"{ik_ctrl}.FollowHand", f"{rev}.inputX")
        cmds.connectAttr(f"{rev}.outputX", f"{pc}.{world_alias}")
        cmds.connectAttr(f"{ik_ctrl}.FollowHand", f"{pc}.{hand_alias}")

        return pc

    # ------------------------------------------------------------------ #
    #  BLEND IK / FK
    # ------------------------------------------------------------------ #
    def blend_chains(self, bind_chain, ik_chain, fk_chain, switch_attr, finger_name):
        """pairBlend por joint: weight 0 = IK, weight 1 = FK (igual que en limbs_module)."""
        for i, bnd in enumerate(bind_chain):
            ik_jnt = ik_chain[i] if ik_chain else None
            fk_jnt = fk_chain[i]

            if cmds.listConnections(f"{bnd}.rotate", s=True, d=False, p=False):
                continue

            if not ik_jnt:
                # Sin IK: el FK manda directamente
                cmds.connectAttr(f"{fk_jnt}.translate", f"{bnd}.translate")
                cmds.connectAttr(f"{fk_jnt}.rotate", f"{bnd}.rotate")
                continue

            pbl = self._make_pairblend(finger_name, f"{i:02d}")
            cmds.setAttr(f"{pbl}.rotInterpolation", 1)     # quaternion

            cmds.connectAttr(f"{ik_jnt}.translate", f"{pbl}.inTranslate1")
            cmds.connectAttr(f"{ik_jnt}.rotate",    f"{pbl}.inRotate1")
            cmds.connectAttr(f"{fk_jnt}.translate", f"{pbl}.inTranslate2")
            cmds.connectAttr(f"{fk_jnt}.rotate",    f"{pbl}.inRotate2")

            cmds.connectAttr(f"{pbl}.outTranslate", f"{bnd}.translate")
            cmds.connectAttr(f"{pbl}.outRotate",    f"{bnd}.rotate")
            cmds.connectAttr(switch_attr, f"{pbl}.weight")

    # ------------------------------------------------------------------ #
    #  BUILD
    # ------------------------------------------------------------------ #
    def build(self):
        """Construye los dedos (IK + FK + switch) para el lado definido en self.side."""

        target_bind_wrist = f"{self.prefix}_{self.names[3]}_bind_JNT"
        if not cmds.objExists(target_bind_wrist):
            cmds.warning(f"[fingers] No existe {target_bind_wrist}. "
                         f"Construye el LimbModule antes que los dedos.")

        # ---- LIMPIEZA DE UN BUILD ANTERIOR (evita nodos reciclados en ciclo) ----
        self._cleanup_previous_build()

        # ---- GRUPOS MAESTROS ----
        ctrl_grp_name = f"{self.prefix}_Fingers_CTRL_GRP"
        self.ctrls_master_grp = ctrl_grp_name if cmds.objExists(ctrl_grp_name) \
            else cmds.group(em=True, n=ctrl_grp_name)

        ikh_grp_name = f"{self.prefix}_Fingers_IKH_GRP"
        self.ikh_master_grp = ikh_grp_name if cmds.objExists(ikh_grp_name) \
            else cmds.group(em=True, n=ikh_grp_name)

        finger_roots = self.get_finger_roots()
        if not finger_roots:
            cmds.warning(f"[fingers] {self.wrist_guide} no tiene guías de dedos.")
            return

        # ---- 1. CADENAS BIND (todavía en world, sin emparentar) ----
        built = []          # [(finger_name, guide_root, bind_chain), ...]
        used_names = {}
        for root in finger_roots:
            bind_chain = self.build_finger_from_guides(root)
            name = self._clean_finger_name(root)
            if name in used_names:
                used_names[name] += 1
                name = f"{name}{used_names[name]}"
            else:
                used_names[name] = 1
            built.append((name, root, bind_chain))

        all_chains = [b[2] for b in built]

        # ---- 2. CONTROL DE AJUSTES ----
        settings = self.get_or_create_settings_ctrl(target_bind_wrist, all_chains)

        # Plan B para dedos totalmente rectos
        fallback_normal = self.fallback_curl_normal(all_chains)

        # ---- 3. DEDO A DEDO ----
        for finger_name, guide_root, bind_chain in built:

            # 3.1 Normal de curvatura ANTES de duplicar (misma pose en las 3 cadenas)
            curl_normal = self.detect_curl_normal(bind_chain)
            if curl_normal is None:
                curl_normal = fallback_normal
                if not self.curl_axis_override.get(finger_name):
                    cmds.warning(f"[fingers] '{finger_name}' está recto en la guía: uso el eje "
                                 f"de la palma. Si dobla al revés usa curl_axis_override.")

            # 3.2 Duplicar cadenas FK / IK
            fk_chain = self.duplicate_chain(bind_chain, "fk")
            ik_chain = self.duplicate_chain(bind_chain, "ik") if self.build_ik else []

            # 3.3 Emparentar las tres cadenas bajo el wrist bind (mismos valores locales)
            if cmds.objExists(target_bind_wrist):
                cmds.parent(bind_chain[0], target_bind_wrist)
                cmds.parent(fk_chain[0], target_bind_wrist)
                if ik_chain:
                    cmds.parent(ik_chain[0], target_bind_wrist)

            cmds.setAttr(f"{fk_chain[0]}.visibility", 0)
            if ik_chain:
                cmds.setAttr(f"{ik_chain[0]}.visibility", 0)

            # 3.4 Grupos de organización / visibilidad (identidad, no tocan transforms)
            #     OJO con el nombre: create_rig_hierarchy genera sus grupos cambiando
            #     _CTRL por _GRP/_SPC/_OFF/_SDK. Como el control IK se llama
            #     "{prefix}_{finger}_ik_CTRL", su grupo sería "{prefix}_{finger}_ik_GRP"
            #     y chocaría con este. De ahí el sufijo _fkCtrls_ / _ikCtrls_.
            fk_grp = cmds.group(em=True, n=f"{self.prefix}_{finger_name}_fkCtrls_GRP",
                                p=self.ctrls_master_grp)
            ik_grp = cmds.group(em=True, n=f"{self.prefix}_{finger_name}_ikCtrls_GRP",
                                p=self.ctrls_master_grp) if ik_chain else None

            # 3.5 Controles FK
            fk_ctrls = self.create_finger_controls(fk_chain, target_bind_wrist,
                                                   parent_grp=fk_grp)

            # 3.6 Setup IK
            ik_ctrl, ik_handle = (None, None)
            if ik_chain:
                ik_ctrl, ik_handle = self.create_finger_ik(ik_chain, target_bind_wrist,
                                                           finger_name,
                                                           parent_grp=ik_grp,
                                                           curl_normal=curl_normal)
                if ik_ctrl is None:
                    # El IK no se pudo montar: limpiamos la cadena para no dejar basura
                    cmds.delete(ik_chain[0])
                    ik_chain = []
                    if ik_grp and cmds.objExists(ik_grp):
                        cmds.delete(ik_grp)
                        ik_grp = None

            # 3.7 Atributo de switch en el control de ajustes
            attr_name = f"{finger_name}_IK_FK"
            if not cmds.attributeQuery(attr_name, node=settings, exists=True):
                cmds.addAttr(settings, ln=attr_name, at="double",
                             min=0, max=1, dv=1, k=True)
            switch_attr = f"{settings}.{attr_name}"

            # 3.8 Blend
            self.blend_chains(bind_chain, ik_chain, fk_chain, switch_attr, finger_name)

            # 3.9 Visibilidad (1 = FK, 0 = IK, igual que en el brazo)
            if ik_grp:
                vis_rev = cmds.createNode("reverse",
                                          n=f"{self.prefix}_{finger_name}_VIS_REV")
                cmds.connectAttr(switch_attr, f"{vis_rev}.inputX")
                cmds.connectAttr(switch_attr, f"{fk_grp}.visibility")
                cmds.connectAttr(f"{vis_rev}.outputX", f"{ik_grp}.visibility")

            self.fingers_data[finger_name] = {
                "bind_chain": bind_chain,
                "fk_chain":   fk_chain,
                "ik_chain":   ik_chain,
                "fk_ctrls":   fk_ctrls,
                "ik_ctrl":    ik_ctrl,
                "ik_handle":  ik_handle,
                "switch":     switch_attr,
                "fk_grp":     fk_grp,
                "ik_grp":     ik_grp,
            }

        # ---- 4. ORGANIZACIÓN FINAL ----
        # Grupo de ikHandles: fuera de los controles, dentro del rig
        arm_grp = f"{self.prefix}_arm_GRP"
        rig_grp = f"{self.root_instance.rig_name}_rig_GRP" if self.root_instance else None
        if cmds.objExists(arm_grp):
            cmds.parent(self.ikh_master_grp, arm_grp)
        elif rig_grp and cmds.objExists(rig_grp):
            cmds.parent(self.ikh_master_grp, rig_grp)

        if self.side == "R":
            # Lado R: bajo mirrorBehaviour_GRP (scaleX -1 invierte el comportamiento)
            mirror_grp = f"{self.root_instance.rig_name}_mirrorBehaviour_GRP" \
                if self.root_instance else "Character_mirrorBehaviour_GRP"
            if cmds.objExists(mirror_grp):
                cmds.parent(self.ctrls_master_grp, mirror_grp)
            else:
                cmds.warning(f"fingers build: no existe {mirror_grp}")
        else:
            local_ctl = self.root_instance.localCtl if self.root_instance else None
            if local_ctl and cmds.objExists(local_ctl):
                cmds.parent(self.ctrls_master_grp, local_ctl)

        print(f"Build {self.prefix} completo. Dedos: {list(self.fingers_data.keys())}")

    # ------------------------------------------------------------------ #
    #  UTILIDAD PARA ANIMACIÓN / DEBUG
    # ------------------------------------------------------------------ #
    def match_ik_to_fk(self, finger_name, switch=True):
        """Coloca el control IK sobre la punta actual del dedo y pasa a IK.

        Como el control IK ya no sigue a la mano, esto es lo que hay que usar al
        cambiar de FK a IK: primero se pega el control a donde está el dedo ahora
        y después se cambia el switch, para que no pegue un salto.
        """
        data = self.fingers_data.get(finger_name)
        if not data or not data.get("ik_ctrl"):
            cmds.warning(f"[fingers] '{finger_name}' no tiene IK.")
            return

        cmds.matchTransform(data["ik_ctrl"], data["bind_chain"][-1], pos=True, rot=False)
        if switch and data.get("switch"):
            cmds.setAttr(data["switch"], 0)   # 0 = IK

    def match_all_ik_to_fk(self, switch=True):
        """Lo mismo para todos los dedos de la mano."""
        for finger_name in self.fingers_data:
            if self.fingers_data[finger_name].get("ik_ctrl"):
                self.match_ik_to_fk(finger_name, switch=switch)