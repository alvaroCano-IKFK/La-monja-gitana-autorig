import re
import math

import maya.cmds as cmds
import controlsLibrary
import groups_module
import module_specs
import fingersIk_module

try:
    from nodeCreator_module import NodeCreator
except Exception:
    NodeCreator = None


class FingersModule(module_specs.FeaturesMixin):
    """Módulo de dedos con setup FK (y opcionalmente IK) y switch por dedo.

    - La cadena BIND se sigue calcando de las guías (posición + orientación exacta).
    - Se duplican dos cadenas (_fk_JNT / _ik_JNT) y se mezclan con pairBlend,
      igual que en limbs_module.
    - El eje de curvatura (preferred angle) se DETECTA por geometría dedo a dedo,
      así que el pulgar funciona aunque esté orientado distinto y arranque en la
      misma posición que el primer joint del índice.
    - El setup IK vive en fingersIk_module y solo se instancia si la feature
      'ik' esta en la receta.
    """

    MODULE_TYPE = "finger"

    # ------------------------------------------------------------------ #
    #  INIT
    # ------------------------------------------------------------------ #
    def __init__(self, wrist_guide="wrist", rig_name="Character", side="L",
                 root_instance=None,
                 build_ik=True,
                 pref_angle=8.0,
                 settings_ctrl=None,
                 ik_follow_hand=0.0,
                 features=None):

        self._init_features(self.MODULE_TYPE, features)

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
        # Dos llaves tienen que estar de acuerdo: el flag de siempre y la
        # feature de la receta. Asi el modulo se puede seguir instanciando a
        # mano con build_ik=False sin tocar la receta, y a la vez la ventana
        # manda cuando hay receta.
        self.build_ik   = bool(build_ik) and self.has("ik")
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

        # Se crea en build() solo si hace falta IK
        self.ik_builder = None

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

        # ---- MODULO DE IK (solo si la receta lo pide) ----
        if self.build_ik:
            self.ik_builder = fingersIk_module.FingersIkModule(
                parent=self,
                side=self.side,
                prefix=self.prefix,
                pref_angle=self.pref_angle,
                ik_start_index=self.ik_start_index,
                ik_tip_rotation=self.ik_tip_rotation,
                ik_follow_hand=self.ik_follow_hand,
                curl_axis_override=self.curl_axis_override,
                ctrls_master_grp=self.ctrls_master_grp,
                ikh_master_grp=self.ikh_master_grp,
            )
        else:
            print(f"[{self.prefix}] IK de dedos desactivado en la receta.")

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

        # Plan B para dedos totalmente rectos. Solo se usa para los preferred
        # angles del solver, asi que sin IK no hay nada que calcular.
        fallback_normal = (self.ik_builder.fallback_curl_normal(all_chains)
                           if self.ik_builder else None)

        # ---- 3. DEDO A DEDO ----
        for finger_name, guide_root, bind_chain in built:

            # 3.1 Normal de curvatura ANTES de duplicar (misma pose en las 3 cadenas)
            curl_normal = None
            if self.ik_builder:
                curl_normal = self.ik_builder.detect_curl_normal(bind_chain)
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
                ik_ctrl, ik_handle = self.ik_builder.build_finger(ik_chain,
                                                                  target_bind_wrist,
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

            # 3.7 Atributo de switch en el control de ajustes.
            #     Sin cadena IK no hay nada que conmutar: crear el canal
            #     igualmente deja un atributo muerto en el channel box del
            #     animador, que es justo lo que se quiere evitar.
            switch_attr = None
            if ik_chain:
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