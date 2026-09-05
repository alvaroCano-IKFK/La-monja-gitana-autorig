"""toes_module.py  --  Dedos del pie para "La monja gitana".

Hereda de FingersModule para no duplicar toda la lógica cara (detección del eje
de curvatura, preferred angles, ikHandle + ikTarget, pairBlends, space switch).
Solo se sobreescribe lo que cambia entre una mano y un pie:

    * Las cadenas cuelgan del BALL bind ({prefix}_ball_bind_JNT), no del wrist.
    * La guía padre (L_ball) ya tiene un hijo que NO es un dedo: L_toe_tip.
      get_finger_roots() lo filtra, igual que el heel si alguien lo cuelga ahí.
    * En el pie no hay metacarpo: el "metatarso" es el propio ball, así que el
      solver arranca en el primer joint del dedo (ik_start_index = 0). Con eso
      un dedo de 4 joints ya deja la falange distal libre para rotarla con el
      control IK, exactamente igual que en la mano.
    * Nombres propios: _Toes_CTRL_GRP, toesSettings_CTRL, FollowFoot...

POR QUÉ ESTO NO ROMPE EL ROLL DEL PIE
-------------------------------------
El reverse foot vive entero en los grupos _SDK de los controles del pie
(footHeel/footTip/footBall) y mueve la cadena IK de la pierna a través de los
dos ikHandles SC (_footBall_HDL y _footTip_HDL). Nada de eso lee los hijos del
ball. Los dedos:

    - Cuelgan del ball BIND, que es un destino, no una fuente: el roll escribe
      en la cadena ik, el pairBlend la vuelca al bind y los dedos heredan.
    - Sus ikHandles viven fuera de la jerarquía de controles, en el
      {prefix}_leg_GRP, igual que hace la mano con el brazo.
    - Arrancan en FK (el atributo IK_FK vale 1 por defecto), así que mientras
      el animador no toque nada los dedos son hijos rígidos del ball.

IMPORTANTE: hay que construirlos ANTES del skinning_module, o los joints de los
dedos no entran en el esqueleto _ENV.
"""

import maya.cmds as cmds

import fingers_module


class ToesModule(fingers_module.FingersModule):

    # Etiquetas de nomenclatura (así el día que haya que renombrar algo, se
    # toca aquí y no en medio del build).
    GROUP_TAG       = "Toes"
    SETTINGS_SUFFIX = "toesSettings"
    SETTINGS_LABEL  = "TOES"
    FOLLOW_ATTR     = "FollowFoot"
    FOLLOW_NICE     = "Follow Foot"

    # ------------------------------------------------------------------ #
    #  INIT
    # ------------------------------------------------------------------ #
    def __init__(self,
                 ball_guide="L_ball",
                 tip_guide="L_toe_tip",
                 heel_guide="L_heel",
                 rig_name="Leg",
                 side="L",
                 root_instance=None,
                 build_ik=True,
                 pref_angle=8.0,
                 settings_ctrl=None,
                 ik_follow_foot=0.0,
                 attach_joint=None,
                 leg_grp=None):

        super(ToesModule, self).__init__(
            wrist_guide=ball_guide,
            rig_name=rig_name,
            side=side,
            root_instance=root_instance,
            build_ik=build_ik,
            pref_angle=pref_angle,
            settings_ctrl=settings_ctrl,
            ik_follow_hand=ik_follow_foot,
        )

        self.ball_guide = ball_guide
        self.tip_guide  = tip_guide
        self.heel_guide = heel_guide

        # Joint del que cuelgan las tres cadenas (bind / fk / ik) de cada dedo.
        self.attach_joint = attach_joint or f"{self.prefix}_ball_bind_JNT"

        # Grupo del rig de la pierna donde se guardan los ikHandles.
        self.leg_grp = leg_grp or f"{self.prefix}_leg_GRP"

        # El ball hace de metatarso, así que el solver empieza en el joint 0.
        self.ik_start_index = 0

        # Cuánto se levanta del suelo el control de ajustes, para poder pincharlo.
        self.settings_lift    = 4.0
        self.settings_reach   = 2.2

        # Alias legible. Es el MISMO diccionario que fingers_data, no una copia.
        self.toes_data = self.fingers_data

    # ------------------------------------------------------------------ #
    #  LIMPIEZA DE BUILDS ANTERIORES
    # ------------------------------------------------------------------ #
    def _cleanup_previous_build(self):
        for grp in (f"{self.prefix}_{self.GROUP_TAG}_CTRL_GRP",
                    f"{self.prefix}_{self.GROUP_TAG}_IKH_GRP"):
            if cmds.objExists(grp):
                cmds.delete(grp)

    def _cleanup_previous_joints(self, guide_roots):
        """Borra las cadenas bind/fk/ik de un build anterior.

        El cleanup de la clase padre solo se lleva los grupos de controles, pero
        los joints cuelgan del ball bind y sobrevivirían, dejando duplicados con
        nombre '...JNT1' en el siguiente build.
        """
        for guide in guide_roots:
            short = guide.split("|")[-1].split(":")[-1]
            base  = f"{self.prefix}_{short}"
            for node in (f"{base}_JNT", f"{base}_fk_JNT", f"{base}_ik_JNT"):
                if cmds.objExists(node):
                    cmds.delete(node)

    # ------------------------------------------------------------------ #
    #  GUÍAS
    # ------------------------------------------------------------------ #
    def get_finger_roots(self):
        """Hijos de la guía del ball que son dedos de verdad.

        Filtra el toe_tip (que es un helper del roll, no un dedo) y el heel por
        si alguien lo reparenta ahí algún día.
        """
        children = cmds.listRelatives(self.wrist_guide, c=True, type="joint") or []

        excluded = set()
        for name in (self.tip_guide, self.heel_guide):
            if name:
                excluded.add(name.split("|")[-1].split(":")[-1])

        roots = []
        for child in children:
            short = child.split("|")[-1].split(":")[-1]
            if short in excluded:
                continue
            low = short.lower()
            if "toe_tip" in low or "heel" in low or low.endswith("_tip"):
                continue
            roots.append(child)
        return roots

    # ------------------------------------------------------------------ #
    #  CONTROL DE AJUSTES
    # ------------------------------------------------------------------ #
    def get_or_create_settings_ctrl(self, bind_ball, all_chains):
        """Control donde viven los atributos <dedo>_IK_FK.

        Si le pasas settings_ctrl en el constructor (por ejemplo
        'L_Leg_switch_CTRL') reutiliza ese y no crea nada.
        """
        if self.settings_ctrl and cmds.objExists(self.settings_ctrl):
            return self.settings_ctrl

        name = f"{self.prefix}_{self.SETTINGS_SUFFIX}_CTRL"
        if cmds.objExists(name):
            self.settings_ctrl = name
            return name

        ctrl = self._create_ctrl(self.styles["switch"], name)
        target = bind_ball if cmds.objExists(bind_ball) else self.wrist_guide
        gen = self.group_maker.create_rig_hierarchy(ctrl, target)

        if self.ctrls_master_grp:
            self._safe_parent(gen, self.ctrls_master_grp)

        # Se coloca por delante de las puntas de los dedos y algo levantado,
        # para que no quede enterrado en el suelo.
        ball_pos = cmds.xform(target, q=True, ws=True, t=True)
        tips = [cmds.xform(c[-1], q=True, ws=True, t=True) for c in all_chains if c]
        if tips:
            avg = [sum(t[i] for t in tips) / float(len(tips)) for i in range(3)]
            direction = self._sub(avg, ball_pos)
            pos = self._add(ball_pos, self._scale(direction, self.settings_reach))
            pos[1] += self.settings_lift
            cmds.xform(gen, ws=True, t=pos)

        if cmds.objExists(bind_ball):
            cmds.parentConstraint(bind_ball, gen, mo=True)

        if not cmds.attributeQuery(self.SETTINGS_LABEL, node=ctrl, exists=True):
            cmds.addAttr(ctrl, ln=self.SETTINGS_LABEL, nn=self.SETTINGS_LABEL,
                         at="enum", en="------", k=True)
            cmds.setAttr(f"{ctrl}.{self.SETTINGS_LABEL}", lock=True, cb=True)

        self.settings_ctrl = ctrl
        return ctrl

    # ------------------------------------------------------------------ #
    #  SPACE SWITCH DEL CONTROL IK  (mundo <-> pie)
    # ------------------------------------------------------------------ #
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

    # ------------------------------------------------------------------ #
    #  BUILD
    # ------------------------------------------------------------------ #
    def build(self):
        """Construye los dedos del pie (IK + FK + switch por dedo)."""

        # ---- COMPROBACIONES PREVIAS ----
        if not cmds.objExists(self.wrist_guide):
            cmds.warning(f"[toes] No existe la guía '{self.wrist_guide}'. "
                         f"Crea las guías del pie antes de construir.")
            return

        attach = self.attach_joint
        if not cmds.objExists(attach):
            cmds.warning(f"[toes] No existe {attach}. Construye el LegModule "
                         f"antes que los dedos del pie.")
            return

        toe_roots = self.get_finger_roots()
        if not toe_roots:
            cmds.warning(f"[toes] '{self.wrist_guide}' no tiene guías de dedos "
                         f"(solo el toe_tip). Añade las guías con ToesGuides.")
            return

        # ---- LIMPIEZA DE UN BUILD ANTERIOR ----
        self._cleanup_previous_build()
        self._cleanup_previous_joints(toe_roots)

        # ---- GRUPOS MAESTROS ----
        self.ctrls_master_grp = cmds.group(
            em=True, n=f"{self.prefix}_{self.GROUP_TAG}_CTRL_GRP")
        self.ikh_master_grp = cmds.group(
            em=True, n=f"{self.prefix}_{self.GROUP_TAG}_IKH_GRP")

        # ---- 1. CADENAS BIND (todavía en world, sin emparentar) ----
        built = []          # [(toe_name, guide_root, bind_chain), ...]
        used_names = {}
        for root in toe_roots:
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
        settings = self.get_or_create_settings_ctrl(attach, all_chains)

        # Plan B para dedos totalmente rectos: el eje "a través del pie".
        fallback_normal = self.fallback_curl_normal(all_chains)

        # ---- 3. DEDO A DEDO ----
        for toe_name, guide_root, bind_chain in built:

            # 3.1 Normal de curvatura ANTES de duplicar (misma pose en las 3 cadenas)
            curl_normal = self.detect_curl_normal(bind_chain)
            if curl_normal is None:
                curl_normal = fallback_normal
                if not self.curl_axis_override.get(toe_name):
                    cmds.warning(f"[toes] '{toe_name}' está recto en la guía: uso el eje "
                                 f"transversal del pie. Si dobla al revés usa "
                                 f"curl_axis_override.")

            # 3.2 Duplicar cadenas FK / IK
            fk_chain = self.duplicate_chain(bind_chain, "fk")
            ik_chain = self.duplicate_chain(bind_chain, "ik") if self.build_ik else []

            # 3.3 Las tres cadenas cuelgan del ball bind (mismos valores locales)
            cmds.parent(bind_chain[0], attach)
            cmds.parent(fk_chain[0], attach)
            if ik_chain:
                cmds.parent(ik_chain[0], attach)

            cmds.setAttr(f"{fk_chain[0]}.visibility", 0)
            if ik_chain:
                cmds.setAttr(f"{ik_chain[0]}.visibility", 0)

            # 3.4 Grupos de organización / visibilidad
            fk_grp = cmds.group(em=True, n=f"{self.prefix}_{toe_name}_fkCtrls_GRP",
                                p=self.ctrls_master_grp)
            ik_grp = cmds.group(em=True, n=f"{self.prefix}_{toe_name}_ikCtrls_GRP",
                                p=self.ctrls_master_grp) if ik_chain else None

            # 3.5 Controles FK
            fk_ctrls = self.create_finger_controls(fk_chain, attach, parent_grp=fk_grp)

            # 3.6 Setup IK
            ik_ctrl, ik_handle = (None, None)
            if ik_chain:
                ik_ctrl, ik_handle = self.create_finger_ik(ik_chain, attach,
                                                           toe_name,
                                                           parent_grp=ik_grp,
                                                           curl_normal=curl_normal)
                if ik_ctrl is None:
                    cmds.delete(ik_chain[0])
                    ik_chain = []
                    if ik_grp and cmds.objExists(ik_grp):
                        cmds.delete(ik_grp)
                        ik_grp = None

            # 3.7 Atributo de switch en el control de ajustes
            attr_name = f"{toe_name}_IK_FK"
            if not cmds.attributeQuery(attr_name, node=settings, exists=True):
                cmds.addAttr(settings, ln=attr_name, at="double",
                             min=0, max=1, dv=1, k=True)
            switch_attr = f"{settings}.{attr_name}"

            # 3.8 Blend
            self.blend_chains(bind_chain, ik_chain, fk_chain, switch_attr, toe_name)

            # 3.9 Visibilidad (1 = FK, 0 = IK)
            if ik_grp:
                vis_rev = cmds.createNode("reverse",
                                          n=f"{self.prefix}_{toe_name}_VIS_REV")
                cmds.connectAttr(switch_attr, f"{vis_rev}.inputX")
                cmds.connectAttr(switch_attr, f"{fk_grp}.visibility")
                cmds.connectAttr(f"{vis_rev}.outputX", f"{ik_grp}.visibility")

            self.fingers_data[toe_name] = {
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
        # Los ikHandles van fuera de los controles (por el scaleX -1 del lado R).
        rig_grp = f"{self.root_instance.rig_name}_rig_GRP" if self.root_instance else None
        if cmds.objExists(self.leg_grp):
            cmds.parent(self.ikh_master_grp, self.leg_grp)
        elif rig_grp and cmds.objExists(rig_grp):
            cmds.parent(self.ikh_master_grp, rig_grp)
        else:
            cmds.warning(f"[toes] No encuentro {self.leg_grp}: el grupo de "
                         f"ikHandles se queda en la raíz de la escena.")

        if self.side == "R":
            mirror_grp = f"{self.root_instance.rig_name}_mirrorBehaviour_GRP" \
                if self.root_instance else "Character_mirrorBehaviour_GRP"
            if cmds.objExists(mirror_grp):
                cmds.parent(self.ctrls_master_grp, mirror_grp)
            else:
                cmds.warning(f"[toes] build: no existe {mirror_grp}")
        else:
            local_ctl = self.root_instance.localCtl if self.root_instance else None
            if local_ctl and cmds.objExists(local_ctl):
                cmds.parent(self.ctrls_master_grp, local_ctl)

        print(f"Build {self.prefix} toes completo. Dedos del pie: "
              f"{list(self.fingers_data.keys())}")

    # ------------------------------------------------------------------ #
    #  UTILIDAD PARA ANIMACIÓN
    # ------------------------------------------------------------------ #
    def match_all_ik_to_fk(self, switch=True):
        """Pega todos los controles IK a la pose FK actual y cambia el switch."""
        for toe_name in self.fingers_data:
            if self.fingers_data[toe_name].get("ik_ctrl"):
                self.match_ik_to_fk(toe_name, switch=switch)