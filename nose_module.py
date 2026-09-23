import maya.cmds as cmds
import controlsLibrary
import module_specs


class NoseModule(module_specs.FeaturesMixin):
    """
    Modul del nas.

    Una UNICA instancia construeix les DOS aletes (nostrils), igual que la
    boca: guides_module.NoseGuides nomes crea la guia de l'aleta al costat
    +X ("L_nose_nostril"). Aquest modul llegeix aquesta guia i en treu el
    costat R invertint la X ell mateix -- no cal passar per MIRROR ni tenir
    cap guia "R_nose_nostril" a l'escena.

    IMPORTANT: la signatura ha de coincidir amb com el crida build_module.py
    (_build_nose):

        nose_module.NoseModule(
            rig_name=self.RIG_NAME,
            root_instance=self.root_rig,
            features=features,
        )

    No rep "side": build_module no en passa cap per aquest modul (com la
    boca), perque una sola crida ja fa els dos costats.

    TODO (pendent, falta groups_module.py per fer-ho be):
    Els controls d'aquest modul es posicionen amb un cmds.xform manual
    (namas translate, sense grup pare ni orientacio). NO es aixi com ho fa
    la resta del rig: eyebrowsModule.py (i probablement tots els altres
    moduls de cara) creen el control amb controlsLibrary.create_control_
    from_lib() i despres el passen per:

        self.group_maker = groups_module.ControlsGroups()
        ctrl_gen = self.group_maker.create_rig_hierarchy(ctrl, guide_name)

    create_rig_hierarchy() sembla crear la jerarquia d'offset estandard
    (grups _OFF/_SDK/etc, per com s'usa) i posicionar/orientar el control
    contra la GUIA (no contra el joint). Falta veure groups_module.py per
    saber exactament quins grups crea i que retorna.

    Complicacio especifica del nas: el nostril R no te guia real (es
    treu invertint la X de "L_nose_nostril" dins d'aquest modul), aixi que
    create_rig_hierarchy no li pot passar un nom de guia per al costat R
    directament -- probablement calgui cridar-lo amb la guia L i despres
    mirallar el grup resultant, pero cal confirmar-ho amb el codi real.

    Quan es tingui groups_module.py, reescriure create_controllers() per
    seguir aquest mateix patro en lloc del cmds.xform manual d'ara.
    """

    def __init__(self, rig_name="rig", root_instance=None, features=None):
        self._init_features("nose", features)

        self.rig_name = rig_name
        self.root_instance = root_instance
        self.center_prefix = f"C_{self.rig_name}_"

        # Noms de les guies TAL COM les crea guides_module.NoseGuides.
        # Cap guia de tot el rig porta sufix "_GUIDE". "L_nose_nostrilBase"
        # es de centre (X=0) malgrat el prefix "L_" del nom; "L_nose_nostril"
        # si que es lateral (X>0) i es l'unica guia real de l'aleta.
        self.nose_root_guide = "nose_root"
        self.nose_tip_guide = "nose_tip"
        self.base_nostril_guide = "L_nose_nostrilBase"
        self.nostril_guide = "L_nose_nostril"

        # Noms dels joints definitius
        self.nose_root_jnt = f"{self.center_prefix}noseRoot_JNT"
        self.nose_tip_jnt = f"{self.center_prefix}noseTip_JNT"
        self.base_nostril_jnt = f"{self.center_prefix}nostrilBase_JNT"
        self.nostril_jnt = {
            "L": f"L_{self.rig_name}_nostril_JNT",
            "R": f"R_{self.rig_name}_nostril_JNT",
        }
        self.nostril_jnt_dup = {
            "L": f"L_{self.rig_name}_nostril_dup_JNT",
            "R": f"R_{self.rig_name}_nostril_dup_JNT",
        }

        # Controladors: un nostril_CTRL per costat, un base_nostril_CTRL i
        # nose_root/nose_tip_CTRL unics de centre.
        self.nostril_ctrl = {
            "L": f"L_{self.rig_name}_nostril_CTRL",
            "R": f"R_{self.rig_name}_nostril_CTRL",
        }
        self.base_nostril_ctrl = f"{self.center_prefix}nostrilBase_CTRL"
        self.nose_root_ctrl = f"{self.center_prefix}noseRoot_CTRL"
        self.nose_tip_ctrl = f"{self.center_prefix}noseTip_CTRL"

        self.joints = []
        self.controls = []

    # ------------------------------------------------------------------
    # GUIES
    # ------------------------------------------------------------------

    def _required_guides(self):
        """Guies que fan falta segons les features actives."""
        guides = [self.nose_root_guide, self.nose_tip_guide]

        if self.has("nostrils"):
            guides += [self.base_nostril_guide, self.nostril_guide]

        return guides

    def _missing_guides(self):
        return [g for g in self._required_guides() if not cmds.objExists(g)]

    # ------------------------------------------------------------------
    # JOINTS
    # ------------------------------------------------------------------

    def _create_joint_from_guide(self, guide_name, joint_name, mirror_x=False):
        """
        Crea un joint a la posicio d'una guia. Si mirror_x=True, inverteix
        la component X de la posicio -- aixi es treu el costat R sense que
        calgui cap guia R_ real a l'escena.
        """
        if not cmds.objExists(guide_name):
            cmds.warning(f"La guia {guide_name} no existeix.")
            return None

        pos = cmds.xform(guide_name, q=True, ws=True, t=True)
        if mirror_x:
            pos = [-pos[0], pos[1], pos[2]]

        cmds.select(clear=True)
        jnt = cmds.joint(name=joint_name)
        cmds.xform(jnt, ws=True, t=pos)

        return jnt

    def create_nose_joints(self):
        """Crea els joints principals del nas a partir de la posicio de les guies."""
        cmds.select(clear=True)

        self.nose_root_jnt = self._create_joint_from_guide(
            self.nose_root_guide, self.nose_root_jnt
        )
        self.nose_tip_jnt = self._create_joint_from_guide(
            self.nose_tip_guide, self.nose_tip_jnt
        )

        self.joints = [self.nose_root_jnt, self.nose_tip_jnt]

        # Les aletes son opcionals (feature "nostrils"): sense elles nomes hi
        # ha nose_root i nose_tip.
        if self.has("nostrils"):
            self.base_nostril_jnt = self._create_joint_from_guide(
                self.base_nostril_guide, self.base_nostril_jnt
            )

            # L es la posicio real de la guia; R surt de mirallar-ne la X.
            self.nostril_jnt["L"] = self._create_joint_from_guide(
                self.nostril_guide, self.nostril_jnt["L"], mirror_x=False
            )
            self.nostril_jnt["R"] = self._create_joint_from_guide(
                self.nostril_guide, self.nostril_jnt["R"], mirror_x=True
            )

            self.joints += [
                self.base_nostril_jnt,
                self.nostril_jnt["L"],
                self.nostril_jnt["R"],
            ]

        cmds.select(clear=True)
        return self.joints

    def duplicate_nostril_joints(self):
        """
        Duplica els dos joints de nostril (L i R) mantenint exactament la
        mateixa posicio. Nomes si "nostrils" i "nostril_dup" estan actives.
        parentOnly=True evita duplicar fills que pengin del joint original.
        """
        if not (self.has("nostrils") and self.has("nostril_dup")):
            return {}

        for side in ("L", "R"):
            dup = cmds.duplicate(
                self.nostril_jnt[side],
                name=self.nostril_jnt_dup[side],
                parentOnly=True,
            )[0]

            # Si el duplicat queda penjat com a fill de l'original, el
            # traiem a world.
            parent = cmds.listRelatives(dup, parent=True)
            if parent:
                cmds.parent(dup, world=True)

            self.nostril_jnt_dup[side] = dup
            self.joints.append(dup)

        return self.nostril_jnt_dup

    # ------------------------------------------------------------------
    # CONTROLADORS
    # ------------------------------------------------------------------

    def create_controllers(self):
        """
        Crea els controladors: nose_root i nose_tip sempre (son features
        "always"), i els dos nostrils + base_nostril nomes si "nostrils"
        esta activa. Fa servir la mateixa shape "circle" de la libreria que
        s'usa a la boca (controlsLibrary.create_control_from_lib).
        """
        nose_root_pos = cmds.xform(self.nose_root_jnt, q=True, ws=True, t=True)
        nose_root_ctrl = controlsLibrary.create_control_from_lib(
            lib_name="circle",
            final_name=self.nose_root_ctrl,
        )
        cmds.xform(nose_root_ctrl, ws=True, t=nose_root_pos)
        self.nose_root_ctrl = nose_root_ctrl
        self.controls.append(nose_root_ctrl)

        nose_tip_pos = cmds.xform(self.nose_tip_jnt, q=True, ws=True, t=True)
        nose_tip_ctrl = controlsLibrary.create_control_from_lib(
            lib_name="circle",
            final_name=self.nose_tip_ctrl,
        )
        cmds.xform(nose_tip_ctrl, ws=True, t=nose_tip_pos)
        self.nose_tip_ctrl = nose_tip_ctrl
        self.controls.append(nose_tip_ctrl)

        if not self.has("nostrils"):
            return self.controls

        for side in ("L", "R"):
            nostril_pos = cmds.xform(self.nostril_jnt[side], q=True, ws=True, t=True)

            nostril_ctrl = controlsLibrary.create_control_from_lib(
                lib_name="circle",
                final_name=self.nostril_ctrl[side],
            )
            cmds.xform(nostril_ctrl, ws=True, t=nostril_pos)

            self.nostril_ctrl[side] = nostril_ctrl
            self.controls.append(nostril_ctrl)

        base_nostril_pos = cmds.xform(self.base_nostril_jnt, q=True, ws=True, t=True)

        base_nostril_ctrl = controlsLibrary.create_control_from_lib(
            lib_name="circle",
            final_name=self.base_nostril_ctrl,
        )
        cmds.xform(base_nostril_ctrl, ws=True, t=base_nostril_pos)

        self.base_nostril_ctrl = base_nostril_ctrl
        self.controls.append(base_nostril_ctrl)

        return self.controls

    # ------------------------------------------------------------------
    # CONSTRAINTS
    # ------------------------------------------------------------------

    def constraint_joints_to_controllers(self):
        """
        Parent constraint de nose_root i nose_tip al seu control (sempre),
        dels joints de cada nostril (original + duplicat, si n'hi ha) cap
        al seu propi controlador, i del joint de base_nostril cap al seu
        controlador de centre (nomes si "nostrils" esta activa).
        """
        cmds.parentConstraint(
            self.nose_root_ctrl, self.nose_root_jnt, maintainOffset=True
        )
        cmds.parentConstraint(
            self.nose_tip_ctrl, self.nose_tip_jnt, maintainOffset=True
        )

        if not self.has("nostrils"):
            return

        for side in ("L", "R"):
            cmds.parentConstraint(
                self.nostril_ctrl[side], self.nostril_jnt[side], maintainOffset=True
            )

            if self.has("nostril_dup"):
                cmds.parentConstraint(
                    self.nostril_ctrl[side], self.nostril_jnt_dup[side],
                    maintainOffset=True,
                )

        cmds.parentConstraint(
            self.base_nostril_ctrl, self.base_nostril_jnt, maintainOffset=True
        )

    # ------------------------------------------------------------------
    # BUILD COMPLET
    # ------------------------------------------------------------------

    def build(self):
        """
        Executa tot el modul en ordre. Una sola crida construeix L i R.

        Torna None (i avisa) si falta alguna guia -- aixi build_module la
        pot saltar en lloc de petar, igual que fa amb la boca, el jaw, les
        celles i els ulls.
        """
        missing = self._missing_guides()
        if missing:
            cmds.warning(
                "[Nose] Falten guies ({}). Es salta el nas.".format(
                    ", ".join(missing))
            )
            return None

        self.create_nose_joints()
        self.duplicate_nostril_joints()
        self.create_controllers()
        self.constraint_joints_to_controllers()

        return self.joints, self.controls